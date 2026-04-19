"""R0.8.3 server-owned portfolio identity: create vs update vs calculate."""
from __future__ import annotations
import pytest
from app.domain.models import EquityPosition, Portfolio
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import SqlAlchemyPortfolioRepository
from app.persistence.testing import make_sqlite_session_factory
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.services.portfolio_service import PortfolioService
from app.services.risk_run_worker import RiskRunWorker

@pytest.fixture
def session_factory():
    return make_sqlite_session_factory()

def _equity(position_id: str, symbol: str, *, quantity: float=10.0) -> EquityPosition:
    return EquityPosition(type='equity', id=position_id, symbol=symbol, quantity=quantity)

def _book(portfolio_id: str, name: str, *positions: EquityPosition) -> Portfolio:
    return Portfolio(id=portfolio_id, name=name, positions=list(positions))

def test_create_then_create_same_id_fails(session_factory):
    first = _book('ident-create', 'First Book', _equity('eq-kept', 'AAPL'))
    second = _book('ident-create', 'Replacement', _equity('eq-wipe', 'MSFT'))
    with session_scope(session_factory) as session:
        repo = SqlAlchemyPortfolioRepository(session)
        created = repo.create(first)
        assert created.id == 'ident-create'
        with pytest.raises(ValueError, match='already exists'):
            repo.create(second)
        loaded = repo.get('ident-create')
        assert loaded is not None
        assert loaded.name == 'First Book'
        assert [p.id for p in loaded.positions] == ['eq-kept']

def test_update_missing_fails(session_factory):
    missing = _book('ident-missing', 'Ghost', _equity('eq-1', 'AAPL'))
    with session_scope(session_factory) as session:
        repo = SqlAlchemyPortfolioRepository(session)
        with pytest.raises(ValueError, match='not found'):
            repo.update(missing)
        assert repo.get('ident-missing') is None

def test_update_replaces_existing_positions(session_factory):
    original = _book('ident-update', 'Original', _equity('eq-old', 'AAPL'))
    revised = _book('ident-update', 'Revised', _equity('eq-new', 'MSFT'))
    with session_scope(session_factory) as session:
        repo = SqlAlchemyPortfolioRepository(session)
        repo.create(original)
        updated = repo.update(revised)
        assert updated.name == 'Revised'
        loaded = repo.get('ident-update')
        assert loaded is not None
        assert loaded.name == 'Revised'
        assert [p.id for p in loaded.positions] == ['eq-new']

def test_submit_against_existing_id_does_not_wipe_stored_positions(session_factory):
    """Queued calculate attaches the stored book; it must not upsert the POST body."""
    stored = _book('ident-run', 'Stored Book', _equity('eq-kept', 'AAPL', quantity=25))
    posted = _book('ident-run', 'Attacker Book', _equity('eq-wipe', 'MSFT', quantity=1))
    with session_scope(session_factory) as session:
        SqlAlchemyPortfolioRepository(session).create(stored)
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, session_factory=session_factory, max_workers=1)
    try:
        view = worker.submit(portfolio=posted, run_type='summary', execute=False)
        assert view.portfolio_id == 'ident-run'
    finally:
        worker.shutdown(wait=False)
    with session_scope(session_factory) as session:
        loaded = SqlAlchemyPortfolioRepository(session).get('ident-run')
        assert loaded is not None
        assert loaded.name == 'Stored Book'
        assert [p.id for p in loaded.positions] == ['eq-kept']
        assert loaded.positions[0].symbol == 'AAPL'
        assert loaded.positions[0].quantity == 25

def test_second_submit_same_id_does_not_replace_trades(session_factory):
    first = _book('ident-twice', 'Original', _equity('eq-kept', 'AAPL', quantity=25))
    second = _book('ident-twice', 'Replacement', _equity('eq-wipe', 'MSFT', quantity=1))
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, session_factory=session_factory, max_workers=1)
    try:
        worker.submit(portfolio=first, run_type='summary', execute=False)
        worker.submit(portfolio=second, run_type='summary', execute=False)
    finally:
        worker.shutdown(wait=False)
    with session_scope(session_factory) as session:
        loaded = SqlAlchemyPortfolioRepository(session).get('ident-twice')
        assert loaded is not None
        assert loaded.name == 'Original'
        assert [p.id for p in loaded.positions] == ['eq-kept']
        assert loaded.positions[0].quantity == 25

def test_submit_creates_portfolio_when_id_is_absent(session_factory):
    posted = _book('ident-new', 'New Book', _equity('eq-1', 'AAPL'))
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, session_factory=session_factory, max_workers=1)
    try:
        view = worker.submit(portfolio=posted, run_type='summary', execute=False)
        assert view.portfolio_id == 'ident-new'
    finally:
        worker.shutdown(wait=False)
    with session_scope(session_factory) as session:
        loaded = SqlAlchemyPortfolioRepository(session).get('ident-new')
        assert loaded is not None
        assert loaded.name == 'New Book'
        assert [p.id for p in loaded.positions] == ['eq-1']

def test_inline_demo_submit_does_not_require_persistence():
    """In-memory calculate path is unchanged: no SQL create/upsert."""
    posted = _book('demo-inline', 'Demo', _equity('eq-1', 'AAPL'))
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, repo=InMemoryRiskRunRepository(), max_workers=1)
    try:
        view = worker.submit(portfolio=posted, run_type='summary', execute=False)
        assert view.portfolio_id == 'demo-inline'
        assert view.status.value == 'QUEUED'
    finally:
        worker.shutdown(wait=False)
