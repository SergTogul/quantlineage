"""Map domain ``RiskRun`` ↔ ORM ``RiskRunRow`` (M5.2).

Field aliases:
- domain ``completed_at`` ↔ ORM ``finished_at``
- domain ``error`` ↔ ORM ``error_message``
- domain ``result_refs`` ↔ ``risk_results`` rows (type + id only)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.domain.models import (
    RiskResultRef,
    RiskRun,
    RiskRunStatus,
    VaRMethodology,
)
from app.persistence.models import RiskRunRow


def _parse_methodology(value: str | None) -> VaRMethodology | None:
    if value is None or value == "":
        return None
    return VaRMethodology(value)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize DB datetimes to timezone-aware UTC (SQLite often returns naive)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def row_to_risk_run(row: RiskRunRow) -> RiskRun:
    """Build a validated domain ``RiskRun`` from an ORM row (+ result children)."""
    refs = [
        RiskResultRef(result_type=r.result_type, result_id=r.id)
        for r in (row.results or [])
    ]
    return RiskRun(
        id=row.id,
        portfolio_id=row.portfolio_id,
        market_snapshot_id=row.market_snapshot_id,
        created_at=_as_utc(row.created_at) or datetime.now(timezone.utc),
        started_at=_as_utc(row.started_at),
        completed_at=_as_utc(row.finished_at),
        pricing_engine_version=row.pricing_engine_version,
        methodology=_parse_methodology(row.methodology),
        scenario_set=list(row.scenario_set or []),
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


def risk_run_to_row(run: RiskRun) -> RiskRunRow:
    """Allocate a new ORM row from a domain ``RiskRun`` (no result children)."""
    row = RiskRunRow(id=run.id)
    apply_risk_run_to_row(run, row)
    return row


def results_payload_map(row: RiskRunRow) -> dict[str, dict[str, Any]]:
    """Optional helper: ``result_type`` → payload for API envelopes."""
    return {r.result_type: dict(r.payload) for r in (row.results or [])}
