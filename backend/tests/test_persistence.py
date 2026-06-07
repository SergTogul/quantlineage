"""M5.1 persistence: SQLite round-trips (no live Postgres required)."""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.domain.models import (
    EquityPosition,
    MarketSnapshot,
    Portfolio,
    RiskLimit,
    RiskRun,
    RiskRunStatus,
)
from app.risk.factor_types import EquitySpot
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    ScenarioCategory,
    ScenarioThreshold,
)
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyLimitDefinitionRepository,
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
    SqlAlchemyScenarioDefinitionRepository,
)
from app.persistence.testing import make_sqlite_engine, make_sqlite_session_factory


@pytest.fixture
def session_factory():
    return make_sqlite_session_factory()

def test_schema_has_expected_tables():
    engine = make_sqlite_engine()
    names = set(inspect(engine).get_table_names())
    assert {'portfolios', 'trades', 'market_snapshots', 'scenario_definitions', 'risk_runs', 'risk_results', 'limit_definitions'} <= names

def test_portfolio_and_trades_round_trip(session_factory):
    portfolio = Portfolio(id='p-persist', name='Persist Book', desk='Rates Desk', positions=[EquityPosition(type='equity', id='eq-1', symbol='SPY', quantity=10, desk='Equity Desk', book='Equity')])
    with session_scope(session_factory) as session:
        repo = SqlAlchemyPortfolioRepository(session)
        repo.save(portfolio)
        assert repo.list_ids() == ['p-persist']
    with session_scope(session_factory) as session:
        loaded = SqlAlchemyPortfolioRepository(session).get('p-persist')
        assert loaded is not None
        assert loaded.name == 'Persist Book'
        assert loaded.desk == 'Rates Desk'
        assert len(loaded.positions) == 1
        assert loaded.positions[0].id == 'eq-1'
        assert loaded.positions[0].symbol == 'SPY'
        assert loaded.positions[0].desk == 'Equity Desk'

def test_market_snapshot_meta_and_data(session_factory):
    snap = MarketSnapshot(id='snap-1', as_of=date(2026, 9, 2), equity_spots={'SPY': 400.0}, rates={'USD': 0.04})
    with session_scope(session_factory) as session:
        repo = SqlAlchemyMarketSnapshotRepository(session)
        repo.save(snap, meta={'source': 'unit-test'})
        meta = repo.get_meta('snap-1')
        assert meta is not None
        assert meta['as_of'] == '2026-09-02'
        assert meta['content_hash'] == snap.content_hash()
        assert meta['meta']['source'] == 'unit-test'
        loaded = repo.get('snap-1')
        assert loaded is not None
        assert loaded.as_of == date(2026, 9, 2)
        assert math.isclose(loaded.equity_spots['SPY'], 400.0)
        with pytest.raises(TypeError):
            loaded.equity_spots['SPY'] = 1.0

def test_scenario_definition_round_trip(session_factory):
    scenario = Scenario(
        id='scn-eq-crash',
        name='Equity crash',
        description='demo',
        category=ScenarioCategory.FACTOR,
        shocks=(FactorShock(EquitySpot('SPY'), -0.15),),
        threshold=ScenarioThreshold(max_loss_pct=0.05),
    )
    with session_scope(session_factory) as session:
        repo = SqlAlchemyScenarioDefinitionRepository(session)
        saved = repo.save(scenario)
        assert saved.id == 'scn-eq-crash'
        loaded = repo.get('scn-eq-crash')
        assert loaded is not None
        assert isinstance(loaded, Scenario)
        assert loaded.shocks == scenario.shocks
        assert len(repo.list_all()) == 1

def test_risk_run_lifecycle_and_results(session_factory):
    portfolio = Portfolio(id='p-run', name='Run Book', positions=[EquityPosition(type='equity', id='eq-1', symbol='AAPL', quantity=1)])
    snap = MarketSnapshot(id='snap-run', equity_spots={'AAPL': 100.0})
    with session_scope(session_factory) as session:
        SqlAlchemyPortfolioRepository(session).save(portfolio)
        SqlAlchemyMarketSnapshotRepository(session).save(snap)
        runs = SqlAlchemyRiskRunRepository(session)
        runs.create(RiskRun(id='run-1', portfolio_id='p-run', market_snapshot_id='snap-run', run_type='summary', request={'methodology': 'delta_gamma'}))
        runs.set_status('run-1', RiskRunStatus.RUNNING)
        runs.add_result('run-1', 'summary', {'portfolio_id': 'p-run', 'var_99': 1234.5, 'market_value': 100.0})
        runs.set_status('run-1', RiskRunStatus.COMPLETED)
    with session_scope(session_factory) as session:
        got = SqlAlchemyRiskRunRepository(session).get('run-1')
        assert got is not None
        assert got.status == RiskRunStatus.COMPLETED
        assert got.market_snapshot_id == 'snap-run'
        assert got.result_refs[0].result_type == 'summary'
        assert got.completed_at is not None
        payloads = SqlAlchemyRiskRunRepository(session).get_result_payloads('run-1')
        assert payloads is not None
        assert math.isclose(payloads['summary']['var_99'], 1234.5)

def test_limit_definition_round_trip(session_factory):
    limit = RiskLimit(metric='var_99', limit=250000.0, warning_threshold_pct=80.0, scope='firm', label='Firm VaR')
    with session_scope(session_factory) as session:
        repo = SqlAlchemyLimitDefinitionRepository(session)
        repo.save('lim-var99', limit)
        loaded = repo.get('lim-var99')
        assert loaded is not None
        assert loaded.metric == 'var_99'
        assert math.isclose(loaded.limit, 250000.0)
        firm = repo.list_for_portfolio(None)
        assert len(firm) == 1
        assert firm[0][0] == 'lim-var99'

def test_alembic_upgrade_on_sqlite_file(tmp_path: Path):
    """Initial migration applies on SQLite (CI-friendly stand-in for Postgres)."""
    db_path = tmp_path / 'alembic_test.db'
    url = f'sqlite:///{db_path}'
    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / 'alembic.ini'))
    cfg.set_main_option('script_location', str(backend_root / 'migrations'))
    cfg.set_main_option('sqlalchemy.url', url)
    command.upgrade(cfg, 'head')
    engine = make_sqlite_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert 'portfolios' in tables
    assert 'alembic_version' in tables
    columns = {c['name'] for c in inspect(engine).get_columns('risk_runs')}
    assert {'historical_dataset_id', 'historical_dataset_version', 'as_of', 'calculation_config'}.issubset(columns)
    with engine.connect() as conn:
        ver = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    assert ver == '003_risk_run_spec_fields'

def test_no_quantlib_types_in_orm_modules():
    """Guard: persistence package must not import QuantLib."""
    import app.persistence.models as m
    import app.persistence.sqlalchemy_repos as r
    for mod in (m, r):
        assert 'QuantLib' not in dir(mod)
        src = Path(mod.__file__).read_text(encoding='utf-8')
        assert 'import QuantLib' not in src
        assert 'from QuantLib' not in src
