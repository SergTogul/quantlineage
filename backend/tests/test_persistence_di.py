"""M5.6: optional FastAPI persistence DI via RISKFORGE_DATABASE_URL."""
from __future__ import annotations

import time

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from tests.market_fixtures import FixedMarketProvider, equity_spot_market

from app.api.deps import (
    get_default_market_snapshot,
    get_limit_definition_repository,
    get_market_snapshot_repository,
    get_scenario_definition_repository,
)
from app.domain.models import EquityPosition, Portfolio, RiskRunStatus
from app.persistence.config import get_configured_database_url
from app.persistence.repositories import (
    LimitDefinitionRepository,
    MarketSnapshotRepository,
    ScenarioDefinitionRepository,
)
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyLimitDefinitionRepository,
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
    SqlAlchemyScenarioDefinitionRepository,
)
from app.persistence.wiring import (
    DEFAULT_MARKET_SNAPSHOT_ID,
    default_limit_id,
    default_seed_scenarios,
)
from app.risk.limits import DEFAULT_LIMITS
from app.sample import SAMPLE_PORTFOLIO


@pytest.fixture
def clear_db_url(monkeypatch):
    monkeypatch.delenv('RISKFORGE_DATABASE_URL', raising=False)

def test_get_configured_database_url_none_when_unset(clear_db_url, monkeypatch):
    monkeypatch.delenv('RISKFORGE_DATABASE_URL', raising=False)
    assert get_configured_database_url() is None

def test_get_configured_database_url_strips_blank(monkeypatch):
    monkeypatch.setenv('RISKFORGE_DATABASE_URL', '   ')
    assert get_configured_database_url() is None

def test_get_configured_database_url_returns_value(monkeypatch):
    monkeypatch.setenv('RISKFORGE_DATABASE_URL', 'sqlite:///./tmp.db')
    assert get_configured_database_url() == 'sqlite:///./tmp.db'

def test_default_portfolio_is_sample_without_database_url(clear_db_url):
    from app.main import app
    with TestClient(app) as client:
        resp = client.get('/portfolio')
        assert resp.status_code == 200
        body = resp.json()
        assert body['id'] == SAMPLE_PORTFOLIO.id
        assert body['name'] == SAMPLE_PORTFOLIO.name
        assert len(body['positions']) == len(SAMPLE_PORTFOLIO.positions)

def test_memory_repos_seeded_without_database_url(clear_db_url):
    """Unset URL → in-memory snapshot / scenario / limit repos on app.state."""
    from app.main import app
    with TestClient(app) as client:
        assert client.app.state.persistence_enabled is False
        assert client.app.state.session_factory is None
        assert client.app.state.market_snapshot_repo is not None
        assert client.app.state.scenario_definition_repo is not None
        assert client.app.state.limit_definition_repo is not None
        snap = client.app.state.market_snapshot_repo.get(DEFAULT_MARKET_SNAPSHOT_ID)
        assert snap is not None
        assert 'NVDA' in snap.equity_spots or 'SPY' in snap.equity_spots
        scenarios = client.app.state.scenario_definition_repo.list_all()
        assert len(scenarios) == len(default_seed_scenarios())
        ids = {s.id for s in scenarios}
        assert 'eq_down_10' in ids
        assert 'lehman_2008' in ids
        firm_limits = client.app.state.limit_definition_repo.list_for_portfolio(None)
        assert len(firm_limits) == len(DEFAULT_LIMITS)
        metrics = {lim.metric for _, lim in firm_limits}
        assert 'var_99' in metrics

def test_depends_repos_available_without_database_url(clear_db_url):
    """Depends() resolves in-memory repos when DATABASE_URL is unset."""
    from app.main import app

    @app.get('/_test/di/memory-repos')
    def _probe(market: MarketSnapshotRepository=Depends(get_market_snapshot_repository), scenarios: ScenarioDefinitionRepository=Depends(get_scenario_definition_repository), limits: LimitDefinitionRepository=Depends(get_limit_definition_repository), snap=Depends(get_default_market_snapshot)):
        return {'snapshot_id': snap.id, 'scenario_count': len(scenarios.list_all()), 'limit_count': len(limits.list_for_portfolio(None)), 'market_has_seed': market.get(DEFAULT_MARKET_SNAPSHOT_ID) is not None}
    with TestClient(app) as client:
        resp = client.get('/_test/di/memory-repos')
        assert resp.status_code == 200
        body = resp.json()
        assert body['snapshot_id'] == DEFAULT_MARKET_SNAPSHOT_ID
        assert body['scenario_count'] == len(default_seed_scenarios())
        assert body['limit_count'] == len(DEFAULT_LIMITS)
        assert body['market_has_seed'] is True

def test_default_risk_runs_use_memory_without_database_url(clear_db_url, tiny_portfolio):
    from app.api import deps
    from app.main import app
    previous = deps.portfolio_service.market_data
    deps.portfolio_service.market_data = FixedMarketProvider(equity_spot_market("SPY", 190.0))
    try:
        with TestClient(app) as client:
            created = client.post('/risk/runs', json={'portfolio': tiny_portfolio.model_dump(mode='json'), 'run_type': 'summary'})
            assert created.status_code == 202
            run_id = created.json()['id']
            done = _wait_terminal(client, run_id)
            assert done['status'] == 'COMPLETED'
            assert getattr(client.app.state, 'session_factory', None) is None
            assert getattr(client.app.state, 'persistence_enabled', False) is False
    finally:
        deps.portfolio_service.market_data = previous

@pytest.fixture
def tiny_portfolio() -> Portfolio:
    return Portfolio(id='di-async-book', name='DI Async Book', positions=[EquityPosition(type='equity', id='eq-di-1', symbol='SPY', quantity=10)])

def _wait_terminal(client: TestClient, run_id: str, *, timeout_s: float=30.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        resp = client.get(f'/risk/runs/{run_id}')
        assert resp.status_code == 200
        last = resp.json()
        if last['status'] in {RiskRunStatus.COMPLETED.value, RiskRunStatus.FAILED.value}:
            return last
        time.sleep(0.05)
    raise AssertionError(f'run {run_id} did not finish; last={last}')

def test_database_url_wires_sqlalchemy_portfolio_and_risk_runs(monkeypatch, tmp_path, tiny_portfolio):
    """When RISKFORGE_DATABASE_URL is set, lifespan uses SQLAlchemy repos."""
    db_path = tmp_path / 'm56_di.db'
    url = f'sqlite:///{db_path}'
    monkeypatch.setenv('RISKFORGE_DATABASE_URL', url)
    from app.api import deps
    from app.main import app
    previous = deps.portfolio_service.market_data
    deps.portfolio_service.market_data = FixedMarketProvider(equity_spot_market("SPY", 190.0))
    try:
        with TestClient(app) as client:
            assert client.app.state.persistence_enabled is True
            assert client.app.state.session_factory is not None
            assert client.app.state.market_snapshot_repo is None
            assert client.app.state.scenario_definition_repo is None
            assert client.app.state.limit_definition_repo is None
            resp = client.get('/portfolio')
            assert resp.status_code == 200
            body = resp.json()
            assert body['id'] == SAMPLE_PORTFOLIO.id
            assert len(body['positions']) == len(SAMPLE_PORTFOLIO.positions)
            with session_scope(client.app.state.session_factory) as session:
                stored = SqlAlchemyPortfolioRepository(session).get(SAMPLE_PORTFOLIO.id)
                assert stored is not None
                assert stored.name == SAMPLE_PORTFOLIO.name
            created = client.post('/risk/runs', json={'portfolio': tiny_portfolio.model_dump(mode='json'), 'run_type': 'summary', 'request': {'methodology': 'DELTA_GAMMA'}})
            assert created.status_code == 202
            run_id = created.json()['id']
            done = _wait_terminal(client, run_id)
            assert done['status'] == 'COMPLETED', done.get('error_message')
            assert done['results'][0]['result_type'] == 'summary'
            with session_scope(client.app.state.session_factory) as session:
                run = SqlAlchemyRiskRunRepository(session).get(run_id)
                assert run is not None
                assert run.status == RiskRunStatus.COMPLETED
                payloads = SqlAlchemyRiskRunRepository(session).get_result_payloads(run_id)
                assert payloads is not None
                assert 'summary' in payloads
    finally:
        deps.portfolio_service.market_data = previous

def test_database_url_seeds_snapshots_scenarios_limits(monkeypatch, tmp_path):
    """SQLAlchemy path seeds market snapshot, scenarios, and limit definitions."""
    db_path = tmp_path / 'm56_seed.db'
    monkeypatch.setenv('RISKFORGE_DATABASE_URL', f'sqlite:///{db_path}')
    from app.main import app
    with TestClient(app) as client:
        factory = client.app.state.session_factory
        assert factory is not None
        with session_scope(factory) as session:
            snap = SqlAlchemyMarketSnapshotRepository(session).get(DEFAULT_MARKET_SNAPSHOT_ID)
            assert snap is not None
            assert snap.id == DEFAULT_MARKET_SNAPSHOT_ID
            meta = SqlAlchemyMarketSnapshotRepository(session).get_meta(DEFAULT_MARKET_SNAPSHOT_ID)
            assert meta is not None
            assert meta['meta'].get('source') == 'sample'
            scenarios = SqlAlchemyScenarioDefinitionRepository(session).list_all()
            assert len(scenarios) == len(default_seed_scenarios())
            assert {s.id for s in scenarios} >= {'eq_down_10', 'lehman_2008', 'stagflation'}
            limits = SqlAlchemyLimitDefinitionRepository(session).list_for_portfolio(None)
            assert len(limits) == len(DEFAULT_LIMITS)
            by_id = dict(limits)
            for lim in DEFAULT_LIMITS:
                assert default_limit_id(lim) in by_id
                assert by_id[default_limit_id(lim)].metric == lim.metric

def test_depends_repos_available_with_database_url(monkeypatch, tmp_path):
    """Depends() resolves SQLAlchemy repos when DATABASE_URL is set."""
    monkeypatch.setenv('RISKFORGE_DATABASE_URL', f"sqlite:///{tmp_path / 'm56_depends.db'}")
    from app.main import app

    @app.get('/_test/di/sql-repos')
    def _probe(market: MarketSnapshotRepository=Depends(get_market_snapshot_repository), scenarios: ScenarioDefinitionRepository=Depends(get_scenario_definition_repository), limits: LimitDefinitionRepository=Depends(get_limit_definition_repository), snap=Depends(get_default_market_snapshot)):
        return {'snapshot_id': snap.id, 'scenario_count': len(scenarios.list_all()), 'limit_count': len(limits.list_for_portfolio(None)), 'market_has_seed': market.get(DEFAULT_MARKET_SNAPSHOT_ID) is not None, 'repo_types': [type(market).__name__, type(scenarios).__name__, type(limits).__name__]}
    with TestClient(app) as client:
        resp = client.get('/_test/di/sql-repos')
        assert resp.status_code == 200
        body = resp.json()
        assert body['snapshot_id'] == DEFAULT_MARKET_SNAPSHOT_ID
        assert body['scenario_count'] == len(default_seed_scenarios())
        assert body['limit_count'] == len(DEFAULT_LIMITS)
        assert body['market_has_seed'] is True
        assert body['repo_types'] == ['SqlAlchemyMarketSnapshotRepository', 'SqlAlchemyScenarioDefinitionRepository', 'SqlAlchemyLimitDefinitionRepository']

def test_sqlalchemy_portfolio_reflects_db_updates(monkeypatch, tmp_path):
    db_path = tmp_path / 'm56_portfolio.db'
    monkeypatch.setenv('RISKFORGE_DATABASE_URL', f'sqlite:///{db_path}')
    from app.main import app
    with TestClient(app) as client:
        factory = client.app.state.session_factory
        updated = SAMPLE_PORTFOLIO.model_copy(update={'name': 'Updated Via Repo', 'positions': SAMPLE_PORTFOLIO.positions[:1]})
        with session_scope(factory) as session:
            SqlAlchemyPortfolioRepository(session).save(updated)
        resp = client.get('/portfolio')
        assert resp.status_code == 200
        body = resp.json()
        assert body['name'] == 'Updated Via Repo'
        assert len(body['positions']) == 1
