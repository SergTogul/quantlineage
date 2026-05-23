"""R0.8.5 — same RiskRunSpec interactive vs worker numerical parity (RF-009).

Interactive/API-equivalent execution and worker execution of the same resolved
spec must yield identical deterministic results (demo/synthetic, exact floats).

Also proves execute prefers persisted first-class columns over a tampered
request blob, and that worker results use the run's stored dataset identity.
"""
from __future__ import annotations

import time
from typing import Any

import pytest
from tests.market_fixtures import FixedMarketProvider, equity_spot_market

from app.domain.models import EquityPosition, Portfolio, RiskRunStatus
from app.persistence.models import RiskRunRow
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import SqlAlchemyRiskRunRepository
from app.persistence.testing import make_sqlite_session_factory
from app.risk.historical_data import DEMO_HISTORICAL_DATASET_ID
from app.services.risk_factories import (
    SYNTHETIC_HISTORICAL_DATASET_ID,
    build_portfolio_service,
    dataset_identity,
    portfolio_service_for_spec,
    resolve_execute_spec,
    resolve_run_spec,
)
from app.services.risk_run_worker import RiskRunWorker, execute_run_type


def _book(portfolio_id: str = "parity-book") -> Portfolio:
    return Portfolio(
        id=portfolio_id,
        name="Parity Book",
        positions=[
            EquityPosition(type="equity", id="eq-1", symbol="NVDA", quantity=10),
        ],
    )


def _market():
    return FixedMarketProvider(equity_spot_market("NVDA", 190.0))


def _wait_worker(worker: RiskRunWorker, run_id: str, *, timeout_s: float = 30.0):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = worker.get(run_id)
        if last.status in {RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish; last={last}")


def _interactive_payload(
    *,
    run_type: str,
    portfolio: Portfolio,
    request: dict[str, Any],
    process_dataset_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """API-equivalent sync path: resolve spec → rebound service → execute_run_type."""
    base = build_portfolio_service(
        historical_dataset_id=process_dataset_id,
        market_data=_market(),
    )
    engine = base.risk
    spec = resolve_run_spec(request, risk_engine=engine, run_type=run_type)
    service = portfolio_service_for_spec(base, spec)
    used_id, _ = dataset_identity(service.risk.dataset)
    return (
        execute_run_type(service, run_type=run_type, portfolio=portfolio, request=request),
        used_id,
    )


@pytest.mark.parametrize("run_type", ["summary", "var"])
def test_same_spec_interactive_matches_worker_sqlite(run_type: str, tmp_path):
    """Exit criterion: same resolved spec → same numerical result (exact)."""
    portfolio = _book(f"parity-{run_type}")
    request = {
        "methodology": "DELTA_GAMMA",
        "historical_dataset_id": SYNTHETIC_HISTORICAL_DATASET_ID,
        "calculation_config": {"observations": 250, "seed": 7},
    }
    interactive, interactive_dataset = _interactive_payload(
        run_type=run_type,
        portfolio=portfolio,
        request=request,
        # Process default is demo; request rebinds to synthetic (same as worker).
        process_dataset_id=DEMO_HISTORICAL_DATASET_ID,
    )
    assert interactive_dataset == SYNTHETIC_HISTORICAL_DATASET_ID

    url = f"sqlite:///{tmp_path / f'parity_{run_type}.db'}"
    factory = make_sqlite_session_factory(url)
    # Worker process engine is demo; enqueue request rebinds via shared factories.
    worker_base = build_portfolio_service(
        historical_dataset_id=DEMO_HISTORICAL_DATASET_ID,
        market_data=_market(),
    )
    worker = RiskRunWorker(worker_base, session_factory=factory, max_workers=1)
    try:
        accepted = worker.submit(
            portfolio=portfolio,
            run_type=run_type,
            request=request,
            execute=False,
        )
        assert accepted.status == RiskRunStatus.QUEUED
        assert accepted.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
        assert worker.poll_once(limit=5) == 1
        done = _wait_worker(worker, accepted.id)
    finally:
        worker.shutdown(wait=True)

    assert done.status == RiskRunStatus.COMPLETED, done.error_message
    assert done.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
    assert len(done.results) == 1
    worker_payload = done.results[0].payload
    assert worker_payload == interactive


def test_execute_prefers_persisted_columns_over_tampered_request_blob(tmp_path):
    """R0.8.4 residual: emptied/wrong request must not rebind away from columns."""
    portfolio = _book("parity-columns")
    request = {
        "methodology": "DELTA_GAMMA",
        "historical_dataset_id": SYNTHETIC_HISTORICAL_DATASET_ID,
        "calculation_config": {"observations": 250, "seed": 7},
    }
    interactive_synth, _ = _interactive_payload(
        run_type="summary",
        portfolio=portfolio,
        request=request,
        process_dataset_id=DEMO_HISTORICAL_DATASET_ID,
    )
    interactive_demo, demo_id = _interactive_payload(
        run_type="summary",
        portfolio=portfolio,
        request={"methodology": "DELTA_GAMMA"},
        process_dataset_id=DEMO_HISTORICAL_DATASET_ID,
    )
    assert demo_id == DEMO_HISTORICAL_DATASET_ID
    assert interactive_synth != interactive_demo

    url = f"sqlite:///{tmp_path / 'parity_columns.db'}"
    factory = make_sqlite_session_factory(url)
    worker_base = build_portfolio_service(
        historical_dataset_id=DEMO_HISTORICAL_DATASET_ID,
        market_data=_market(),
    )
    worker = RiskRunWorker(worker_base, session_factory=factory, max_workers=1)
    try:
        accepted = worker.submit(
            portfolio=portfolio,
            run_type="summary",
            request=request,
            execute=False,
        )
        assert accepted.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
        # Tamper: wipe dataset id from request blob while columns stay synthetic.
        with session_scope(factory) as session:
            row = session.get(RiskRunRow, accepted.id)
            assert row is not None
            assert row.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
            row.request = {"methodology": "DELTA_GAMMA"}
            session.flush()
        # Resolve-from-columns still yields synthetic (prove blob alone would drift).
        with session_scope(factory) as session:
            stored = SqlAlchemyRiskRunRepository(session).get(accepted.id)
            assert stored is not None
            blob_only = resolve_run_spec(
                dict(stored.request or {}),
                risk_engine=worker_base.risk,
                run_type=stored.run_type,
            )
            assert blob_only.historical_dataset_id == DEMO_HISTORICAL_DATASET_ID
            from_columns = resolve_execute_spec(stored, risk_engine=worker_base.risk)
            assert from_columns.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID

        assert worker.poll_once(limit=5) == 1
        done = _wait_worker(worker, accepted.id)
    finally:
        worker.shutdown(wait=True)

    assert done.status == RiskRunStatus.COMPLETED, done.error_message
    assert done.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
    payload = done.results[0].payload
    assert payload == interactive_synth
    assert payload != interactive_demo


def test_worker_execute_uses_stored_portfolio_not_posted_attacker(tmp_path):
    """Portfolio identity: completed run prices the stored book, not the POST body."""
    stored = Portfolio(
        id="parity-ident",
        name="Stored",
        positions=[
            EquityPosition(type="equity", id="eq-kept", symbol="NVDA", quantity=25),
        ],
    )
    posted = Portfolio(
        id="parity-ident",
        name="Attacker",
        positions=[
            EquityPosition(type="equity", id="eq-wipe", symbol="NVDA", quantity=1),
        ],
    )
    request = {
        "methodology": "DELTA_GAMMA",
        "historical_dataset_id": SYNTHETIC_HISTORICAL_DATASET_ID,
        "calculation_config": {"observations": 250, "seed": 7},
    }
    expected, _ = _interactive_payload(
        run_type="summary",
        portfolio=stored,
        request=request,
        process_dataset_id=DEMO_HISTORICAL_DATASET_ID,
    )
    attacker, _ = _interactive_payload(
        run_type="summary",
        portfolio=posted,
        request=request,
        process_dataset_id=DEMO_HISTORICAL_DATASET_ID,
    )
    assert expected != attacker

    url = f"sqlite:///{tmp_path / 'parity_ident.db'}"
    factory = make_sqlite_session_factory(url)
    from app.persistence.sqlalchemy_repos import SqlAlchemyPortfolioRepository

    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).create(stored)

    worker_base = build_portfolio_service(
        historical_dataset_id=DEMO_HISTORICAL_DATASET_ID,
        market_data=_market(),
    )
    # External-style: enqueue without in-process portfolio cache, then poll.
    api = RiskRunWorker(worker_base, session_factory=factory, max_workers=1)
    try:
        accepted = api.submit(portfolio=posted, run_type="summary", request=request, execute=False)
        api.shutdown(wait=False)
    finally:
        api.shutdown(wait=False)

    drain = RiskRunWorker(worker_base, session_factory=factory, max_workers=1)
    try:
        assert drain.poll_once(limit=5) == 1
        done = _wait_worker(drain, accepted.id)
    finally:
        drain.shutdown(wait=True)

    assert done.status == RiskRunStatus.COMPLETED, done.error_message
    assert done.results[0].payload == expected
    assert done.results[0].payload != attacker
