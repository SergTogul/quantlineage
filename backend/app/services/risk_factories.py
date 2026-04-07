"""Shared pricing + historical-dataset construction for API and worker (R0.8.2).

Both FastAPI deps and ``python -m app.worker`` must call
:func:`build_portfolio_service` so interactive and queued runs resolve the
same historical dataset and calculation knobs.

Does not close RF-009: portfolio persistence identity and typed run-request
schemas remain R0.8.3 / R0.8.4.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.domain.models import AsOf, AsOfLabel, RiskRunCalculationConfig
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import (
    DEMO_HISTORICAL_DATASET_ID,
    FileHistoricalDataset,
    SyntheticHistoricalDataset,
    create_historical_dataset,
)
from app.services.portfolio_service import PortfolioService

DEFAULT_HISTORICAL_DATASET_VERSION = "v1"
SYNTHETIC_HISTORICAL_DATASET_ID = "synthetic-historical-factors"

_AS_OF_ADAPTER: TypeAdapter[date | AsOfLabel] = TypeAdapter(AsOf)


@dataclass(frozen=True, slots=True)
class ResolvedRiskRunSpec:
    """Deterministic spec columns implied by the shared factory and/or request."""

    historical_dataset_id: str
    historical_dataset_version: str
    as_of: date | AsOfLabel | None = None
    calculation_config: RiskRunCalculationConfig | None = None


def build_historical_risk_engine() -> HistoricalRiskEngine:
    """Wire :class:`HistoricalRiskEngine` to :func:`create_historical_dataset`."""
    return HistoricalRiskEngine(dataset=create_historical_dataset())


def build_portfolio_service() -> PortfolioService:
    """Construct the process-wide pricing + historical risk stack.

    Used by FastAPI ``deps.portfolio_service`` and Compose ``app.worker``.
    """
    return PortfolioService(create_pricing_engine(), build_historical_risk_engine())


def dataset_identity(dataset: object) -> tuple[str, str]:
    """Stable id/version for a resolved historical dataset instance."""
    raw_id = getattr(dataset, "dataset_id", None)
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip(), DEFAULT_HISTORICAL_DATASET_VERSION
    if isinstance(dataset, FileHistoricalDataset):
        return DEMO_HISTORICAL_DATASET_ID, DEFAULT_HISTORICAL_DATASET_VERSION
    if isinstance(dataset, SyntheticHistoricalDataset):
        return SYNTHETIC_HISTORICAL_DATASET_ID, DEFAULT_HISTORICAL_DATASET_VERSION
    return SYNTHETIC_HISTORICAL_DATASET_ID, DEFAULT_HISTORICAL_DATASET_VERSION


def resolve_run_spec(
    request: dict[str, Any] | None = None,
    *,
    risk_engine: HistoricalRiskEngine | None = None,
) -> ResolvedRiskRunSpec:
    """Merge request-blob spec fields with the factory-resolved dataset/config.

    Request values win when present and valid. Unparseable ``as_of`` is omitted
    (the request dict is still an untyped envelope). Dataset identity always
    comes from the shared factory when the request does not supply one.
    """
    engine = risk_engine if risk_engine is not None else build_historical_risk_engine()
    dataset_id, dataset_version = dataset_identity(engine.dataset)
    factory_config = RiskRunCalculationConfig(
        observations=engine.observations,
        seed=engine.seed,
    )
    req = request or {}
    return ResolvedRiskRunSpec(
        historical_dataset_id=_nonempty_str(req.get("historical_dataset_id")) or dataset_id,
        historical_dataset_version=(
            _nonempty_str(req.get("historical_dataset_version")) or dataset_version
        ),
        as_of=_parse_as_of(req.get("as_of")),
        calculation_config=_parse_calculation_config(req.get("calculation_config"))
        or factory_config,
    )


def _nonempty_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_as_of(value: Any) -> date | AsOfLabel | None:
    if value is None or value == "":
        return None
    try:
        return _AS_OF_ADAPTER.validate_python(value)
    except (ValidationError, ValueError, TypeError):
        return None


def _parse_calculation_config(value: Any) -> RiskRunCalculationConfig | None:
    if value is None or value == "":
        return None
    if isinstance(value, RiskRunCalculationConfig):
        return value
    if not isinstance(value, Mapping):
        return None
    try:
        return RiskRunCalculationConfig.model_validate(value)
    except ValidationError:
        return None
