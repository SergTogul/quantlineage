"""M5.7: durable worker poll + claim_queued + external-worker enqueue deferral."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.domain.models import EquityPosition, Portfolio, RiskRun, RiskRunStatus
from app.persistence.config import external_worker_enabled
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
from app.services.risk_run_worker import RiskRunWorker


@pytest.fixture
def tiny_portfolio() -> Portfolio:
    return Portfolio(
        id="worker-book",
        name="Worker Book",
        positions=[
            EquityPosition(
                type="equity", id="eq-1", symbol="AAPL", quantity=10, price=100.0
            )
        ],
    )


def _wait_worker(worker: RiskRunWorker, run_id: str, *, timeout_s: float = 30.0):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = worker.get(run_id)
        if last.status in {RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish; last={last}")


def test_external_worker_env_flag(monkeypatch):
    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    assert external_worker_enabled() is False
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    assert external_worker_enabled() is True
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "true")
    assert external_worker_enabled() is True


def test_list_by_status_memory_fifo():
    repo = InMemoryRiskRunRepository()
    svc_portfolio = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc_portfolio, repo=repo, max_workers=1)
    a = worker.submit(portfolio=Portfolio(id="a", name="A", positions=[]), execute=False)
    b = worker.submit(portfolio=Portfolio(id="b", name="B", positions=[]), execute=False)
    queued = repo.list_by_status(RiskRunStatus.QUEUED, limit=10)
    assert [r.id for r in queued] == [a.id, b.id]
    worker.shutdown(wait=False)


def test_submit_execute_false_stays_queued_until_poll(tiny_portfolio, tmp_path):
    url = f"sqlite:///{tmp_path / 'm57_poll.db'}"
    factory = make_sqlite_session_factory(url)
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).save(tiny_portfolio)

    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    api_side = RiskRunWorker(svc, session_factory=factory, max_workers=1)
    view = api_side.submit(portfolio=tiny_portfolio, run_type="summary", execute=False)
    assert view.status == RiskRunStatus.QUEUED
    time.sleep(0.2)
    still = api_side.get(view.id)
    assert still.status == RiskRunStatus.QUEUED
    api_side.shutdown(wait=False)

    # Separate process simulation: new worker, empty in-memory portfolio cache.
    drain = RiskRunWorker(svc, session_factory=factory, max_workers=1)
    assert drain.poll_once(limit=5) == 1
    done = _wait_worker(drain, view.id)
    drain.shutdown(wait=True)
    assert done.status == RiskRunStatus.COMPLETED, done.error_message
    assert done.results[0].result_type == "summary"

    with session_scope(factory) as session:
        stored = SqlAlchemyRiskRunRepository(session).get(view.id)
        assert stored is not None
        assert stored.status == RiskRunStatus.COMPLETED


def test_submit_execute_true_returns_stable_queued_acceptance_snapshot(tiny_portfolio):
    """POST /risk/runs semantics: acceptance is stable even if execution starts fast."""
    repo = InMemoryRiskRunRepository()
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, repo=repo, max_workers=1)

    accepted = worker.submit(portfolio=tiny_portfolio, run_type="summary", execute=True)

    assert accepted.status == RiskRunStatus.QUEUED
    assert accepted.results == []
    done = _wait_worker(worker, accepted.id)
    worker.shutdown(wait=True)
    assert done.status == RiskRunStatus.COMPLETED, done.error_message
    assert done.results[0].result_type == "summary"


def test_external_worker_env_defers_execution(monkeypatch, tiny_portfolio, tmp_path):
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    url = f"sqlite:///{tmp_path / 'm57_ext.db'}"
    factory = make_sqlite_session_factory(url)
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, session_factory=factory, max_workers=1)
    view = worker.submit(portfolio=tiny_portfolio, run_type="var")
    time.sleep(0.2)
    assert worker.get(view.id).status == RiskRunStatus.QUEUED
    assert worker.poll_once() == 1
    done = _wait_worker(worker, view.id)
    worker.shutdown(wait=True)
    assert done.status == RiskRunStatus.COMPLETED


def test_poll_once_respects_batch_limit_and_leaves_excess_queued(tiny_portfolio):
    """Postgres/RQ-equivalent queue contract: FIFO claims are bounded by poll batch."""
    repo = InMemoryRiskRunRepository()
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, repo=repo, max_workers=1)
    accepted = [
        worker.submit(
            portfolio=tiny_portfolio.model_copy(update={"id": f"batch-book-{idx}"}),
            run_type="summary",
            execute=False,
        )
        for idx in range(3)
    ]

    assert worker.poll_once(limit=2) == 2

    queued = repo.list_by_status(RiskRunStatus.QUEUED, limit=10)
    worker.shutdown(wait=True)
    assert [run.id for run in queued] == [accepted[2].id]


def test_claim_queued_memory_exclusive_fifo():
    """Two claimers never get the same run; FIFO order preserved."""
    repo = InMemoryRiskRunRepository()
    svc = RiskRunService(repo)
    first = svc.enqueue(run_id="c1", portfolio_id="p", run_type="summary")
    second = svc.enqueue(run_id="c2", portfolio_id="p", run_type="summary")
    assert first.status == RiskRunStatus.QUEUED
    assert second.status == RiskRunStatus.QUEUED

    batch_a = repo.claim_queued(limit=1)
    batch_b = repo.claim_queued(limit=1)
    batch_c = repo.claim_queued(limit=1)

    assert [r.id for r in batch_a] == ["c1"]
    assert [r.id for r in batch_b] == ["c2"]
    assert batch_c == []
    assert batch_a[0].status == RiskRunStatus.RUNNING
    assert batch_b[0].status == RiskRunStatus.RUNNING
    assert repo.list_by_status(RiskRunStatus.QUEUED) == []


def test_claim_queued_sqlite_marks_running(tmp_path, tiny_portfolio):
    """SQLite has no SKIP LOCKED; claim still transitions QUEUED → RUNNING."""
    url = f"sqlite:///{tmp_path / 'm57_claim.db'}"
    factory = make_sqlite_session_factory(url)
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).save(tiny_portfolio)
        SqlAlchemyRiskRunRepository(session).create(
            RiskRun(
                id="sq-1",
                portfolio_id=tiny_portfolio.id,
                status=RiskRunStatus.QUEUED,
                run_type="summary",
            )
        )

    with session_scope(factory) as session:
        repo = SqlAlchemyRiskRunRepository(session)
        claimed = repo.claim_queued(limit=5)
        assert len(claimed) == 1
        assert claimed[0].id == "sq-1"
        assert claimed[0].status == RiskRunStatus.RUNNING
        assert claimed[0].started_at is not None
        assert repo.claim_queued(limit=5) == []


def test_claim_queued_postgres_dialect_uses_skip_locked():
    """Postgres-only path: SELECT ... FOR UPDATE SKIP LOCKED (mocked dialect).

    Live Postgres multi-worker proof remains M9.9 runner smoke; unit suite
    cannot assume a Postgres server, so we assert the SQLAlchemy statement
    options when dialect.name == 'postgresql'.
    """
    session = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    session.get_bind.return_value = bind

    captured: dict[str, object] = {}

    def _scalars(stmt):  # noqa: ANN001
        captured["stmt"] = stmt
        empty = MagicMock()
        empty.all.return_value = []
        return empty

    session.scalars.side_effect = _scalars
    repo = SqlAlchemyRiskRunRepository(session)
    assert repo.claim_queued(limit=3) == []

    stmt = captured["stmt"]
    for_update = getattr(stmt, "_for_update_arg", None)
    assert for_update is not None, "expected with_for_update on postgresql dialect"
    assert for_update.skip_locked is True


def test_claim_queued_sqlite_dialect_omits_skip_locked(tmp_path):
    """Non-Postgres dialects must not require SKIP LOCKED support."""
    url = f"sqlite:///{tmp_path / 'm57_dialect.db'}"
    factory = make_sqlite_session_factory(url)
    with session_scope(factory) as session:
        bind = session.get_bind()
        assert bind is not None
        assert bind.dialect.name == "sqlite"
        # Empty claim is enough: would raise if SKIP LOCKED were forced.
        assert SqlAlchemyRiskRunRepository(session).claim_queued(limit=1) == []
