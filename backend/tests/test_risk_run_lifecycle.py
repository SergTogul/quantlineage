"""M5.3 risk-run lifecycle: valid transitions, illegal rejects, duration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.models import EquityPosition, Portfolio, RiskRun, RiskRunStatus
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.persistence.testing import make_sqlite_session_factory
from app.services.risk_run_service import (
    ALLOWED_TRANSITIONS,
    InvalidRiskRunTransition,
    RiskRunNotFound,
    RiskRunService,
    assert_transition_allowed,
    can_transition,
    elapsed_seconds,
)


@pytest.fixture
def session_factory():
    return make_sqlite_session_factory()


def _seed_portfolio(session) -> None:
    SqlAlchemyPortfolioRepository(session).save(
        Portfolio(
            id="p-life",
            name="Lifecycle Book",
            positions=[
                EquityPosition(
                    type="equity", id="eq-1", symbol="AAPL", quantity=1, price=100.0
                )
            ],
        )
    )


# --- pure helpers (no DB) -------------------------------------------------


@pytest.mark.parametrize(
    "current,target,ok",
    [
        (RiskRunStatus.QUEUED, RiskRunStatus.RUNNING, True),
        (RiskRunStatus.RUNNING, RiskRunStatus.COMPLETED, True),
        (RiskRunStatus.RUNNING, RiskRunStatus.FAILED, True),
        (RiskRunStatus.QUEUED, RiskRunStatus.COMPLETED, False),
        (RiskRunStatus.QUEUED, RiskRunStatus.FAILED, False),
        (RiskRunStatus.QUEUED, RiskRunStatus.QUEUED, False),
        (RiskRunStatus.RUNNING, RiskRunStatus.QUEUED, False),
        (RiskRunStatus.RUNNING, RiskRunStatus.RUNNING, False),
        (RiskRunStatus.COMPLETED, RiskRunStatus.RUNNING, False),
        (RiskRunStatus.COMPLETED, RiskRunStatus.FAILED, False),
        (RiskRunStatus.COMPLETED, RiskRunStatus.QUEUED, False),
        (RiskRunStatus.FAILED, RiskRunStatus.RUNNING, False),
        (RiskRunStatus.FAILED, RiskRunStatus.QUEUED, False),
        (RiskRunStatus.FAILED, RiskRunStatus.COMPLETED, False),
    ],
)
def test_can_transition_matrix(current, target, ok):
    assert can_transition(current, target) is ok


def test_assert_transition_allowed_raises():
    with pytest.raises(InvalidRiskRunTransition, match="QUEUED → COMPLETED"):
        assert_transition_allowed(
            RiskRunStatus.QUEUED, RiskRunStatus.COMPLETED, run_id="r1"
        )


def test_terminal_states_have_no_outbound():
    assert ALLOWED_TRANSITIONS[RiskRunStatus.COMPLETED] == frozenset()
    assert ALLOWED_TRANSITIONS[RiskRunStatus.FAILED] == frozenset()


def test_elapsed_seconds_helpers():
    started = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(seconds=42.5)
    queued = RiskRun(id="q", portfolio_id="p", status=RiskRunStatus.QUEUED)
    assert elapsed_seconds(queued) is None

    running = RiskRun(
        id="r",
        portfolio_id="p",
        status=RiskRunStatus.RUNNING,
        started_at=started,
    )
    assert (
        elapsed_seconds(running, now=started + timedelta(seconds=10)) == 10.0
    )

    done = RiskRun(
        id="c",
        portfolio_id="p",
        status=RiskRunStatus.COMPLETED,
        started_at=started,
        completed_at=finished,
    )
    assert elapsed_seconds(done) == 42.5
    assert done.duration == 42.5


# --- service + persistence -------------------------------------------------


def test_happy_path_queued_running_completed(session_factory):
    with session_scope(session_factory) as session:
        _seed_portfolio(session)
        svc = RiskRunService(SqlAlchemyRiskRunRepository(session))
        queued = svc.enqueue(
            run_id="run-ok",
            portfolio_id="p-life",
            run_type="summary",
            request={"methodology": "delta_gamma"},
        )
        assert queued.status == RiskRunStatus.QUEUED
        assert queued.started_at is None
        assert queued.completed_at is None
        assert queued.duration is None
        assert elapsed_seconds(queued) is None

        running = svc.start("run-ok")
        assert running.status == RiskRunStatus.RUNNING
        assert running.started_at is not None
        assert running.completed_at is None
        assert elapsed_seconds(running) is not None
        assert elapsed_seconds(running) >= 0.0

        done = svc.complete(
            "run-ok",
            result_type="summary",
            payload={"var_99": 100.0},
        )
        assert done.status == RiskRunStatus.COMPLETED
        assert done.completed_at is not None
        assert done.duration is not None
        assert done.duration >= 0.0
        assert done.error is None
        assert done.result_refs[0].result_type == "summary"
        payloads = SqlAlchemyRiskRunRepository(session).get_result_payloads("run-ok")
        assert payloads is not None
        assert payloads["summary"]["var_99"] == 100.0


def test_happy_path_queued_running_failed(session_factory):
    with session_scope(session_factory) as session:
        _seed_portfolio(session)
        svc = RiskRunService(SqlAlchemyRiskRunRepository(session))
        svc.enqueue(run_id="run-fail", portfolio_id="p-life", run_type="var")
        svc.start("run-fail")
        failed = svc.fail("run-fail", "pricing engine unavailable")
        assert failed.status == RiskRunStatus.FAILED
        assert failed.error == "pricing engine unavailable"
        assert failed.completed_at is not None
        assert failed.duration is not None


@pytest.mark.parametrize(
    "setup,illegal_call",
    [
        ("queued", lambda svc: svc.complete("run-bad")),
        ("queued", lambda svc: svc.fail("run-bad", "nope")),
        ("running", lambda svc: svc.start("run-bad")),
        ("completed", lambda svc: svc.start("run-bad")),
        ("completed", lambda svc: svc.fail("run-bad", "late")),
        ("failed", lambda svc: svc.start("run-bad")),
        ("failed", lambda svc: svc.complete("run-bad")),
    ],
)
def test_illegal_transitions_raise(session_factory, setup, illegal_call):
    with session_scope(session_factory) as session:
        _seed_portfolio(session)
        svc = RiskRunService(SqlAlchemyRiskRunRepository(session))
        svc.enqueue(run_id="run-bad", portfolio_id="p-life", run_type="summary")
        if setup in {"running", "completed", "failed"}:
            svc.start("run-bad")
        if setup == "completed":
            svc.complete("run-bad")
        if setup == "failed":
            svc.fail("run-bad", "boom")

        with pytest.raises(InvalidRiskRunTransition):
            illegal_call(svc)


def test_fail_requires_error(session_factory):
    with session_scope(session_factory) as session:
        _seed_portfolio(session)
        svc = RiskRunService(SqlAlchemyRiskRunRepository(session))
        svc.enqueue(run_id="run-err", portfolio_id="p-life", run_type="summary")
        svc.start("run-err")
        with pytest.raises(ValueError, match="error is required"):
            svc.fail("run-err", "   ")


def test_get_missing_run_raises(session_factory):
    with session_scope(session_factory) as session:
        svc = RiskRunService(SqlAlchemyRiskRunRepository(session))
        with pytest.raises(RiskRunNotFound, match="missing"):
            svc.get("missing")


def test_complete_with_result_rejects_when_not_running(session_factory):
    with session_scope(session_factory) as session:
        _seed_portfolio(session)
        svc = RiskRunService(SqlAlchemyRiskRunRepository(session))
        svc.enqueue(run_id="run-early", portfolio_id="p-life", run_type="summary")
        with pytest.raises(InvalidRiskRunTransition):
            svc.complete(
                "run-early",
                result_type="summary",
                payload={"x": 1},
            )
        got = svc.get("run-early")
        assert got.status == RiskRunStatus.QUEUED
        assert got.result_refs == []
        payloads = SqlAlchemyRiskRunRepository(session).get_result_payloads("run-early")
        assert payloads == {}
