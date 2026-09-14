"""R0.12.4 nightly — live Postgres two-worker claim (SKIP LOCKED).

Local (``CI`` and ``QUANTLINEAGE_NIGHTLY`` unset): skip if the DSN is missing or
unreachable. When ``QUANTLINEAGE_NIGHTLY`` is set, fail if the DSN is missing or
unreachable. When ``CI`` is set and a postgresql DSN is offered, fail if it is
unreachable (the GHA skip-green hole). ``CI`` plus an unset DSN still skips so
PR ``backend-pytest`` is not broken. Does not change PR ``postgres-persistence-smoke``.
"""
from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from app.domain.models import EquityPosition, Portfolio, RiskRun, RiskRunStatus
from app.persistence.config import get_configured_database_url
from app.persistence.session import create_engine_from_url, create_session_factory, session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, '').strip().lower() in {'1', 'true', 'yes', 'on'}

def _configured_postgres_url() -> str | None:
    url = (get_configured_database_url() or '').strip()
    if not url.startswith('postgresql'):
        return None
    return url

def _postgres_reachable(url: str) -> bool:
    try:
        import psycopg
        from sqlalchemy.engine.url import make_url
        dsn = make_url(url).set(drivername='postgresql').render_as_string(hide_password=False)
        with psycopg.connect(dsn, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
    except Exception:
        return False
    return True

def require_live_postgres() -> str:
    """Return a reachable postgresql DSN, or skip/fail per env.

    * Local (``CI`` and ``QUANTLINEAGE_NIGHTLY`` unset): skip if missing/unreachable.
    * ``QUANTLINEAGE_NIGHTLY`` set: fail if missing or unreachable.
    * ``CI`` set and a postgresql DSN is offered: fail if unreachable.
    * ``CI`` set and DSN missing: skip (PR ``backend-pytest`` has no Postgres).
    """
    ci = _env_flag('CI')
    nightly = _env_flag('QUANTLINEAGE_NIGHTLY')
    url = _configured_postgres_url()
    if url and _postgres_reachable(url):
        return url
    if nightly or (ci and url):
        detail = 'unreachable' if url else 'missing'
        pytest.fail(f'QUANTLINEAGE_DATABASE_URL must be a reachable postgresql DSN when CI or QUANTLINEAGE_NIGHTLY is set ({detail})')
    pytest.skip('live Postgres required (nightly GHA service; local docker optional — see BUILD_NOTES / .github/workflows/nightly.yml)')

def _factory():
    engine = create_engine_from_url(require_live_postgres(), echo=False)
    return create_session_factory(engine=engine)

def _seed_book_and_runs(factory, *, n_runs: int) -> tuple[str, list[str]]:
    book_id = f'nightly-two-worker-{uuid4().hex[:12]}'
    book = Portfolio(id=book_id, name='Nightly two-worker book', positions=[EquityPosition(type='equity', id=f'{book_id}-eq', symbol='AAPL', quantity=1)])
    run_ids = [f'{book_id}-run-{idx}' for idx in range(n_runs)]
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).save(book)
        repo = SqlAlchemyRiskRunRepository(session)
        for run_id in run_ids:
            repo.create(RiskRun(id=run_id, portfolio_id=book_id, status=RiskRunStatus.QUEUED, run_type='summary'))
    return (book_id, run_ids)

def _claim_one(factory, barrier: threading.Barrier) -> list[str]:
    session = factory()
    try:
        repo = SqlAlchemyRiskRunRepository(session)
        barrier.wait(timeout=10)
        claimed = repo.claim_queued(limit=1)
        session.commit()
        return [run.id for run in claimed]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def test_two_workers_do_not_double_claim_one_queued_run():
    factory = _factory()
    _book_id, run_ids = _seed_book_and_runs(factory, n_runs=1)
    barrier = threading.Barrier(2)
    boxes: list[list[str]] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            boxes.append(_claim_one(factory, barrier))
        except BaseException as exc:
            errors.append(exc)
    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), 'claimer thread hung'
    assert not errors, errors
    flat = [rid for batch in boxes for rid in batch]
    assert flat.count(run_ids[0]) == 1, boxes
    assert boxes.count([]) == 1, boxes
    with session_scope(factory) as session:
        stored = SqlAlchemyRiskRunRepository(session).get(run_ids[0])
        assert stored is not None
        assert stored.status == RiskRunStatus.RUNNING

def test_two_workers_claim_distinct_queued_runs():
    factory = _factory()
    _book_id, run_ids = _seed_book_and_runs(factory, n_runs=2)
    barrier = threading.Barrier(2)
    boxes: list[list[str]] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            boxes.append(_claim_one(factory, barrier))
        except BaseException as exc:
            errors.append(exc)
    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), 'claimer thread hung'
    assert not errors, errors
    flat = [rid for batch in boxes for rid in batch]
    assert sorted(flat) == sorted(run_ids), boxes
    assert len(set(flat)) == 2, boxes
