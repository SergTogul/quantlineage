"""RF-014 / R0.11.4: failed risk HTTP and risk-run errors must not leak internals."""
from __future__ import annotations
import time
from typing import Any
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.deps import get_portfolio_service
from app.api.errors import PUBLIC_BAD_REQUEST_MESSAGE, PUBLIC_RISK_RUN_FAILURE_MESSAGE, register_exception_handlers
from app.domain.models import EquityPosition, Portfolio, RiskRunStatus
from app.main import app
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.services.risk_run_worker import RiskRunWorker
_LEAK = 'QuantLib::Error: file /secret/ql/errors.cpp:42 cannot price XYZ'

def _assert_error_shape(body: dict[str, Any]) -> None:
    assert set(body.keys()) == {'code', 'message', 'details'}
    assert isinstance(body['code'], str) and body['code']
    assert isinstance(body['message'], str) and body['message']
    assert body['details'] is None or isinstance(body['details'], (dict, list))

def _assert_no_internal_leak(payload: str) -> None:
    lowered = payload.lower()
    assert _LEAK not in payload
    assert 'quantlib::error' not in lowered
    assert '/secret/' not in lowered
    assert 'errors.cpp' not in lowered
    assert 'traceback' not in lowered

def _tiny_portfolio() -> Portfolio:
    return Portfolio(id='sanitize-book', name='Sanitize Book', positions=[EquityPosition(type='equity', id='eq-1', symbol='AAPL', quantity=10)])

def test_what_if_value_error_does_not_leak_raw_exception() -> None:
    """POST /risk/what-if used detail=str(exc); a leaky ValueError must be sanitized."""

    class LeakyService:

        def what_if(self, request, *, methodology=None):
            raise ValueError(_LEAK)
    app.dependency_overrides[get_portfolio_service] = lambda: LeakyService()
    try:
        with TestClient(app) as client:
            resp = client.post('/risk/what-if', json={'portfolio': _tiny_portfolio().model_dump(mode='json'), 'changes': [{'operation': 'remove', 'position_id': 'eq-1'}]})
    finally:
        app.dependency_overrides.pop(get_portfolio_service, None)
    assert resp.status_code == 400
    body = resp.json()
    _assert_error_shape(body)
    _assert_no_internal_leak(resp.text)
    assert body['code'] == 'bad_request'
    assert body['message'] == PUBLIC_BAD_REQUEST_MESSAGE
    if isinstance(body['details'], dict):
        _assert_no_internal_leak(str(body['details']))

def test_unhandled_500_uses_opaque_internal_error() -> None:
    probe = FastAPI()
    register_exception_handlers(probe)

    @probe.get('/__boom')
    def _boom() -> None:
        raise RuntimeError(_LEAK)
    with TestClient(probe, raise_server_exceptions=False) as client:
        resp = client.get('/__boom')
    assert resp.status_code == 500
    body = resp.json()
    _assert_error_shape(body)
    _assert_no_internal_leak(resp.text)
    assert body['code'] == 'internal_error'
    assert 'unexpected' in body['message'].lower()
    assert body['details'] is None

def test_failed_risk_run_error_message_is_sanitized() -> None:

    class BoomService:

        def summary(self, portfolio, methodology=None):
            raise RuntimeError(_LEAK)
    repo = InMemoryRiskRunRepository()
    worker = RiskRunWorker(BoomService(), repo=repo, max_workers=1)
    view = worker.submit(portfolio=_tiny_portfolio(), run_type='summary')
    deadline = time.time() + 10.0
    last = None
    try:
        while time.time() < deadline:
            last = worker.get(view.id)
            if last.status in {RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}:
                break
            time.sleep(0.05)
    finally:
        worker.shutdown(wait=True)
    assert last is not None
    assert last.status == RiskRunStatus.FAILED
    assert last.error_message == PUBLIC_RISK_RUN_FAILURE_MESSAGE
    _assert_no_internal_leak(last.error_message)
