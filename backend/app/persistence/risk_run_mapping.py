"""Map domain ``RiskRun`` ↔ ORM ``RiskRunRow`` (M5.2).

Field aliases:
- domain ``completed_at`` ↔ ORM ``finished_at``
- domain ``error`` ↔ ORM ``error_message``
- domain ``result_refs`` ↔ ``risk_results`` rows (type + id only)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import TypeAdapter

from app.domain.models import (
    AsOf,
    AsOfLabel,
    RiskResultRef,
    RiskRun,
    RiskRunCalculationConfig,
    RiskRunStatus,
    VaRMethodology,
    as_of_wire,
)
from app.persistence.models import RiskRunRow

_AS_OF_ADAPTER: TypeAdapter[AsOf] = TypeAdapter(AsOf)


def _parse_methodology(value: str | None) -> VaRMethodology | None:
    if value is None or value == "":
        return None
    return VaRMethodology(value)


def _parse_as_of(value: str | None) -> date | AsOfLabel | None:
    if value is None or value == "":
        return None
    return _AS_OF_ADAPTER.validate_python(value)


def _parse_calculation_config(
    value: dict[str, Any] | None,
) -> RiskRunCalculationConfig | None:
    if value is None or value == {}:
        return None
    return RiskRunCalculationConfig.model_validate(value)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize DB datetimes to timezone-aware UTC (SQLite often returns naive)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def row_to_risk_run(row: RiskRunRow) -> RiskRun:
    """Build a validated domain ``RiskRun`` from an ORM row (+ result children)."""
    refs = [
        RiskResultRef(result_type=r.result_type, result_id=r.id)
        for r in (row.results or [])
    ]
    return RiskRun(
        id=row.id,
        portfolio_id=row.portfolio_id,
        portfolio_version=row.portfolio_version,
        market_snapshot_id=row.market_snapshot_id,
        created_at=_as_utc(row.created_at) or datetime.now(UTC),
        started_at=_as_utc(row.started_at),
        completed_at=_as_utc(row.finished_at),
        pricing_engine_version=row.pricing_engine_version,
        methodology=_parse_methodology(row.methodology),
        scenario_set=list(row.scenario_set or []),
        historical_dataset_id=row.historical_dataset_id or None,
        historical_dataset_version=row.historical_dataset_version or None,
        as_of=_parse_as_of(row.as_of),
        calculation_config=_parse_calculation_config(row.calculation_config),
        status=row.status if isinstance(row.status, RiskRunStatus) else RiskRunStatus(row.status),
        result_refs=refs,
        error=row.error_message,
        run_type=row.run_type,
        request=dict(row.request or {}),
    )


def apply_risk_run_to_row(run: RiskRun, row: RiskRunRow) -> None:
    """Copy domain header fields onto an ORM row (does not sync result payloads)."""
    row.id = run.id
    row.portfolio_id = run.portfolio_id
    row.portfolio_version = run.portfolio_version
    row.market_snapshot_id = run.market_snapshot_id
    row.status = run.status
    row.run_type = run.run_type
    row.request = dict(run.request or {})
    row.error_message = run.error
    row.created_at = run.created_at
    row.started_at = run.started_at
    row.finished_at = run.completed_at
    row.pricing_engine_version = run.pricing_engine_version
    row.methodology = run.methodology.value if run.methodology is not None else None
    row.scenario_set = list(run.scenario_set or [])
    row.historical_dataset_id = run.historical_dataset_id
    row.historical_dataset_version = run.historical_dataset_version
    row.as_of = as_of_wire(run.as_of) if run.as_of is not None else None
    row.calculation_config = (
        run.calculation_config.model_dump() if run.calculation_config is not None else None
    )


def risk_run_to_row(run: RiskRun) -> RiskRunRow:
    """Allocate a new ORM row from a domain ``RiskRun`` (no result children)."""
    row = RiskRunRow(id=run.id)
    apply_risk_run_to_row(run, row)
    return row


def results_payload_map(row: RiskRunRow) -> dict[str, dict[str, Any]]:
    """Optional helper: ``result_type`` → payload for API envelopes."""
    return {r.result_type: dict(r.payload) for r in (row.results or [])}
