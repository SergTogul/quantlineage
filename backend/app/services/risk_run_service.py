"""Risk-run lifecycle service (M5.3).

Enforces ``QUEUED → RUNNING → COMPLETED | FAILED`` only. Persistence owns
storage and timestamp columns; this service owns transition rules.
Domain ``RiskRun.duration`` covers completed/failed elapsed time; for
``RUNNING`` runs ``elapsed_seconds`` reports live wall-clock duration.

No quant formulas live here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from app.domain.models import (
    AsOf,
    RiskRun,
    RiskRunCalculationConfig,
    RiskRunStatus,
    VaRMethodology,
)
from app.persistence.repositories import RiskRunRepository
from app.persistence.result_payloads import parse_result_payload

Clock = Callable[[], datetime]

# Directed edges only — terminal states have no outbound transitions.
ALLOWED_TRANSITIONS: Mapping[RiskRunStatus, frozenset[RiskRunStatus]] = {
    RiskRunStatus.QUEUED: frozenset({RiskRunStatus.RUNNING}),
    RiskRunStatus.RUNNING: frozenset({RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}),
    RiskRunStatus.COMPLETED: frozenset(),
    RiskRunStatus.FAILED: frozenset(),
}


class InvalidRiskRunTransition(ValueError):
    """Raised when a status change is not in the allowed lifecycle graph."""

    def __init__(
        self,
        run_id: str,
        current: RiskRunStatus,
        target: RiskRunStatus,
    ) -> None:
        self.run_id = run_id
        self.current = current
        self.target = target
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[current])
        super().__init__(
            f"illegal risk-run transition for {run_id}: "
            f"{current.value} → {target.value} "
            f"(allowed: {allowed or 'none'})"
        )


class RiskRunNotFound(KeyError):
    """Raised when a run id is missing from the repository."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"risk run not found: {run_id}")


def can_transition(current: RiskRunStatus, target: RiskRunStatus) -> bool:
    """Return True iff ``current → target`` is a valid lifecycle edge."""
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition_allowed(
    current: RiskRunStatus,
    target: RiskRunStatus,
    *,
    run_id: str = "<unknown>",
) -> None:
    if not can_transition(current, target):
        raise InvalidRiskRunTransition(run_id, current, target)


def parse_status(value: str | RiskRunStatus) -> RiskRunStatus:
    if isinstance(value, RiskRunStatus):
        return value
    return RiskRunStatus(value)


def elapsed_seconds(run: RiskRun, *, now: datetime | None = None) -> float | None:
    """Wall-clock elapsed seconds for any lifecycle state.

    Prefers domain ``RiskRun.duration`` when both timestamps exist (COMPLETED /
    FAILED). For ``RUNNING``, uses ``now - started_at``. ``QUEUED`` → ``None``.
    """
    if run.duration is not None:
        return max(0.0, float(run.duration))
    if run.status != RiskRunStatus.RUNNING or run.started_at is None:
        return None
    clock = now or datetime.now(UTC)
    started = run.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return max(0.0, (clock - started).total_seconds())


class RiskRunService:
    """Application service for risk-run create + lifecycle transitions."""

    def __init__(
        self,
        repo: RiskRunRepository,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repo = repo
        self._clock: Clock = clock or (lambda: datetime.now(UTC))

    def enqueue(
        self,
        *,
        run_id: str,
        portfolio_id: str,
        run_type: str = "summary",
        request: dict[str, Any] | None = None,
        market_snapshot_id: str | None = None,
        portfolio_version: int | None = None,
        pricing_engine_version: str | None = None,
        methodology: VaRMethodology | None = None,
        scenario_set: list[str] | None = None,
        historical_dataset_id: str | None = None,
        historical_dataset_version: str | None = None,
        as_of: AsOf | None = None,
        calculation_config: RiskRunCalculationConfig | None = None,
        owner: str | None = None,
    ) -> RiskRun:
        """Create a run in ``QUEUED``. Spec fields are optional (pre-R0.8.2 callers)."""
        run = RiskRun(
            id=run_id,
            portfolio_id=portfolio_id,
            portfolio_version=portfolio_version,
            owner=owner,
            market_snapshot_id=market_snapshot_id,
            pricing_engine_version=pricing_engine_version,
            methodology=methodology,
            scenario_set=list(scenario_set or []),
            historical_dataset_id=historical_dataset_id,
            historical_dataset_version=historical_dataset_version,
            as_of=as_of,
            calculation_config=calculation_config,
            status=RiskRunStatus.QUEUED,
            run_type=run_type,
            request=dict(request or {}),
        )
        return self._repo.create(run)

    def start(self, run_id: str) -> RiskRun:
        """QUEUED → RUNNING; repository sets ``started_at``."""
        return self._transition(run_id, RiskRunStatus.RUNNING)

    def complete(
        self,
        run_id: str,
        *,
        result_type: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RiskRun:
        """RUNNING → COMPLETED; optionally attach one result payload first."""
        if result_type is not None:
            if payload is None:
                raise ValueError("payload is required when result_type is set")
            current = self._require(run_id)
            assert_transition_allowed(
                current.status,
                RiskRunStatus.COMPLETED,
                run_id=run_id,
            )
            parse_result_payload(result_type, payload)
            self._repo.add_result(run_id, result_type, payload)
        return self._transition(run_id, RiskRunStatus.COMPLETED)

    def fail(self, run_id: str, error: str) -> RiskRun:
        """RUNNING → FAILED; requires a non-empty error."""
        message = (error or "").strip()
        if not message:
            raise ValueError("error is required when failing a risk run")
        return self._transition(run_id, RiskRunStatus.FAILED, error=message)

    def get(self, run_id: str) -> RiskRun:
        run = self._repo.get(run_id)
        if run is None:
            raise RiskRunNotFound(run_id)
        return run

    def get_result_payloads(self, run_id: str) -> dict[str, dict[str, Any]]:
        payloads = self._repo.get_result_payloads(run_id)
        if payloads is None:
            raise RiskRunNotFound(run_id)
        return payloads

    def _require(self, run_id: str) -> RiskRun:
        return self.get(run_id)

    def _transition(
        self,
        run_id: str,
        target: RiskRunStatus,
        *,
        error: str | None = None,
    ) -> RiskRun:
        current = self._require(run_id)
        assert_transition_allowed(current.status, target, run_id=run_id)
        try:
            return self._repo.set_status(run_id, target, error=error)
        except KeyError as exc:
            raise RiskRunNotFound(run_id) from exc
