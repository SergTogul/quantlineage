"""R0.8.7 / RF-013 cell 4: persisted risk_results.payload is typed per result_type."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models import (
    EquityPosition,
    Portfolio,
    RiskRun,
    RiskRunStatus,
    RiskSummary,
    VaRMethodology,
)
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.persistence.testing import make_sqlite_session_factory
from app.services.risk_run_service import RiskRunService


def _summary_payload(**overrides: object) -> dict:
    payload = RiskSummary(
        portfolio_id="p-payload",
        market_value=100.0,
        delta=1.0,
        gamma=0.0,
        vega=0.0,
        dv01=0.0,
        fx_delta=0.0,
        var_95=50.0,
        var_99=80.0,
        expected_shortfall_99=90.0,
        methodology=VaRMethodology.DELTA_GAMMA,
    ).model_dump(mode="json")
    payload.update(overrides)
    return payload


def _seed_sql_run(session, *, run_id: str = "run-payload") -> SqlAlchemyRiskRunRepository:
    SqlAlchemyPortfolioRepository(session).save(
        Portfolio(
            id="p-payload",
            name="Payload Book",
            positions=[EquityPosition(type="equity", id="eq-1", symbol="NVDA", quantity=1)],
        )
    )
    runs = SqlAlchemyRiskRunRepository(session)
    runs.create(RiskRun(id=run_id, portfolio_id="p-payload", run_type="summary"))
    runs.set_status(run_id, RiskRunStatus.RUNNING)
    return runs


def test_unknown_result_type_fails_closed_on_sqlalchemy_add_result() -> None:
    factory = make_sqlite_session_factory()
    with session_scope(factory) as session:
        runs = _seed_sql_run(session)
        with pytest.raises(ValueError, match="unknown result_type"):
            runs.add_result("run-payload", "not-a-real-type", _summary_payload())
        assert runs.get_result_payloads("run-payload") == {}


def test_unknown_result_type_fails_closed_on_memory_add_result() -> None:
    repo = InMemoryRiskRunRepository()
    svc = RiskRunService(repo)
    svc.enqueue(run_id="mem-unknown", portfolio_id="p-payload")
    svc.start("mem-unknown")
    with pytest.raises(ValueError, match="unknown result_type"):
        repo.add_result("mem-unknown", "mystery", _summary_payload())
    assert svc.get_result_payloads("mem-unknown") == {}


def test_extra_keys_fail_on_sqlalchemy_add_result() -> None:
    factory = make_sqlite_session_factory()
    with session_scope(factory) as session:
        runs = _seed_sql_run(session)
        with pytest.raises((ValidationError, ValueError)):
            runs.add_result(
                "run-payload",
                "summary",
                _summary_payload(unexpected_blob=1),
            )
        assert runs.get_result_payloads("run-payload") == {}


def test_extra_keys_fail_on_complete() -> None:
    repo = InMemoryRiskRunRepository()
    svc = RiskRunService(repo)
    svc.enqueue(run_id="mem-extra", portfolio_id="p-payload")
    svc.start("mem-extra")
    with pytest.raises((ValidationError, ValueError)):
        svc.complete(
            "mem-extra",
            result_type="summary",
            payload=_summary_payload(rogue=True),
        )
    got = svc.get("mem-extra")
    assert got.status == RiskRunStatus.RUNNING
    assert svc.get_result_payloads("mem-extra") == {}


def test_known_summary_payload_round_trips_sqlalchemy() -> None:
    payload = _summary_payload()
    factory = make_sqlite_session_factory()
    with session_scope(factory) as session:
        runs = _seed_sql_run(session)
        runs.add_result("run-payload", "summary", payload)
        runs.set_status("run-payload", RiskRunStatus.COMPLETED)
    with session_scope(factory) as session:
        stored = SqlAlchemyRiskRunRepository(session).get_result_payloads("run-payload")
        assert stored is not None
        assert stored["summary"]["var_99"] == pytest.approx(80.0)
        assert stored["summary"]["portfolio_id"] == "p-payload"
        RiskSummary.model_validate(stored["summary"])


def test_known_summary_payload_round_trips_via_complete() -> None:
    payload = _summary_payload()
    repo = InMemoryRiskRunRepository()
    svc = RiskRunService(repo)
    svc.enqueue(run_id="mem-ok", portfolio_id="p-payload")
    svc.start("mem-ok")
    done = svc.complete("mem-ok", result_type="summary", payload=payload)
    assert done.status == RiskRunStatus.COMPLETED
    stored = svc.get_result_payloads("mem-ok")["summary"]
    assert stored["var_99"] == pytest.approx(80.0)
    assert stored["market_value"] == pytest.approx(100.0)
    RiskSummary.model_validate(stored)


def test_payload_schemas_cover_supported_run_types() -> None:
    from app.persistence.result_payloads import RISK_RESULT_PAYLOAD_SCHEMAS
    from app.services.risk_run_worker import SUPPORTED_RUN_TYPES

    assert set(SUPPORTED_RUN_TYPES) == set(RISK_RESULT_PAYLOAD_SCHEMAS)


@pytest.mark.parametrize("run_type", ["summary", "var", "stress", "factors", "dashboard"])
def test_execute_run_type_payload_validates(run_type: str) -> None:
    from tests.market_fixtures import FixedMarketProvider, equity_spot_market

    from app.persistence.result_payloads import parse_result_payload
    from app.pricing.factory import create_pricing_engine
    from app.risk.historical import HistoricalRiskEngine
    from app.services.portfolio_service import PortfolioService
    from app.services.risk_run_worker import execute_run_type

    book = Portfolio(
        id="p-payload",
        name="Payload Book",
        positions=[EquityPosition(type="equity", id="eq-1", symbol="NVDA", quantity=1)],
    )
    service = PortfolioService(
        create_pricing_engine(),
        HistoricalRiskEngine(seed=1, observations=8),
        market_data=FixedMarketProvider(equity_spot_market("NVDA", 190.0)),
    )
    payload = execute_run_type(service, run_type=run_type, portfolio=book, request={})
    stored = parse_result_payload(run_type, payload)
    assert stored == payload
