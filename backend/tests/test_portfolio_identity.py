"""R0.8.3 server-owned portfolio identity: create vs update vs calculate."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.domain.models import EquityPosition, Portfolio
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.persistence.testing import make_sqlite_session_factory
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService
from app.services.risk_run_worker import RiskRunWorker

_CROSS_ASSET_POSITION_IDS = tuple(p.id for p in SAMPLE_PORTFOLIO.positions)

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


def _assert_cross_asset_seed(book: Portfolio, *, ordered: bool = False) -> None:
    """Pin SAMPLE / global-macro Cross-Asset identity (do not mutate demo contracts).

    SQLAlchemy trade reload does not preserve insert order; identity is id set +
    economics. In-code catalog responses keep SAMPLE order.
    """
    assert book.id == "global-macro"
    assert book.name == "Global Macro Demo"
    assert book.desk == "Global Macro"
    got_ids = [p.id for p in book.positions]
    assert set(got_ids) == set(_CROSS_ASSET_POSITION_IDS)
    assert len(got_ids) == len(_CROSS_ASSET_POSITION_IDS)
    if ordered:
        assert got_ids == list(_CROSS_ASSET_POSITION_IDS)
    nvda = next(p for p in book.positions if p.id == "eq-nvda")
    assert nvda.symbol == "NVDA"
    assert nvda.quantity == 1200
    spy = next(p for p in book.positions if p.id == "eq-spy")
    assert spy.quantity == 900
    assert SAMPLE_PORTFOLIO.id == "global-macro"
    assert [p.id for p in SAMPLE_PORTFOLIO.positions] == list(_CROSS_ASSET_POSITION_IDS)


def _attacker_global_macro() -> Portfolio:
    return _book("global-macro", "Attacker Book", _equity("eq-wipe", "AAPL", quantity=1))


def test_submit_cannot_overwrite_seeded_global_macro(session_factory):
    """RiskRun submit against the seeded demo id must keep the Cross-Asset book."""
    with session_scope(session_factory) as session:
        SqlAlchemyPortfolioRepository(session).create(SAMPLE_PORTFOLIO)
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, session_factory=session_factory, max_workers=1)
    try:
        view = worker.submit(portfolio=_attacker_global_macro(), run_type="summary", execute=False)
        assert view.portfolio_id == "global-macro"
    finally:
        worker.shutdown(wait=False)
    with session_scope(session_factory) as session:
        loaded = SqlAlchemyPortfolioRepository(session).get("global-macro")
        assert loaded is not None
        _assert_cross_asset_seed(loaded)
        assert "eq-wipe" not in [p.id for p in loaded.positions]


def test_http_post_run_cannot_overwrite_seeded_global_macro(monkeypatch, tmp_path):
    """SEC-003 / RF-013: POST /risk/runs with id=global-macro must not clobber seed."""
    db_path = tmp_path / "rf013_global_macro.db"
    monkeypatch.setenv("RISKFORGE_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    from app.main import app

    attacker = _attacker_global_macro().model_dump(mode="json")
    with TestClient(app) as client:
        assert client.app.state.persistence_enabled is True
        before = client.get("/api/v1/portfolio")
        assert before.status_code == 200
        _assert_cross_asset_seed(Portfolio.model_validate(before.json()))

        catalog = client.get("/api/v1/portfolios/global-macro")
        assert catalog.status_code == 200
        _assert_cross_asset_seed(Portfolio.model_validate(catalog.json()), ordered=True)

        created = client.post(
            "/api/v1/risk/runs",
            json={"portfolio": attacker, "run_type": "summary", "request": {"methodology": "DELTA_GAMMA"}},
        )
        assert created.status_code == 202, created.text
        body = created.json()
        assert body["portfolio_id"] == "global-macro"
        assert body["portfolio_version"] == 1
        assert body["status"] == "QUEUED"

        after = client.get("/api/v1/portfolio")
        assert after.status_code == 200
        _assert_cross_asset_seed(Portfolio.model_validate(after.json()))
        assert after.json()["name"] != "Attacker Book"
        assert "eq-wipe" not in [p["id"] for p in after.json()["positions"]]

        catalog_after = client.get("/api/v1/portfolios/global-macro")
        assert catalog_after.status_code == 200
        _assert_cross_asset_seed(Portfolio.model_validate(catalog_after.json()), ordered=True)

        legacy = client.post(
            "/risk/runs",
            json={"portfolio": attacker, "run_type": "summary", "request": {"methodology": "DELTA_GAMMA"}},
        )
        assert legacy.status_code == 202, legacy.text

        with session_scope(client.app.state.session_factory) as session:
            stored = SqlAlchemyPortfolioRepository(session).get("global-macro")
            assert stored is not None
            _assert_cross_asset_seed(stored)
            assert stored.name != "Attacker Book"
            assert "eq-wipe" not in [p.id for p in stored.positions]
            assert stored.version == 1
            run_ver = session.execute(
                text("SELECT portfolio_version FROM risk_runs WHERE id = :rid"),
                {"rid": body["id"]},
            ).scalar_one()
            assert run_ver == 1


def test_create_starts_at_version_1_ignoring_client_version(session_factory):
    """Server owns version: create always stores 1, even if the client sends 99."""
    posted = Portfolio(
        id="ident-ver",
        name="Client Version",
        positions=[_equity("eq-1", "AAPL")],
        version=99,
    )
    with session_scope(session_factory) as session:
        repo = SqlAlchemyPortfolioRepository(session)
        created = repo.create(posted)
        assert created.version == 1
        loaded = repo.get("ident-ver")
        assert loaded is not None
        assert loaded.version == 1
        stored = session.execute(
            text("SELECT version FROM portfolios WHERE id = 'ident-ver'")
        ).scalar_one()
        assert stored == 1


def test_update_bumps_version(session_factory):
    original = _book("ident-bump", "Original", _equity("eq-old", "AAPL"))
    revised = _book("ident-bump", "Revised", _equity("eq-new", "MSFT"))
    with session_scope(session_factory) as session:
        repo = SqlAlchemyPortfolioRepository(session)
        created = repo.create(original)
        assert created.version == 1
        updated = repo.update(revised.model_copy(update={"version": 1}))
        assert updated.version == 2
        loaded = repo.get("ident-bump")
        assert loaded is not None
        assert loaded.version == 2
        assert loaded.name == "Revised"
        stored = session.execute(
            text("SELECT version FROM portfolios WHERE id = 'ident-bump'")
        ).scalar_one()
        assert stored == 2


def test_stale_version_update_fails_closed(session_factory):
    original = _book("ident-cas", "Original", _equity("eq-old", "AAPL"))
    revised = _book("ident-cas", "Revised", _equity("eq-new", "MSFT"))
    stale = _book("ident-cas", "Stale", _equity("eq-stale", "IBM"))
    with session_scope(session_factory) as session:
        repo = SqlAlchemyPortfolioRepository(session)
        repo.create(original)
        bumped = repo.update(revised.model_copy(update={"version": 1}))
        assert bumped.version == 2
        with pytest.raises(ValueError, match="version"):
            repo.update(stale.model_copy(update={"version": 1}))
        loaded = repo.get("ident-cas")
        assert loaded is not None
        assert loaded.name == "Revised"
        assert loaded.version == 2
        assert [p.id for p in loaded.positions] == ["eq-new"]
        stored = session.execute(
            text("SELECT version FROM portfolios WHERE id = 'ident-cas'")
        ).scalar_one()
        assert stored == 2


def test_save_upsert_sets_or_bumps_version(session_factory):
    """Legacy seed save: insert starts at 1; overwrite bumps and does not CAS."""
    first = _book("ident-save", "Seed", _equity("eq-1", "AAPL"))
    second = _book("ident-save", "Reseed", _equity("eq-2", "MSFT"))
    with session_scope(session_factory) as session:
        repo = SqlAlchemyPortfolioRepository(session)
        created = repo.save(first)
        assert created.version == 1
        overwritten = repo.save(second.model_copy(update={"version": 99}))
        assert overwritten.version == 2
        loaded = repo.get("ident-save")
        assert loaded is not None
        assert loaded.version == 2
        assert loaded.name == "Reseed"


def test_submit_records_stored_portfolio_version(session_factory):
    """Attach-stored submit copies the book's current version onto the run header."""
    stored = _book("ident-pv", "Stored Book", _equity("eq-kept", "AAPL", quantity=25))
    with session_scope(session_factory) as session:
        created = SqlAlchemyPortfolioRepository(session).create(stored)
        assert created.version == 1
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(svc, session_factory=session_factory, max_workers=1)
    try:
        first = worker.submit(portfolio=stored, run_type="summary", execute=False)
        assert first.portfolio_id == "ident-pv"
        assert first.portfolio_version == 1
        with session_scope(session_factory) as session:
            repo = SqlAlchemyPortfolioRepository(session)
            loaded = repo.get("ident-pv")
            assert loaded is not None
            bumped = repo.update(loaded)
            assert bumped.version == 2
            header = SqlAlchemyRiskRunRepository(session).get(first.id)
            assert header is not None
            assert header.portfolio_version == 1
            sql_ver = session.execute(
                text("SELECT portfolio_version FROM risk_runs WHERE id = :rid"),
                {"rid": first.id},
            ).scalar_one()
            assert sql_ver == 1
        second = worker.submit(portfolio=stored, run_type="summary", execute=False)
        assert second.portfolio_version == 2
        assert first.portfolio_version == 1
    finally:
        worker.shutdown(wait=False)
