"""M5.4 async risk-run APIs: POST/GET /risk/runs (+ /api/v1/risk/runs alias)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.domain.models import EquityPosition, Portfolio, RiskRunStatus
from app.main import app
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.persistence.testing import make_sqlite_session_factory
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.services.portfolio_service import PortfolioService
from app.services.risk_run_service import RiskRunService
from app.services.risk_run_worker import (
    SUPPORTED_RUN_TYPES,
    RiskRunWorker,
    execute_run_type,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tiny_portfolio() -> Portfolio:
    return Portfolio(
        id="async-book",
        name="Async Book",
        positions=[
            EquityPosition(
                type="equity", id="eq-1", symbol="AAPL", quantity=10, price=100.0
            )
        ],
    )


def _wait_terminal(client: TestClient, run_id: str, *, timeout_s: float = 30.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        resp = client.get(f"/risk/runs/{run_id}")
        assert resp.status_code == 200
        last = resp.json()
        if last["status"] in {RiskRunStatus.COMPLETED.value, RiskRunStatus.FAILED.value}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish; last={last}")


def test_create_returns_202_queued(client, tiny_portfolio):
    resp = client.post(
        "/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "summary",
            "request": {"methodology": "DELTA_GAMMA"},
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "QUEUED"
    assert body["portfolio_id"] == "async-book"
    assert body["run_type"] == "summary"
    assert body["id"]
    assert body["results"] == []


def test_poll_until_completed_with_summary_result(client, tiny_portfolio):
    created = client.post(
        "/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "summary",
            "request": {"methodology": "DELTA_GAMMA"},
        },
    )
    assert created.status_code == 202
    run_id = created.json()["id"]
    done = _wait_terminal(client, run_id)
    assert done["status"] == "COMPLETED"
    assert done["error_message"] is None
    assert done["started_at"] is not None
    assert done["finished_at"] is not None
    assert done["duration_seconds"] is not None
    assert done["duration_seconds"] >= 0.0
    assert len(done["results"]) == 1
    assert done["results"][0]["result_type"] == "summary"
    assert done["results"][0]["payload"]["portfolio_id"] == "async-book"


def test_api_v1_alias_matches_unversioned(client, tiny_portfolio):
    created = client.post(
        "/api/v1/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "var",
            "request": {"methodology": "LINEAR"},
        },
    )
    assert created.status_code == 202
    run_id = created.json()["id"]
    done = _wait_terminal(client, run_id)
    assert done["status"] == "COMPLETED"
    assert done["run_type"] == "var"
    via_v1 = client.get(f"/api/v1/risk/runs/{run_id}")
    assert via_v1.status_code == 200
    assert via_v1.json()["status"] == "COMPLETED"


def test_get_missing_run_404(client):
    resp = client.get("/risk/runs/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "not_found"
    assert "not found" in body["message"].lower()


def test_unsupported_run_type_400(client, tiny_portfolio):
    resp = client.post(
        "/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "not-a-real-type",
        },
    )
    assert resp.status_code == 400
    assert "unsupported run_type" in resp.json()["message"]


def test_validation_rejects_empty_run_type(client, tiny_portfolio):
    resp = client.post(
        "/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "",
        },
    )
    assert resp.status_code == 422


def test_worker_fails_run_on_execution_error(tiny_portfolio):
    class BoomService:
        def summary(self, portfolio, methodology=None):
            raise RuntimeError("boom")

    repo = InMemoryRiskRunRepository()
    worker = RiskRunWorker(BoomService(), repo=repo, max_workers=1)  # type: ignore[arg-type]
    view = worker.submit(portfolio=tiny_portfolio, run_type="summary")
    run_id = view.id
    deadline = time.time() + 10.0
    last = None
    while time.time() < deadline:
        last = worker.get(run_id)
        if last.status in {RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}:
            break
        time.sleep(0.05)
    worker.shutdown(wait=True)
    assert last is not None
    assert last.status == RiskRunStatus.FAILED
    assert "boom" in (last.error_message or "")


def test_execute_run_type_dispatch(tiny_portfolio):
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    for run_type in sorted(SUPPORTED_RUN_TYPES):
        payload = execute_run_type(
            svc,
            run_type=run_type,
            portfolio=tiny_portfolio,
            request={"methodology": "DELTA_GAMMA"},
        )
        assert isinstance(payload, dict)


def test_worker_with_sqlalchemy_session_factory(tiny_portfolio, tmp_path):
    """Persistence wiring path: SQLAlchemy repo + RiskRunService lifecycle."""
    # File DB so worker threads share the same SQLite store (memory DBs do not).
    url = f"sqlite:///{tmp_path / 'risk_runs.db'}"
    factory = make_sqlite_session_factory(url)
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).save(tiny_portfolio)

    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, session_factory=factory, max_workers=1)
    view = worker.submit(portfolio=tiny_portfolio, run_type="summary")
    run_id = view.id
    deadline = time.time() + 30.0
    last = None
    while time.time() < deadline:
        last = worker.get(run_id)
        if last.status in {RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}:
            break
        time.sleep(0.05)
    worker.shutdown(wait=True)
    assert last is not None
    assert last.status == RiskRunStatus.COMPLETED, (
        f"expected COMPLETED, got {last.status}: {last.error_message}"
    )
    assert last.results[0].result_type == "summary"

    with session_scope(factory) as session:
        stored = SqlAlchemyRiskRunRepository(session).get(run_id)
        assert stored is not None
        assert stored.status == RiskRunStatus.COMPLETED
        payloads = SqlAlchemyRiskRunRepository(session).get_result_payloads(run_id)
        assert payloads is not None
        assert "summary" in payloads


def test_in_memory_repo_status_enum_matches_service():
    repo = InMemoryRiskRunRepository()
    svc = RiskRunService(repo)
    queued = svc.enqueue(
        run_id="mem-1",
        portfolio_id="p",
        run_type="summary",
    )
    assert queued.status == RiskRunStatus.QUEUED
    running = svc.start("mem-1")
    assert running.status == RiskRunStatus.RUNNING
    done = svc.complete("mem-1", result_type="summary", payload={"ok": True})
    assert done.status == RiskRunStatus.COMPLETED
    assert svc.get_result_payloads("mem-1")["summary"]["ok"] is True
