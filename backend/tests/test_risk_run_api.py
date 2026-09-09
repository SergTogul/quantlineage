"""M5.4 async risk-run APIs: POST/GET /risk/runs (+ /api/v1/risk/runs alias)."""
from __future__ import annotations
import time
import pytest
from fastapi.testclient import TestClient
from app.domain.models import EquityPosition, Portfolio, RiskRunStatus
from app.main import app
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import SqlAlchemyPortfolioRepository, SqlAlchemyRiskRunRepository
from app.persistence.testing import make_sqlite_session_factory
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.services.portfolio_service import PortfolioService
from tests.market_fixtures import FixedMarketProvider, equity_spot_market
from app.services.risk_run_service import RiskRunService
from app.services.risk_run_worker import SUPPORTED_RUN_TYPES, RiskRunWorker, execute_run_type

@pytest.fixture
def client():
    from app.api import deps
    previous = deps.portfolio_service.market_data
    # Production panel covers NVDA/SPY (not AAPL); keep fixtures panel-compatible.
    deps.portfolio_service.market_data = FixedMarketProvider(equity_spot_market("NVDA", 190.0))
    try:
        with TestClient(app) as c:
            yield c
    finally:
        deps.portfolio_service.market_data = previous

@pytest.fixture
def tiny_portfolio() -> Portfolio:
    return Portfolio(id='async-book', name='Async Book', positions=[EquityPosition(type='equity', id='eq-1', symbol='NVDA', quantity=10)])

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

def test_create_returns_202_queued(client, tiny_portfolio):
    resp = client.post('/risk/runs', json={'portfolio': tiny_portfolio.model_dump(mode='json'), 'run_type': 'summary', 'request': {'methodology': 'DELTA_GAMMA'}})
    assert resp.status_code == 202
    body = resp.json()
    assert body['status'] == 'QUEUED'
    assert body['portfolio_id'] == 'async-book'
    assert body['run_type'] == 'summary'
    assert body['id']
    assert body['results'] == []

def test_create_persists_factory_dataset_identity(client, tiny_portfolio):
    resp = client.post('/risk/runs', json={'portfolio': tiny_portfolio.model_dump(mode='json'), 'run_type': 'summary', 'request': {'methodology': 'DELTA_GAMMA', 'as_of': 'current', 'calculation_config': {'observations': 750, 'seed': 7}}})
    assert resp.status_code == 202
    body = resp.json()
    assert body['historical_dataset_id'] is not None
    assert body['historical_dataset_version'] is not None
    assert body['as_of'] == 'current'
    assert body['calculation_config'] is not None
    assert body['calculation_config']['observations'] == 750
    assert body['calculation_config']['seed'] == 7

def test_poll_until_completed_with_summary_result(client, tiny_portfolio):
    created = client.post('/risk/runs', json={'portfolio': tiny_portfolio.model_dump(mode='json'), 'run_type': 'summary', 'request': {'methodology': 'DELTA_GAMMA'}})
    assert created.status_code == 202
    run_id = created.json()['id']
    done = _wait_terminal(client, run_id)
    assert done['status'] == 'COMPLETED'
    assert done['error_message'] is None
    assert done['started_at'] is not None
    assert done['finished_at'] is not None
    assert done['duration_seconds'] is not None
    assert done['duration_seconds'] >= 0.0
    assert len(done['results']) == 1
    assert done['results'][0]['result_type'] == 'summary'
    assert done['results'][0]['payload']['portfolio_id'] == 'async-book'

def test_api_v1_alias_matches_unversioned(client, tiny_portfolio):
    created = client.post('/api/v1/risk/runs', json={'portfolio': tiny_portfolio.model_dump(mode='json'), 'run_type': 'var', 'request': {'methodology': 'LINEAR'}})
    assert created.status_code == 202
    run_id = created.json()['id']
    done = _wait_terminal(client, run_id)
    assert done['status'] == 'COMPLETED'
    assert done['run_type'] == 'var'
    via_v1 = client.get(f'/api/v1/risk/runs/{run_id}')
    assert via_v1.status_code == 200
    assert via_v1.json()['status'] == 'COMPLETED'

def test_get_missing_run_404(client):
    resp = client.get('/risk/runs/does-not-exist')
    assert resp.status_code == 404
    body = resp.json()
    assert body['code'] == 'not_found'
    assert 'not found' in body['message'].lower()

def test_unsupported_run_type_400(client, tiny_portfolio):
    resp = client.post('/risk/runs', json={'portfolio': tiny_portfolio.model_dump(mode='json'), 'run_type': 'not-a-real-type'})
    assert resp.status_code == 400
    err = resp.json()
    assert err['code'] == 'bad_request'
    assert err['message'] == 'Invalid request'
    assert 'unsupported run_type' not in err['message']
    assert 'not-a-real-type' not in resp.text

def test_validation_rejects_empty_run_type(client, tiny_portfolio):
    resp = client.post('/risk/runs', json={'portfolio': tiny_portfolio.model_dump(mode='json'), 'run_type': ''})
    assert resp.status_code == 422


def test_typed_request_rejects_unknown_keys(client, tiny_portfolio):
    resp = client.post(
        '/risk/runs',
        json={
            'portfolio': tiny_portfolio.model_dump(mode='json'),
            'run_type': 'summary',
            'request': {'methodology': 'DELTA_GAMMA', 'not_a_real_knob': 1},
        },
    )
    assert resp.status_code == 422
    err = resp.json()
    assert err['code'] == 'validation_error'


def test_typed_request_rejects_bad_methodology(client, tiny_portfolio):
    resp = client.post(
        '/risk/runs',
        json={
            'portfolio': tiny_portfolio.model_dump(mode='json'),
            'run_type': 'var',
            'request': {'methodology': 'NOT_A_METHOD'},
        },
    )
    assert resp.status_code == 422
    err = resp.json()
    assert err['code'] == 'validation_error'


def test_typed_request_rejects_unknown_dataset_id(client, tiny_portfolio):
    resp = client.post(
        '/risk/runs',
        json={
            'portfolio': tiny_portfolio.model_dump(mode='json'),
            'run_type': 'summary',
            'request': {'historical_dataset_id': 'does-not-exist-dataset'},
        },
    )
    assert resp.status_code == 400
    err = resp.json()
    assert err['code'] == 'bad_request'
    assert err['message'] == 'Invalid request'


def test_typed_request_accepts_matching_dataset_id(client, tiny_portfolio):
    from app.risk.historical_data import DEMO_HISTORICAL_DATASET_ID

    resp = client.post(
        '/risk/runs',
        json={
            'portfolio': tiny_portfolio.model_dump(mode='json'),
            'run_type': 'summary',
            'request': {
                'methodology': 'DELTA_GAMMA',
                'historical_dataset_id': DEMO_HISTORICAL_DATASET_ID,
                'historical_dataset_version': 'v1',
            },
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body['historical_dataset_id'] == DEMO_HISTORICAL_DATASET_ID
    assert body['historical_dataset_version'] == 'v1'
    assert body['request']['historical_dataset_id'] == DEMO_HISTORICAL_DATASET_ID


def test_typed_request_rebinds_synthetic_dataset_id(client, tiny_portfolio, monkeypatch):
    """Client-supplied synthetic id must select that dataset, not silently keep demo."""
    monkeypatch.delenv('RISKFORGE_HISTORICAL_DATASET', raising=False)
    from app.services.risk_factories import SYNTHETIC_HISTORICAL_DATASET_ID

    created = client.post(
        '/risk/runs',
        json={
            'portfolio': tiny_portfolio.model_dump(mode='json'),
            'run_type': 'summary',
            'request': {
                'methodology': 'DELTA_GAMMA',
                'historical_dataset_id': SYNTHETIC_HISTORICAL_DATASET_ID,
            },
        },
    )
    assert created.status_code == 202, created.text
    body = created.json()
    assert body['historical_dataset_id'] == SYNTHETIC_HISTORICAL_DATASET_ID
    done = _wait_terminal(client, body['id'])
    assert done['status'] == 'COMPLETED', done
    assert done['historical_dataset_id'] == SYNTHETIC_HISTORICAL_DATASET_ID
    assert done['results'][0]['result_type'] == 'summary'


def test_typed_request_rejects_missing_csv_dataset_path(client, tiny_portfolio, tmp_path):
    missing = tmp_path / 'missing-factors.csv'
    resp = client.post(
        '/risk/runs',
        json={
            'portfolio': tiny_portfolio.model_dump(mode='json'),
            'run_type': 'summary',
            'request': {'historical_dataset_id': str(missing)},
        },
    )
    assert resp.status_code == 400
    err = resp.json()
    assert err['code'] == 'bad_request'
    assert err['message'] == 'Invalid request'


def test_typed_request_rejects_ambiguous_file_dataset_id(client, tiny_portfolio, monkeypatch):
    monkeypatch.delenv('RISKFORGE_HISTORICAL_DATASET', raising=False)
    resp = client.post(
        '/risk/runs',
        json={
            'portfolio': tiny_portfolio.model_dump(mode='json'),
            'run_type': 'summary',
            'request': {'historical_dataset_id': 'file'},
        },
    )
    assert resp.status_code == 400
    err = resp.json()
    assert err['code'] == 'bad_request'


def test_typed_request_rebinds_csv_path_dataset(client, tiny_portfolio, tmp_path, monkeypatch):
    """Process CSV A + request CSV B must COMPLETE on B's identity, never A's."""
    monkeypatch.delenv('RISKFORGE_HISTORICAL_DATASET', raising=False)
    from app.api import deps
    from app.risk.historical_data import file_csv_dataset_id
    from app.services.risk_factories import build_portfolio_service

    path_a = tmp_path / 'process_a.csv'
    path_b = tmp_path / 'request_b.csv'
    for path, equity in ((path_a, 0.01), (path_b, -0.05)):
        path.write_text(
            'date,equity_return,vol_move,rate_move_bps,fx_return\n'
            f'2024-01-02,{equity},0.0,1.0,0.001\n'
            '2024-01-03,-0.02,0.05,-2.0,-0.001\n',
            encoding='utf-8',
        )

    previous = deps.portfolio_service
    deps.portfolio_service = build_portfolio_service(historical_dataset_id=str(path_a))
    deps.portfolio_service.market_data = previous.market_data
    try:
        created = client.post(
            '/risk/runs',
            json={
                'portfolio': tiny_portfolio.model_dump(mode='json'),
                'run_type': 'summary',
                'request': {
                    'methodology': 'DELTA_GAMMA',
                    'historical_dataset_id': str(path_b),
                },
            },
        )
        assert created.status_code == 202, created.text
        body = created.json()
        expected_b = file_csv_dataset_id(path_b)
        assert body['historical_dataset_id'] == expected_b
        assert body['historical_dataset_id'] != file_csv_dataset_id(path_a)
        done = _wait_terminal(client, body['id'])
        assert done['status'] == 'COMPLETED', done
        assert done['historical_dataset_id'] == expected_b
        assert done['results'][0]['result_type'] == 'summary'
    finally:
        deps.portfolio_service = previous


def test_worker_fails_run_on_execution_error(tiny_portfolio):

    class BoomService:

        def summary(self, portfolio, methodology=None):
            raise RuntimeError('boom')
    repo = InMemoryRiskRunRepository()
    worker = RiskRunWorker(BoomService(), repo=repo, max_workers=1)
    view = worker.submit(portfolio=tiny_portfolio, run_type='summary')
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
    assert last.error_message == 'Risk run failed'
    assert 'boom' not in (last.error_message or '')

DASHBOARD_BATCH_KEYS = {
    "portfolio",
    "summary",
    "stress",
    "threats",
    "contributors",
    "limits",
    "factors",
    "varReport",
    "hierarchy",
    "attribution",
}


def test_execute_run_type_dispatch(tiny_portfolio):
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine(), market_data=FixedMarketProvider(equity_spot_market('NVDA', 190.0)))
    hedged = tiny_portfolio.model_copy(deep=True)
    scenario = {
        "id": "eq-down",
        "name": "Equity Down",
        "category": "factor",
        "shocks": [{"factor_type": "equity", "key": "NVDA", "amount": -0.1, "bucket": "NVDA"}],
    }
    requests_by_type = {
        "stress_evaluate": {"scenarios": [scenario]},
        "reverse_stress": {"target_loss_pct": 0.05, "factor": "equity"},
        "reverse_stress_multi": {"target_loss_pct": 0.05, "factors": ["equity"]},
        "stress_compare": {"hedged_portfolio": hedged.model_dump(mode="json"), "scenarios": [scenario]},
        "query": {"question": "What is VaR?"},
        "attribution": {
            "previous_portfolio": tiny_portfolio.model_dump(mode="json"),
            "current_portfolio": tiny_portfolio.model_dump(mode="json"),
        },
        "change_attribution": {
            "previous_portfolio": tiny_portfolio.model_dump(mode="json"),
            "current_portfolio": tiny_portfolio.model_dump(mode="json"),
            "metric": "var_99",
            "methodology": "DELTA_GAMMA",
        },
        "var_compare": {"observations": 50},
    }
    for run_type in sorted(SUPPORTED_RUN_TYPES):
        request = {"methodology": "DELTA_GAMMA", **requests_by_type.get(run_type, {})}
        payload = execute_run_type(
            svc, run_type=run_type, portfolio=tiny_portfolio, request=request
        )
        assert isinstance(payload, dict)


def test_ui_heavy_run_types_in_supported():
    for name in (
        "stress_evaluate",
        "reverse_stress",
        "reverse_stress_multi",
        "stress_compare",
        "query",
        "attribution",
        "attribution_demo",
        "change_attribution",
        "es",
        "var_compare",
    ):
        assert name in SUPPORTED_RUN_TYPES


def test_dashboard_in_supported_run_types():
    assert "dashboard" in SUPPORTED_RUN_TYPES


def test_poll_until_completed_with_dashboard_batch_payload():
    """Live HTTP: dashboard run stores DashboardBatchResponse keys; lists stay lists."""
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio")
        assert book.status_code == 200
        portfolio = book.json()
        created = client.post(
            "/risk/runs",
            json={
                "portfolio": portfolio,
                "run_type": "dashboard",
                "request": {},
            },
        )
        assert created.status_code == 202
        run_id = created.json()["id"]
        done = _wait_terminal(client, run_id, timeout_s=120.0)
        assert done["status"] == "COMPLETED", done
        assert done["run_type"] == "dashboard"
        assert done["error_message"] is None
        assert len(done["results"]) == 1
        assert done["results"][0]["result_type"] == "dashboard"
        payload = done["results"][0]["payload"]
        assert set(payload) == DASHBOARD_BATCH_KEYS
        assert isinstance(payload["stress"], list)
        assert payload["stress"]
        assert isinstance(payload["contributors"], list)
        assert isinstance(payload["limits"], list)
        assert isinstance(payload["factors"], list)
        assert isinstance(payload["threats"], dict)
        assert "evaluations" in payload["threats"]
        assert "items" not in payload["threats"]
        assert isinstance(payload["summary"], dict)
        assert isinstance(payload["varReport"], dict)
        assert isinstance(payload["hierarchy"], dict)
        assert isinstance(payload["attribution"], dict)
        assert isinstance(payload["portfolio"], dict)
        assert payload["portfolio"]["id"] == portfolio["id"]


def test_api_v1_dashboard_run_type():
    with TestClient(app) as client:
        portfolio = client.get("/api/v1/portfolio").json()
        created = client.post(
            "/api/v1/risk/runs",
            json={
                "portfolio": portfolio,
                "run_type": "dashboard",
            },
        )
        assert created.status_code == 202
        done = _wait_terminal(client, created.json()["id"], timeout_s=120.0)
        assert done["status"] == "COMPLETED"
        payload = done["results"][0]["payload"]
        assert set(payload) == DASHBOARD_BATCH_KEYS
        assert isinstance(payload["stress"], list)

def test_worker_with_sqlalchemy_session_factory(tiny_portfolio, tmp_path):
    """Persistence wiring path: SQLAlchemy repo + RiskRunService lifecycle."""
    url = f"sqlite:///{tmp_path / 'risk_runs.db'}"
    factory = make_sqlite_session_factory(url)
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).save(tiny_portfolio)
    svc = PortfolioService(create_pricing_engine(), HistoricalRiskEngine(), market_data=FixedMarketProvider(equity_spot_market('NVDA', 190.0)))
    worker = RiskRunWorker(svc, session_factory=factory, max_workers=1)
    view = worker.submit(portfolio=tiny_portfolio, run_type='summary')
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
    assert last.status == RiskRunStatus.COMPLETED, f'expected COMPLETED, got {last.status}: {last.error_message}'
    assert last.results[0].result_type == 'summary'
    with session_scope(factory) as session:
        stored = SqlAlchemyRiskRunRepository(session).get(run_id)
        assert stored is not None
        assert stored.status == RiskRunStatus.COMPLETED
        payloads = SqlAlchemyRiskRunRepository(session).get_result_payloads(run_id)
        assert payloads is not None
        assert 'summary' in payloads

def test_in_memory_repo_status_enum_matches_service():
    repo = InMemoryRiskRunRepository()
    svc = RiskRunService(repo)
    queued = svc.enqueue(run_id='mem-1', portfolio_id='p', run_type='summary')
    assert queued.status == RiskRunStatus.QUEUED
    running = svc.start('mem-1')
    assert running.status == RiskRunStatus.RUNNING
    done = svc.complete('mem-1', result_type='summary', payload={'ok': True})
    assert done.status == RiskRunStatus.COMPLETED
    assert svc.get_result_payloads('mem-1')['summary']['ok'] is True
