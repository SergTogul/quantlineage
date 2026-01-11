"""M5.2 RiskRun domain DTO validation and persistence mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain.models import (
    EquityPosition,
    MarketSnapshot,
    Portfolio,
    RiskResultRef,
    RiskRun,
    RiskRunStatus,
    VaRMethodology,
)
from app.persistence.risk_run_mapping import apply_risk_run_to_row, risk_run_to_row, row_to_risk_run
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.persistence.testing import make_sqlite_session_factory

UTC = UTC


def _ts(hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 9, 2, hour, minute, tzinfo=UTC)


def test_risk_run_status_values():
    assert {s.value for s in RiskRunStatus} == {
        "QUEUED",
        "RUNNING",
        "COMPLETED",
        "FAILED",
    }


def test_queued_risk_run_defaults():
    run = RiskRun(id="run-1", portfolio_id="p-1")
    assert run.status == RiskRunStatus.QUEUED
    assert run.duration is None
    assert run.result_refs == []
    assert run.scenario_set == []
    assert run.methodology is None
    assert run.error is None


def test_duration_computed_from_timestamps():
    start = _ts(12, 0)
    end = start + timedelta(seconds=45.5)
    run = RiskRun(
        id="run-1",
        portfolio_id="p-1",
        status=RiskRunStatus.COMPLETED,
        started_at=start,
        completed_at=end,
        methodology=VaRMethodology.DELTA_GAMMA,
        pricing_engine_version="builtin-1.0",
        scenario_set=["scn-a", "scn-b"],
        result_refs=[RiskResultRef(result_type="summary", result_id=7)],
    )
    assert run.duration == pytest.approx(45.5)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"id": " ", "portfolio_id": "p"}, "id must be non-empty"),
        ({"id": "r", "portfolio_id": " "}, "portfolio_id must be non-empty"),
        (
            {
                "id": "r",
                "portfolio_id": "p",
                "status": RiskRunStatus.QUEUED,
                "started_at": _ts(),
            },
            "QUEUED runs must not have started_at",
        ),
        (
            {
                "id": "r",
                "portfolio_id": "p",
                "status": RiskRunStatus.RUNNING,
            },
            "RUNNING runs require started_at",
        ),
        (
            {
                "id": "r",
                "portfolio_id": "p",
                "status": RiskRunStatus.COMPLETED,
                "started_at": _ts(),
            },
            "COMPLETED runs require started_at and completed_at",
        ),
        (
            {
                "id": "r",
                "portfolio_id": "p",
                "status": RiskRunStatus.FAILED,
                "started_at": _ts(),
                "completed_at": _ts(12, 1),
            },
            "FAILED runs require a non-empty error",
        ),
        (
            {
                "id": "r",
                "portfolio_id": "p",
                "status": RiskRunStatus.COMPLETED,
                "started_at": _ts(12, 2),
                "completed_at": _ts(12, 1),
            },
            "completed_at must be >= started_at",
        ),
        (
            {
                "id": "r",
                "portfolio_id": "p",
                "scenario_set": ["ok", ""],
            },
            "scenario_set entries must be non-empty",
        ),
        (
            {
                "id": "r",
                "portfolio_id": "p",
                "pricing_engine_version": "  ",
            },
            "pricing_engine_version must be non-empty",
        ),
    ],
)
def test_risk_run_validation_rejects(kwargs, match):
    with pytest.raises(ValidationError, match=match):
        RiskRun(**kwargs)


def test_failed_run_requires_error_ok():
    run = RiskRun(
        id="run-f",
        portfolio_id="p-1",
        status=RiskRunStatus.FAILED,
        started_at=_ts(),
        completed_at=_ts(12, 1),
        error="pricing timeout",
    )
    assert run.error == "pricing timeout"
    assert run.duration == pytest.approx(60.0)


def test_orm_round_trip_mapping_aliases():
    run = RiskRun(
        id="run-m",
        portfolio_id="p-1",
        market_snapshot_id="snap-1",
        status=RiskRunStatus.COMPLETED,
        started_at=_ts(),
        completed_at=_ts(12, 1),
        pricing_engine_version="quantlib-1.36",
        methodology=VaRMethodology.FULL_REVALUATION,
        scenario_set=["eq-crash"],
        run_type="stress",
        request={"horizon": 1},
        result_refs=[],
    )
    row = risk_run_to_row(run)
    assert row.finished_at == run.completed_at
    assert row.error_message is None
    assert row.methodology == "FULL_REVALUATION"
    assert row.pricing_engine_version == "quantlib-1.36"
    assert row.scenario_set == ["eq-crash"]

    back = row_to_risk_run(row)
    assert back.completed_at == run.completed_at
    assert back.methodology == VaRMethodology.FULL_REVALUATION
    assert back.model_dump() == run.model_dump()


def test_apply_risk_run_to_row_updates_error_alias():
    run = RiskRun(
        id="run-e",
        portfolio_id="p-1",
        status=RiskRunStatus.FAILED,
        started_at=_ts(),
        completed_at=_ts(12, 1),
        error="boom",
    )
    row = risk_run_to_row(run)
    assert row.error_message == "boom"
    run2 = run.model_copy(update={"error": "boom2"})
    # FAILED validator still holds
    apply_risk_run_to_row(run2, row)
    assert row.error_message == "boom2"


@pytest.fixture
def session_factory():
    return make_sqlite_session_factory()


def test_risk_run_repository_domain_round_trip(session_factory):
    portfolio = Portfolio(
        id="p-run",
        name="Run Book",
        positions=[
            EquityPosition(type="equity", id="eq-1", symbol="AAPL", quantity=1, price=100.0)
        ],
    )
    snap = MarketSnapshot(id="snap-run", equity_spots={"AAPL": 100.0})
    queued = RiskRun(
        id="run-1",
        portfolio_id="p-run",
        market_snapshot_id="snap-run",
        pricing_engine_version="builtin-1.0",
        methodology=VaRMethodology.DELTA_GAMMA,
        scenario_set=["base"],
        run_type="summary",
        request={"confidence": 0.99},
    )
    with session_scope(session_factory) as session:
        SqlAlchemyPortfolioRepository(session).save(portfolio)
        SqlAlchemyMarketSnapshotRepository(session).save(snap)
        runs = SqlAlchemyRiskRunRepository(session)
        stored = runs.create(queued)
        assert stored.status == RiskRunStatus.QUEUED
        runs.set_status("run-1", RiskRunStatus.RUNNING)
        runs.add_result(
            "run-1",
            "summary",
            {"portfolio_id": "p-run", "var_99": 1234.5, "market_value": 100.0},
        )
        completed = runs.set_status("run-1", RiskRunStatus.COMPLETED)
        assert completed.status == RiskRunStatus.COMPLETED
        assert completed.duration is not None
        assert completed.duration >= 0.0
        assert completed.pricing_engine_version == "builtin-1.0"
        assert completed.methodology == VaRMethodology.DELTA_GAMMA
        assert completed.scenario_set == ["base"]
        assert len(completed.result_refs) == 1
        assert completed.result_refs[0].result_type == "summary"
        assert completed.result_refs[0].result_id is not None

    with session_scope(session_factory) as session:
        got = SqlAlchemyRiskRunRepository(session).get("run-1")
        assert got is not None
        assert got.status == RiskRunStatus.COMPLETED
        assert got.market_snapshot_id == "snap-run"
        payloads = SqlAlchemyRiskRunRepository(session).get_result_payloads("run-1")
        assert payloads is not None
        assert payloads["summary"]["var_99"] == pytest.approx(1234.5)


def test_risk_run_repository_failed_requires_error(session_factory):
    portfolio = Portfolio(
        id="p-fail",
        name="Fail Book",
        positions=[
            EquityPosition(type="equity", id="eq-1", symbol="AAPL", quantity=1, price=100.0)
        ],
    )
    with session_scope(session_factory) as session:
        SqlAlchemyPortfolioRepository(session).save(portfolio)
        runs = SqlAlchemyRiskRunRepository(session)
        runs.create(RiskRun(id="run-f", portfolio_id="p-fail"))
        runs.set_status("run-f", RiskRunStatus.RUNNING)
        with pytest.raises(ValueError, match="non-empty error"):
            runs.set_status("run-f", RiskRunStatus.FAILED)
        failed = runs.set_status("run-f", RiskRunStatus.FAILED, error="engine crash")
        assert failed.status == RiskRunStatus.FAILED
        assert failed.error == "engine crash"
