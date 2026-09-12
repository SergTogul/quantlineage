"""Shared pricing + historical-dataset construction for API and worker (R0.8.2 / R0.8.4).

FastAPI lifespan and ``python -m app.worker`` must call
:func:`build_portfolio_service` so interactive and queued runs resolve the
same historical dataset and calculation knobs.

R0.8.4: typed request blobs drive dataset selection. A client-supplied
``historical_dataset_id`` either rebinds the engine through these helpers or
raises — it is never stored as a label while execution silently uses another
dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

from app.api.schemas import (
    RiskRunRequestBody,
    dump_risk_run_request,
    parse_risk_run_request,
)
from app.domain.models import (
    AsOfLabel,
    MarketSnapshot,
    RiskRun,
    RiskRunCalculationConfig,
    as_of_wire,
)
from app.interfaces.pricing import PricingEngine
from app.market.history.artifact import resolve_public_history_csv
from app.market.history.spec import WAVE_A_DATASET_ID
from app.market.snapshot import FixedMarketDataProvider
from app.pricing.factory import create_pricing_engine
from app.risk.factor_panel import factor_panel_from_dataset, truncate_factor_panel
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import (
    DEMO_HISTORICAL_DATASET_ID,
    DEMO_MULTI_FACTOR_DATASET_ID,
    FileHistoricalDataset,
    PerFactorFileHistoricalDataset,
    SyntheticHistoricalDataset,
    create_historical_dataset,
    file_csv_dataset_id,
)
from app.services.portfolio_service import PortfolioService

DEFAULT_HISTORICAL_DATASET_VERSION = "v1"
DEFAULT_HISTORICAL_PANEL_SEED = 7
SYNTHETIC_HISTORICAL_DATASET_ID = "synthetic-historical-factors"

# Canonical id / short alias → create_historical_dataset source key.
_DATASET_SOURCE_BY_ID: dict[str, str] = {
    DEMO_MULTI_FACTOR_DATASET_ID: DEMO_MULTI_FACTOR_DATASET_ID,
    "demo-multi-factor": DEMO_MULTI_FACTOR_DATASET_ID,
    "per_factor": DEMO_MULTI_FACTOR_DATASET_ID,
    "per-factor": DEMO_MULTI_FACTOR_DATASET_ID,
    DEMO_HISTORICAL_DATASET_ID: "demo",
    "demo": "demo",
    "demo-historical": "demo",
    SYNTHETIC_HISTORICAL_DATASET_ID: "synthetic",
    "synthetic": "synthetic",
    "rng": "synthetic",
    "random": "synthetic",
}


@dataclass(frozen=True, slots=True)
class ResolvedRiskRunSpec:
    """Deterministic spec columns implied by the shared factory and/or request."""

    historical_dataset_id: str
    historical_dataset_version: str
    as_of: date | AsOfLabel | None = None
    calculation_config: RiskRunCalculationConfig | None = None


def resolve_dataset_source(historical_dataset_id: str) -> str:
    """Map a client dataset id to a ``create_historical_dataset`` source.

    Raises ``ValueError`` when the id is not a known demo/synthetic alias and
    is not an existing CSV path — callers must not silently ignore it.

    Bare ``\"file\"`` is ambiguous (legacy collapsed CSV identity) and is
    rejected. Canonical CSV ids use ``file:<abspath>``; plain existing ``.csv``
    paths are also accepted and normalize to that form downstream.
    """
    raw = historical_dataset_id.strip()
    if not raw:
        raise ValueError("historical_dataset_id must be non-empty when set")
    if raw.lower() == "file":
        raise ValueError(
            "ambiguous historical_dataset_id 'file'; "
            "provide a concrete CSV path or file:<absolute-path>"
        )
    aliased = _DATASET_SOURCE_BY_ID.get(raw) or _DATASET_SOURCE_BY_ID.get(raw.lower())
    if aliased is not None:
        return aliased
    if raw == WAVE_A_DATASET_ID or raw.lower() == WAVE_A_DATASET_ID:
        return str(resolve_public_history_csv())
    path_raw = raw
    if raw.startswith("file:"):
        path_raw = raw[len("file:") :]
        if not path_raw.strip():
            raise ValueError(
                "ambiguous historical_dataset_id 'file:'; "
                "provide file:<absolute-path> to an existing factor CSV"
            )
    path = Path(path_raw).expanduser()
    if path.suffix.lower() == ".csv" or path.is_file():
        if not path.is_file():
            raise ValueError(f"historical dataset CSV not found: {path}")
        return str(path.resolve())
    raise ValueError(
        f"unsupported historical_dataset_id: {historical_dataset_id!r}; "
        f"use {DEMO_MULTI_FACTOR_DATASET_ID!r}, {DEMO_HISTORICAL_DATASET_ID!r}, "
        f"{SYNTHETIC_HISTORICAL_DATASET_ID!r}, {WAVE_A_DATASET_ID!r}, "
        f"or a path to a factor CSV"
    )


def build_historical_risk_engine(
    *,
    historical_dataset_id: str | None = None,
    seed: int | None = None,
    observations: int | None = None,
) -> HistoricalRiskEngine:
    """Wire production historical VaR to a per-factor panel.

    When ``historical_dataset_id`` is set, selects that dataset via
    :func:`resolve_dataset_source` (rebind). Otherwise uses env / per-factor
    demo default (not the four-macro fixture).
    """
    panel_seed = DEFAULT_HISTORICAL_PANEL_SEED if seed is None else seed
    dataset_kwargs: dict[str, Any] = {"seed": panel_seed}
    if observations is not None:
        dataset_kwargs["observations"] = observations

    if historical_dataset_id is not None:
        source = resolve_dataset_source(historical_dataset_id)
        dataset = create_historical_dataset(source, **dataset_kwargs)
    else:
        dataset = create_historical_dataset(**dataset_kwargs)

    panel = factor_panel_from_dataset(
        dataset,
        observations=observations,
        seed=panel_seed,
    )
    return HistoricalRiskEngine(
        dataset=dataset,
        observations=panel.n_observations,
        seed=panel_seed,
        factor_panel=panel,
    )


def build_portfolio_service(
    *,
    historical_dataset_id: str | None = None,
    seed: int | None = None,
    observations: int | None = None,
    market_data: Any | None = None,
) -> PortfolioService:
    """Construct the process-wide pricing + historical risk stack.

    Used by FastAPI lifespan (``app.state.portfolio_service``) and Compose ``app.worker``.
    Optional kwargs rebuild the historical engine for a rebound run spec.
    """
    engine = build_historical_risk_engine(
        historical_dataset_id=historical_dataset_id,
        seed=seed,
        observations=observations,
    )
    if market_data is None:
        return PortfolioService(create_pricing_engine(), engine)
    return PortfolioService(create_pricing_engine(), engine, market_data=market_data)


def dataset_identity(dataset: object) -> tuple[str, str]:
    """Stable id/version for a resolved historical dataset instance."""
    if isinstance(dataset, PerFactorFileHistoricalDataset):
        raw_id = (dataset.dataset_id or "").strip()
        version = (dataset.dataset_version or "").strip() or DEFAULT_HISTORICAL_DATASET_VERSION
        if raw_id and raw_id != "file":
            return raw_id, version
        if dataset.source_path:
            return file_csv_dataset_id(dataset.source_path), version
        return DEMO_MULTI_FACTOR_DATASET_ID, version
    if isinstance(dataset, FileHistoricalDataset):
        raw_id = (dataset.dataset_id or "").strip()
        if raw_id and raw_id != "file":
            return raw_id, DEFAULT_HISTORICAL_DATASET_VERSION
        if dataset.source_path:
            return file_csv_dataset_id(dataset.source_path), DEFAULT_HISTORICAL_DATASET_VERSION
        return DEMO_HISTORICAL_DATASET_ID, DEFAULT_HISTORICAL_DATASET_VERSION
    raw_id = getattr(dataset, "dataset_id", None)
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip(), DEFAULT_HISTORICAL_DATASET_VERSION
    if isinstance(dataset, SyntheticHistoricalDataset):
        return SYNTHETIC_HISTORICAL_DATASET_ID, DEFAULT_HISTORICAL_DATASET_VERSION
    return SYNTHETIC_HISTORICAL_DATASET_ID, DEFAULT_HISTORICAL_DATASET_VERSION


def _copy_historical_engine(
    engine: HistoricalRiskEngine,
    *,
    observations: int,
    dataset: object,
    factor_panel: object,
) -> HistoricalRiskEngine:
    return HistoricalRiskEngine(
        seed=engine.seed,
        observations=observations,
        dataset=dataset,  # type: ignore[arg-type]
        methodology=engine.methodology,
        scenario_kernel=engine.scenario_kernel,
        scenario_backend=engine.scenario_backend,
        factor_panel=factor_panel,  # type: ignore[arg-type]
    )


def resize_historical_risk_engine(
    engine: HistoricalRiskEngine,
    observations: int,
) -> HistoricalRiskEngine:
    """Rebuild/truncate from the same dataset and factor identities.

    Shrinking truncates the current panel (and a synthetic dataset's observation
    count). Growing a synthetic dataset regenerates the panel with the same seed
    and factors. Growing past a file dataset's length raises — it does not
    switch to a bare four-macro synthetic engine. A source engine with
    ``factor_panel is None`` stays on the four-macro path (no default panel).
    """
    if observations == engine.observations:
        return engine
    if observations < 1:
        raise ValueError("observations must be >= 1")

    panel = engine.factor_panel
    dataset = engine.dataset
    factors = None if panel is None else panel.factors

    if panel is None:
        # Keep the labeled four-macro path. Do not invent DEFAULT_PRODUCTION_PANEL_FACTORS.
        new_dataset = dataset
        if isinstance(dataset, SyntheticHistoricalDataset):
            new_dataset = replace(dataset, observations=observations)
        else:
            n_obs = getattr(dataset, "n_observations", None)
            source_len = (
                int(n_obs)
                if isinstance(n_obs, int)
                else dataset.factor_observations().n_observations
            )
            if observations > source_len:
                raise ValueError(
                    f"observations {observations} exceeds historical dataset length {source_len}"
                )
        return _copy_historical_engine(
            engine,
            observations=observations,
            dataset=new_dataset,
            factor_panel=None,
        )

    if observations < panel.n_observations:
        new_panel = truncate_factor_panel(panel, observations)
        new_dataset = dataset
        if isinstance(dataset, SyntheticHistoricalDataset):
            new_dataset = replace(dataset, observations=observations)
        return _copy_historical_engine(
            engine,
            observations=observations,
            dataset=new_dataset,
            factor_panel=new_panel,
        )

    if isinstance(dataset, SyntheticHistoricalDataset):
        new_dataset = replace(dataset, observations=observations)
        new_panel = factor_panel_from_dataset(
            new_dataset,
            factors=factors,
            observations=observations,
            seed=engine.seed,
        )
        return _copy_historical_engine(
            engine,
            observations=observations,
            dataset=new_dataset,
            factor_panel=new_panel,
        )

    n_obs = getattr(dataset, "n_observations", None)
    source_len = (
        int(n_obs) if isinstance(n_obs, int) else dataset.factor_observations().n_observations
    )
    if observations > source_len:
        raise ValueError(
            f"observations {observations} exceeds historical dataset length {source_len}"
        )
    new_panel = factor_panel_from_dataset(
        dataset,
        factors=factors,
        observations=observations,
        seed=engine.seed,
    )
    return _copy_historical_engine(
        engine,
        observations=observations,
        dataset=dataset,
        factor_panel=new_panel,
    )


def bind_pricing_engine(
    pricing_engine_version: str | None,
    *,
    fallback: PricingEngine | None = None,
) -> PricingEngine:
    """Bind a pricing adapter from a run's ``pricing_engine_version``.

    Unset versions use ``fallback`` (the process engine that execute used).
    Unknown versions fail closed — they are never silently ignored.
    """
    raw = (pricing_engine_version or "").strip()
    if not raw:
        if fallback is None:
            raise ValueError("pricing_engine_version missing; cannot bind pricing")
        return fallback
    key = raw.lower()
    if key.startswith("builtin"):
        from app.pricing.builtin import BuiltinPricingEngine

        return BuiltinPricingEngine()
    if key.startswith("quantlib"):
        from app.pricing.quantlib import QuantLibPricingEngine

        return QuantLibPricingEngine()
    raise ValueError(f"cannot bind pricing engine version {pricing_engine_version!r}")


def build_historical_risk_engine_for_spec(
    spec: ResolvedRiskRunSpec,
) -> HistoricalRiskEngine:
    """Build an engine whose dataset identity matches ``spec`` (execute-time rebind)."""
    cfg = spec.calculation_config
    return build_historical_risk_engine(
        historical_dataset_id=spec.historical_dataset_id,
        seed=None if cfg is None else cfg.seed,
        observations=None if cfg is None else cfg.observations,
    )


def portfolio_service_for_spec(
    base: PortfolioService,
    spec: ResolvedRiskRunSpec,
    *,
    market: MarketSnapshot | None = None,
) -> PortfolioService:
    """Return ``base`` when its engine already matches ``spec``; otherwise rebound.

    When ``market`` is provided, the returned service always binds
    :class:`FixedMarketDataProvider` to that snapshot (RiskRun lineage).
    """
    market_data = (
        FixedMarketDataProvider(market) if market is not None else base.market_data
    )
    engine = getattr(base, "risk", None)
    if isinstance(engine, HistoricalRiskEngine):
        current_id, current_version = dataset_identity(engine.dataset)
        cfg = spec.calculation_config
        seed_ok = cfg is None or cfg.seed is None or cfg.seed == engine.seed
        obs_ok = (
            cfg is None
            or cfg.observations is None
            or cfg.observations == engine.observations
        )
        if (
            current_id == spec.historical_dataset_id
            and current_version == spec.historical_dataset_version
            and seed_ok
            and obs_ok
        ):
            if market is None:
                return base
            return PortfolioService(base.pricing, engine, market_data=market_data)
    rebound = build_historical_risk_engine_for_spec(spec)
    return PortfolioService(
        base.pricing,
        rebound,
        market_data=market_data,
    )


def resolve_run_spec(
    request: dict[str, Any] | RiskRunRequestBody | None = None,
    *,
    risk_engine: HistoricalRiskEngine | None = None,
    run_type: str = "summary",
) -> ResolvedRiskRunSpec:
    """Merge typed request-blob spec fields with the factory-resolved dataset/config.

    When the request names a ``historical_dataset_id``, that dataset is resolved
    (and must be supported). The returned identity is always the canonical id
    of the selected dataset — never a free-form label that execution ignores.
    """
    if isinstance(request, RiskRunRequestBody):
        typed = request
    else:
        typed = parse_risk_run_request(run_type, request)
    req = dump_risk_run_request(typed)

    requested_id = _nonempty_str(req.get("historical_dataset_id"))
    requested_version = _nonempty_str(req.get("historical_dataset_version"))
    cfg = typed.calculation_config

    seed = None if cfg is None else cfg.seed
    observations = None if cfg is None else cfg.observations

    if requested_id is not None:
        # Fail closed on unknown ids; rebind known aliases / CSV paths.
        resolve_dataset_source(requested_id)
        selected = build_historical_risk_engine(
            historical_dataset_id=requested_id,
            seed=seed,
            observations=observations,
        )
    elif risk_engine is not None:
        selected = risk_engine
        if seed is not None or observations is not None:
            current_id, _ = dataset_identity(risk_engine.dataset)
            selected = build_historical_risk_engine(
                historical_dataset_id=current_id,
                seed=seed if seed is not None else risk_engine.seed,
                observations=(
                    observations if observations is not None else risk_engine.observations
                ),
            )
    else:
        selected = build_historical_risk_engine(
            seed=seed,
            observations=observations,
        )

    dataset_id, dataset_version = dataset_identity(selected.dataset)
    if requested_version is not None and requested_version != dataset_version:
        raise ValueError(
            f"unsupported historical_dataset_version: {requested_version!r}; "
            f"expected {dataset_version!r}"
        )

    factory_config = RiskRunCalculationConfig(
        observations=selected.observations,
        seed=selected.seed,
        confidence=None if cfg is None else cfg.confidence,
    )

    return ResolvedRiskRunSpec(
        historical_dataset_id=dataset_id,
        historical_dataset_version=dataset_version,
        as_of=typed.as_of,
        calculation_config=cfg or factory_config,
    )


def request_blob_for_execute(run: RiskRun) -> dict[str, Any]:
    """Build the execute request: first-class columns override the request blob.

    R0.8.5: persisted ``historical_dataset_id`` / version / ``as_of`` /
    ``calculation_config`` are the source of truth when present so a tampered or
    emptied request JSON cannot silently rebind execution to the process engine.
    Legacy rows without columns still resolve from the request blob alone.
    """
    req = dict(run.request or {})
    if run.historical_dataset_id is not None:
        req["historical_dataset_id"] = run.historical_dataset_id
    if run.historical_dataset_version is not None:
        req["historical_dataset_version"] = run.historical_dataset_version
    if run.as_of is not None:
        req["as_of"] = as_of_wire(run.as_of)
    if run.calculation_config is not None:
        req["calculation_config"] = run.calculation_config.model_dump(mode="json")
    if run.methodology is not None and "methodology" not in req:
        req["methodology"] = run.methodology.value
    return req


def resolve_execute_spec(
    run: RiskRun,
    *,
    risk_engine: HistoricalRiskEngine | None = None,
) -> ResolvedRiskRunSpec:
    """Resolve the execute-time spec preferring persisted first-class columns.

    When ``run.historical_dataset_id`` is set, the resolved identity must match
    that column after canonicalization (fail closed on drift).
    """
    spec = resolve_run_spec(
        request_blob_for_execute(run),
        risk_engine=risk_engine,
        run_type=run.run_type,
    )
    stored_id = _nonempty_str(run.historical_dataset_id)
    if stored_id is not None and spec.historical_dataset_id != stored_id:
        raise ValueError(
            "persisted historical_dataset_id does not match execute resolution: "
            f"stored={stored_id!r} resolved={spec.historical_dataset_id!r}"
        )
    stored_version = _nonempty_str(run.historical_dataset_version)
    if (
        stored_version is not None
        and spec.historical_dataset_version != stored_version
    ):
        raise ValueError(
            "persisted historical_dataset_version does not match execute resolution: "
            f"stored={stored_version!r} resolved={spec.historical_dataset_version!r}"
        )
    return spec


def _nonempty_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
