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
from app.market.snapshot import FixedMarketDataProvider
from app.pricing.factory import create_pricing_engine
from app.risk.factor_panel import factor_panel_from_dataset, truncate_factor_panel
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import (
    DEMO_HISTORICAL_DATASET_ID,
    FileHistoricalDataset,
    SyntheticHistoricalDataset,
    create_historical_dataset,
    file_csv_dataset_id,
)
from app.services.portfolio_service import PortfolioService

DEFAULT_HISTORICAL_DATASET_VERSION = "v1"
DEFAULT_HISTORICAL_PANEL_SEED = 7
SYNTHETIC_HISTORICAL_DATASET_ID = "synthetic-historical-factors"

_DATASET_SOURCE_BY_ID: dict[str, str] = {
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
    historical_dataset_id: str
    historical_dataset_version: str
    as_of: date | AsOfLabel | None = None
    calculation_config: RiskRunCalculationConfig | None = None


def resolve_dataset_source(historical_dataset_id: str) -> str:
    raw = historical_dataset_id.strip()
    if not raw:
        raise ValueError("historical_dataset_id must be non-empty when set")
    if raw.lower() == "file":
        raise ValueError(
            "ambiguous historical_dataset_id 'file'; provide a concrete CSV path or file:<absolute-path>"
        )
    aliased = _DATASET_SOURCE_BY_ID.get(raw) or _DATASET_SOURCE_BY_ID.get(raw.lower())
    if aliased is not None:
        return aliased
    path_raw = raw[len("file:") :] if raw.startswith("file:") else raw
    if raw.startswith("file:") and not path_raw.strip():
        raise ValueError("ambiguous historical_dataset_id 'file:'; provide file:<absolute-path> to an existing factor CSV")
    path = Path(path_raw).expanduser()
    if path.suffix.lower() == ".csv" or path.is_file():
        if not path.is_file():
            raise ValueError(f"historical dataset CSV not found: {path}")
        return str(path.resolve())
    raise ValueError(
        f"unsupported historical_dataset_id: {historical_dataset_id!r}; use {DEMO_HISTORICAL_DATASET_ID!r}, {SYNTHETIC_HISTORICAL_DATASET_ID!r}, or a path to a factor CSV"
    )


def build_historical_risk_engine(*, historical_dataset_id: str | None = None, seed: int | None = None, observations: int | None = None) -> HistoricalRiskEngine:
    panel_seed = DEFAULT_HISTORICAL_PANEL_SEED if seed is None else seed
    dataset_kwargs: dict[str, Any] = {"seed": panel_seed}
    if observations is not None:
        dataset_kwargs["observations"] = observations
    if historical_dataset_id is not None:
        source = resolve_dataset_source(historical_dataset_id)
        dataset = create_historical_dataset(source, **dataset_kwargs)
    else:
        dataset = create_historical_dataset(**dataset_kwargs)
    panel = factor_panel_from_dataset(dataset, observations=observations, seed=panel_seed)
    return HistoricalRiskEngine(dataset=dataset, observations=panel.n_observations, seed=panel_seed, factor_panel=panel)


def build_portfolio_service(*, historical_dataset_id: str | None = None, seed: int | None = None, observations: int | None = None, market_data: Any | None = None) -> PortfolioService:
    engine = build_historical_risk_engine(historical_dataset_id=historical_dataset_id, seed=seed, observations=observations)
    if market_data is None:
        return PortfolioService(create_pricing_engine(), engine)
    return PortfolioService(create_pricing_engine(), engine, market_data=market_data)


def dataset_identity(dataset: object) -> tuple[str, str]:
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


def _copy_historical_engine(engine: HistoricalRiskEngine, *, observations: int, dataset: object, factor_panel: object) -> HistoricalRiskEngine:
    return HistoricalRiskEngine(seed=engine.seed, observations=observations, dataset=dataset, methodology=engine.methodology, scenario_kernel=engine.scenario_kernel, scenario_backend=engine.scenario_backend, factor_panel=factor_panel)  # type: ignore[arg-type]


def resize_historical_risk_engine(engine: HistoricalRiskEngine, observations: int) -> HistoricalRiskEngine:
    if observations == engine.observations:
        return engine
    if observations < 1:
        raise ValueError("observations must be >= 1")
    panel = engine.factor_panel
    dataset = engine.dataset
    factors = None if panel is None else panel.factors
    if panel is None:
        new_dataset = dataset
        if isinstance(dataset, SyntheticHistoricalDataset):
            new_dataset = replace(dataset, observations=observations)
        else:
            source_len = dataset.factor_observations().n_observations
            if observations > source_len:
                raise ValueError(f"observations {observations} exceeds historical dataset length {source_len}")
        return _copy_historical_engine(engine, observations=observations, dataset=new_dataset, factor_panel=None)
    if observations < panel.n_observations:
        new_panel = truncate_factor_panel(panel, observations)
        new_dataset = replace(dataset, observations=observations) if isinstance(dataset, SyntheticHistoricalDataset) else dataset
        return _copy_historical_engine(engine, observations=observations, dataset=new_dataset, factor_panel=new_panel)
    if isinstance(dataset, SyntheticHistoricalDataset):
        new_dataset = replace(dataset, observations=observations)
        new_panel = factor_panel_from_dataset(new_dataset, factors=factors, observations=observations, seed=engine.seed)
        return _copy_historical_engine(engine, observations=observations, dataset=new_dataset, factor_panel=new_panel)
    source_len = dataset.factor_observations().n_observations
    if observations > source_len:
        raise ValueError(f"observations {observations} exceeds historical dataset length {source_len}")
    new_panel = factor_panel_from_dataset(dataset, factors=factors, observations=observations, seed=engine.seed)
    return _copy_historical_engine(engine, observations=observations, dataset=dataset, factor_panel=new_panel)


def build_historical_risk_engine_for_spec(spec: ResolvedRiskRunSpec) -> HistoricalRiskEngine:
    cfg = spec.calculation_config
    return build_historical_risk_engine(
        historical_dataset_id=spec.historical_dataset_id,
        seed=None if cfg is None else cfg.seed,
        observations=None if cfg is None else cfg.observations,
    )


def _validate_market_as_of(spec: ResolvedRiskRunSpec, market: MarketSnapshot | None) -> None:
    """Fail closed when a durable run spec and its persisted snapshot disagree."""
    if market is None or spec.as_of is None:
        return
    spec_as_of = as_of_wire(spec.as_of)
    market_as_of = as_of_wire(market.as_of)
    if spec_as_of != market_as_of:
        raise ValueError(
            "risk run as_of does not match persisted market snapshot: "
            f"run={spec_as_of!r} snapshot={market_as_of!r}"
        )


def portfolio_service_for_spec(base: PortfolioService, spec: ResolvedRiskRunSpec, *, market: MarketSnapshot | None = None) -> PortfolioService:
    _validate_market_as_of(spec, market)
    market_data = FixedMarketDataProvider(market) if market is not None else base.market_data
    engine = getattr(base, "risk", None)
    if isinstance(engine, HistoricalRiskEngine):
        current_id, current_version = dataset_identity(engine.dataset)
        cfg = spec.calculation_config
        seed_ok = cfg is None or cfg.seed is None or cfg.seed == engine.seed
        obs_ok = cfg is None or cfg.observations is None or cfg.observations == engine.observations
        if current_id == spec.historical_dataset_id and current_version == spec.historical_dataset_version and seed_ok and obs_ok:
            if market is None:
                return base
            return PortfolioService(base.pricing, engine, market_data=market_data)
    rebound = build_historical_risk_engine_for_spec(spec)
    return PortfolioService(base.pricing, rebound, market_data=market_data)


def resolve_run_spec(request: dict[str, Any] | RiskRunRequestBody | None = None, *, risk_engine: HistoricalRiskEngine | None = None, run_type: str = "summary") -> ResolvedRiskRunSpec:
    typed = request if isinstance(request, RiskRunRequestBody) else parse_risk_run_request(run_type, request)
    req = dump_risk_run_request(typed)
    requested_id = _nonempty_str(req.get("historical_dataset_id"))
    requested_version = _nonempty_str(req.get("historical_dataset_version"))
    cfg = typed.calculation_config
    seed = None if cfg is None else cfg.seed
    observations = None if cfg is None else cfg.observations
    if requested_id is not None:
        resolve_dataset_source(requested_id)
        selected = build_historical_risk_engine(historical_dataset_id=requested_id, seed=seed, observations=observations)
    elif risk_engine is not None:
        selected = risk_engine
        if seed is not None or observations is not None:
            current_id, _ = dataset_identity(risk_engine.dataset)
            selected = build_historical_risk_engine(
                historical_dataset_id=current_id,
                seed=seed if seed is not None else risk_engine.seed,
                observations=observations if observations is not None else risk_engine.observations,
            )
    else:
        selected = build_historical_risk_engine(seed=seed, observations=observations)
    dataset_id, dataset_version = dataset_identity(selected.dataset)
    if requested_version is not None and requested_version != dataset_version:
        raise ValueError(f"unsupported historical_dataset_version: {requested_version!r}; expected {dataset_version!r}")
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


def resolve_execute_spec(run: RiskRun, *, risk_engine: HistoricalRiskEngine | None = None) -> ResolvedRiskRunSpec:
    spec = resolve_run_spec(request_blob_for_execute(run), risk_engine=risk_engine, run_type=run.run_type)
    stored_id = _nonempty_str(run.historical_dataset_id)
    if stored_id is not None and spec.historical_dataset_id != stored_id:
        raise ValueError(
            "persisted historical_dataset_id does not match execute resolution: "
            f"stored={stored_id!r} resolved={spec.historical_dataset_id!r}"
        )
    stored_version = _nonempty_str(run.historical_dataset_version)
    if stored_version is not None and spec.historical_dataset_version != stored_version:
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
