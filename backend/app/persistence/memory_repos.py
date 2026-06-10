"""In-memory repository backends for API / unit tests (no DB required).

``InMemoryRiskRunRepository`` implements the same ``RiskRunRepository`` contract
as SQLAlchemy so ``RiskRunService`` and M5.4 async APIs can run without Postgres.

``InMemoryMarketSnapshotRepository``, ``InMemoryScenarioDefinitionRepository``,
and ``InMemoryLimitDefinitionRepository`` mirror the SQLAlchemy repos so FastAPI
DI can serve the same contracts when ``RISKFORGE_DATABASE_URL`` is unset (M5.6).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Sequence

from app.domain.models import (
    MarketSnapshot,
    RiskLimit,
    RiskResultRef,
    RiskRun,
    RiskRunStatus,
    as_of_wire,
)
from app.persistence.repositories import (
    LimitDefinitionRepository,
    MarketSnapshotRepository,
    RiskRunRepository,
    ScenarioDefinitionRepository,
)
from app.persistence.result_payloads import parse_result_payload
from app.risk.scenario_model import Scenario


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class InMemoryMarketSnapshotRepository(MarketSnapshotRepository):
    """Thread-safe store mirroring ``SqlAlchemyMarketSnapshotRepository``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, MarketSnapshot] = {}
        self._meta: dict[str, dict[str, Any]] = {}

    def save(self, snapshot: MarketSnapshot, *, meta: dict[str, Any] | None = None) -> str:
        with self._lock:
            # MarketSnapshot freezes nested maps as mappingproxy; round-trip via JSON dump.
            stored = MarketSnapshot.model_validate(snapshot.model_dump(mode="json"))
            self._data[snapshot.id] = stored
            self._meta[snapshot.id] = {
                "id": snapshot.id,
                "as_of": as_of_wire(snapshot.as_of),
                "content_hash": snapshot.content_hash(),
                "meta": dict(meta or {}),
                "created_at": _utcnow().isoformat(),
            }
            return snapshot.id

    def get(self, snapshot_id: str) -> MarketSnapshot | None:
        with self._lock:
            row = self._data.get(snapshot_id)
            if row is None:
                return None
            return MarketSnapshot.model_validate(row.model_dump(mode="json"))

    def get_meta(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._lock:
            meta = self._meta.get(snapshot_id)
            return None if meta is None else dict(meta)


class InMemoryScenarioDefinitionRepository(ScenarioDefinitionRepository):
    """Thread-safe store mirroring ``SqlAlchemyScenarioDefinitionRepository``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: dict[str, Scenario] = {}

    def save(self, scenario: Scenario) -> Scenario:
        if not isinstance(scenario, Scenario):
            raise TypeError(f"scenario definitions store Scenario, got {type(scenario)!r}")
        scenario_id = scenario.id
        if not scenario_id:
            raise ValueError("scenario id required")
        with self._lock:
            self._rows[scenario_id] = scenario
            return scenario

    def get(self, scenario_id: str) -> Scenario | None:
        with self._lock:
            return self._rows.get(scenario_id)

    def list_all(self) -> list[Scenario]:
        with self._lock:
            return [r for r in sorted(self._rows.values(), key=lambda s: s.id)]

    def delete(self, scenario_id: str) -> bool:
        with self._lock:
            if scenario_id not in self._rows:
                return False
            del self._rows[scenario_id]
            return True


class InMemoryLimitDefinitionRepository(LimitDefinitionRepository):
    """Thread-safe store mirroring ``SqlAlchemyLimitDefinitionRepository``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # limit_id -> (portfolio_id, RiskLimit, active)
        self._rows: dict[str, tuple[str | None, RiskLimit, bool]] = {}

    def save(self, limit_id: str, limit: RiskLimit, *, portfolio_id: str | None = None) -> str:
        with self._lock:
            self._rows[limit_id] = (portfolio_id, limit.model_copy(deep=True), True)
            return limit_id

    def get(self, limit_id: str) -> RiskLimit | None:
        with self._lock:
            row = self._rows.get(limit_id)
            if row is None or not row[2]:
                return None
            return row[1].model_copy(deep=True)

    def list_for_portfolio(
        self, portfolio_id: str | None = None
    ) -> Sequence[tuple[str, RiskLimit]]:
        with self._lock:
            out: list[tuple[str, RiskLimit]] = []
            for lid, (pid, lim, active) in sorted(self._rows.items()):
                if not active:
                    continue
                if pid != portfolio_id:
                    continue
                out.append((lid, lim.model_copy(deep=True)))
            return out

    def delete(self, limit_id: str) -> bool:
        with self._lock:
            if limit_id not in self._rows:
                return False
            del self._rows[limit_id]
            return True


class InMemoryRiskRunRepository(RiskRunRepository):
    """Thread-safe store mirroring ``SqlAlchemyRiskRunRepository`` domain DTOs."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, RiskRun] = {}
        self._payloads: dict[str, dict[str, dict[str, Any]]] = {}
        self._next_result_id = 1

    def create(self, run: RiskRun) -> RiskRun:
        with self._lock:
            if run.id in self._runs:
                raise ValueError(f"risk run already exists: {run.id}")
            stored = run.model_copy(deep=True)
            self._runs[run.id] = stored
            self._payloads[run.id] = {}
            return stored.model_copy(deep=True)

    def set_status(
        self,
        run_id: str,
        status: RiskRunStatus,
        *,
        error: str | None = None,
    ) -> RiskRun:
        with self._lock:
            row = self._runs.get(run_id)
            if row is None:
                raise KeyError(f"risk run not found: {run_id}")
            started_at = row.started_at
            completed_at = row.completed_at
            err = row.error
            if status == RiskRunStatus.RUNNING and started_at is None:
                started_at = _utcnow()
            if status in {RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}:
                if started_at is None:
                    started_at = _as_utc(row.created_at) or _utcnow()
                completed_at = _utcnow()
            if status == RiskRunStatus.FAILED:
                if error is None or not str(error).strip():
                    raise ValueError("FAILED status requires a non-empty error")
                err = error
            elif status == RiskRunStatus.COMPLETED:
                err = None
            elif error is not None:
                err = error
            updated = row.model_copy(
                update={
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "status": status,
                    "error": err,
                }
            )
            self._runs[run_id] = updated
            return updated.model_copy(deep=True)

    def add_result(self, run_id: str, result_type: str, payload: dict[str, Any]) -> None:
        with self._lock:
            row = self._runs.get(run_id)
            if row is None:
                raise KeyError(f"risk run not found: {run_id}")
            typed = parse_result_payload(result_type, payload)
            payloads = self._payloads.setdefault(run_id, {})
            payloads[result_type] = typed
            refs = [r for r in row.result_refs if r.result_type != result_type]
            refs.append(
                RiskResultRef(result_type=result_type, result_id=self._next_result_id)
            )
            self._next_result_id += 1
            self._runs[run_id] = row.model_copy(update={"result_refs": refs})

    def get(self, run_id: str) -> RiskRun | None:
        with self._lock:
            row = self._runs.get(run_id)
            if row is None:
                return None
            return row.model_copy(deep=True)

    def get_result_payloads(self, run_id: str) -> dict[str, dict[str, Any]] | None:
        with self._lock:
            if run_id not in self._runs:
                return None
            return {k: dict(v) for k, v in self._payloads.get(run_id, {}).items()}

    def list_by_status(
        self,
        status: RiskRunStatus,
        *,
        limit: int = 50,
    ) -> list[RiskRun]:
        with self._lock:
            matched = [
                r.model_copy(deep=True)
                for r in self._runs.values()
                if r.status == status
            ]
        matched.sort(key=lambda r: (_as_utc(r.created_at) or datetime.min.replace(tzinfo=UTC), r.id))
        return matched[: max(0, int(limit))]

    def claim_queued(self, *, limit: int = 1) -> list[RiskRun]:
        """Claim QUEUED → RUNNING under the in-process RLock (FIFO)."""
        n = max(0, int(limit))
        if n == 0:
            return []
        with self._lock:
            matched = [r for r in self._runs.values() if r.status == RiskRunStatus.QUEUED]
            matched.sort(
                key=lambda r: (
                    _as_utc(r.created_at) or datetime.min.replace(tzinfo=UTC),
                    r.id,
                )
            )
            claimed: list[RiskRun] = []
            for run in matched[:n]:
                claimed.append(self.set_status(run.id, RiskRunStatus.RUNNING))
            return claimed
