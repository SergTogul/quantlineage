"""R0.8.5 — Postgres RiskRun lifecycle + same-spec parity (live DSN optional).

Skip/fail rules match ``test_postgres_two_worker.py`` so PR ``backend-pytest``
stays green without Postgres. When a reachable postgresql DSN is available
(nightly / local docker), covers:

- save/load portfolio + run create
- worker claim + status lifecycle (QUEUED → RUNNING → COMPLETED)
- failed run
- portfolio identity protection on execute
- same-spec interactive vs worker numerical parity (summary)

Two-worker SKIP LOCKED claim remains in ``test_postgres_two_worker.py``.
"""
from __future__ import annotations

import time
from uuid import uuid4

import pytest

from app.domain.models import EquityPosition, Portfolio, RiskRunStatus
from app.persistence.session import (
    create_engine_from_url,
    create_session_factory,
    session_scope,
)
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.risk.historical_data import DEMO_HISTORICAL_DATASET_ID
from app.services.risk_factories import (
    SYNTHETIC_HISTORICAL_DATASET_ID,
    build_portfolio_service,
    dataset_identity,
    portfolio_service_for_spec,
    resolve_run_spec,
)
from app.services.risk_run_worker import RiskRunWorker, execute_run_type
from tests.market_fixtures import FixedMarketProvider, equity_spot_market
from tests.test_postgres_two_worker import require_live_postgres


def _factory():
    engine = create_engine_from_url(require_live_postgres(), echo=False)
    # Ensure schema exists for local docker without requiring alembic migrate.
    from app.persistence.base import Base
    from app.persistence import models as _models  # noqa: F401

    Base.metadata.create_all(engine)
    return create_session_factory(engine=engine)


def _market():
    return FixedMarketProvider(equity_spot_market("NVDA", 190.0))


def _book(suffix: str) -> Portfolio:
    pid = f"pg-r085-{suffix}-{uuid4().hex[:10]}"
    return Portfolio(
        id=pid,
        name=f"PG R085 {suffix}",
        positions=[
            EquityPosition(type="equity", id=f"{pid}-eq", symbol="NVDA", quantity=10),
        ],
    )


def _wait_worker(worker: RiskRunWorker, run_id: str, *, timeout_s: float = 45.0):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = worker.get(run_id)
        if last.status in {RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish; last={last}")


def test_postgres_save_load_run_create_claim_complete_lifecycle():
    factory = _factory()
    book = _book("life")
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).create(book)
        loaded = SqlAlchemyPortfolioRepository(session).get(book.id)
        assert loaded is not None
        assert loaded.name == book.name
        assert [p.symbol for p in loaded.positions] == ["NVDA"]

    svc = build_portfolio_service(
        historical_dataset_id=SYNTHETIC_HISTORICAL_DATASET_ID,
        market_data=_market(),
    )
    worker = RiskRunWorker(svc, session_factory=factory, max_workers=1)
    try:
        accepted = worker.submit(
            portfolio=book,
            run_type="summary",
            request={
                "methodology": "DELTA_GAMMA",
                "historical_dataset_id": SYNTHETIC_HISTORICAL_DATASET_ID,
                "calculation_config": {"observations": 250, "seed": 7},
            },
            execute=False,
        )
        assert accepted.status == RiskRunStatus.QUEUED
        assert accepted.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
        with session_scope(factory) as session:
            stored = SqlAlchemyRiskRunRepository(session).get(accepted.id)
            assert stored is not None
            assert stored.status == RiskRunStatus.QUEUED
            assert stored.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
        assert worker.poll_once(limit=5) == 1
        done = _wait_worker(worker, accepted.id)
    finally:
        worker.shutdown(wait=True)

    assert done.status == RiskRunStatus.COMPLETED, done.error_message
    assert done.started_at is not None
    assert done.finished_at is not None
    assert done.duration_seconds is not None
    assert done.results[0].result_type == "summary"
    with session_scope(factory) as session:
        terminal = SqlAlchemyRiskRunRepository(session).get(accepted.id)
        assert terminal is not None
        assert terminal.status == RiskRunStatus.COMPLETED


def test_postgres_failed_run_lifecycle():
    """Missing portfolio after claim → FAILED (poll path)."""
    factory = _factory()
    book = _book("fail")
    svc = build_portfolio_service(market_data=_market())
    worker = RiskRunWorker(svc, session_factory=factory, max_workers=1)
    try:
        accepted = worker.submit(
            portfolio=book,
            run_type="summary",
            request={"methodology": "DELTA_GAMMA"},
            execute=False,
        )
        with session_scope(factory) as session:
            assert SqlAlchemyPortfolioRepository(session).delete(book.id)
        with worker._portfolios_lock:
            worker._portfolios.pop(accepted.id, None)
        # claim_queued → RUNNING, then fail for missing book (no schedule).
        assert worker.poll_once(limit=5) == 0
        view = worker.get(accepted.id)
    finally:
        worker.shutdown(wait=True)

    assert view.status == RiskRunStatus.FAILED
    assert view.error_message
    with session_scope(factory) as session:
        stored = SqlAlchemyRiskRunRepository(session).get(accepted.id)
        assert stored is not None
        assert stored.status == RiskRunStatus.FAILED
        assert stored.error


def test_postgres_same_spec_interactive_matches_worker():
    factory = _factory()
    book = _book("parity")
    request = {
        "methodology": "DELTA_GAMMA",
        "historical_dataset_id": SYNTHETIC_HISTORICAL_DATASET_ID,
        "calculation_config": {"observations": 250, "seed": 7},
    }
    base = build_portfolio_service(
        historical_dataset_id=DEMO_HISTORICAL_DATASET_ID,
        market_data=_market(),
    )
    spec = resolve_run_spec(request, risk_engine=base.risk, run_type="summary")
    assert spec.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
    interactive_svc = portfolio_service_for_spec(base, spec)
    used_id, _ = dataset_identity(interactive_svc.risk.dataset)
    assert used_id == SYNTHETIC_HISTORICAL_DATASET_ID
    interactive = execute_run_type(
        interactive_svc, run_type="summary", portfolio=book, request=request
    )

    worker = RiskRunWorker(base, session_factory=factory, max_workers=1)
    try:
        accepted = worker.submit(
            portfolio=book, run_type="summary", request=request, execute=False
        )
        assert accepted.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
        assert worker.poll_once(limit=5) == 1
        done = _wait_worker(worker, accepted.id)
    finally:
        worker.shutdown(wait=True)

    assert done.status == RiskRunStatus.COMPLETED, done.error_message
    assert done.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
    assert done.results[0].payload == interactive


def test_postgres_portfolio_identity_execute_uses_stored_book():
    factory = _factory()
    suffix = uuid4().hex[:8]
    stored = Portfolio(
        id=f"pg-ident-{suffix}",
        name="Stored",
        positions=[
            EquityPosition(
                type="equity", id=f"eq-kept-{suffix}", symbol="NVDA", quantity=25
            ),
        ],
    )
    posted = Portfolio(
        id=stored.id,
        name="Attacker",
        positions=[
            EquityPosition(
                type="equity", id=f"eq-wipe-{suffix}", symbol="NVDA", quantity=1
            ),
        ],
    )
    request = {
        "methodology": "DELTA_GAMMA",
        "historical_dataset_id": SYNTHETIC_HISTORICAL_DATASET_ID,
        "calculation_config": {"observations": 250, "seed": 7},
    }
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).create(stored)

    base = build_portfolio_service(
        historical_dataset_id=DEMO_HISTORICAL_DATASET_ID,
        market_data=_market(),
    )
    spec = resolve_run_spec(request, risk_engine=base.risk, run_type="summary")
    expected = execute_run_type(
        portfolio_service_for_spec(base, spec),
        run_type="summary",
        portfolio=stored,
        request=request,
    )
    attacker = execute_run_type(
        portfolio_service_for_spec(base, spec),
        run_type="summary",
        portfolio=posted,
        request=request,
    )
    assert expected != attacker

    api = RiskRunWorker(base, session_factory=factory, max_workers=1)
    try:
        accepted = api.submit(
            portfolio=posted, run_type="summary", request=request, execute=False
        )
    finally:
        api.shutdown(wait=False)

    drain = RiskRunWorker(base, session_factory=factory, max_workers=1)
    try:
        assert drain.poll_once(limit=5) == 1
        done = _wait_worker(drain, accepted.id)
    finally:
        drain.shutdown(wait=True)

    assert done.status == RiskRunStatus.COMPLETED, done.error_message
    assert done.results[0].payload == expected
    assert done.results[0].payload != attacker
    with session_scope(factory) as session:
        loaded = SqlAlchemyPortfolioRepository(session).get(stored.id)
        assert loaded is not None
        assert loaded.name == "Stored"
        assert loaded.positions[0].quantity == 25
