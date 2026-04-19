"""R0.11.3 / RF-014: configurable HTTP workload caps (positions, scenarios, body size)."""
from __future__ import annotations
import asyncio
import json
from typing import Any
import pytest
from fastapi.testclient import TestClient
from app.api import workload as workload_mod
from app.api.errors import error_payload
from app.domain.models import EquityPosition, Portfolio
from app.main import app
from app.sample import SAMPLE_PORTFOLIO

def _assert_error_shape(body: dict[str, Any]) -> None:
    assert set(body.keys()) == {'code', 'message', 'details'}
    assert isinstance(body['code'], str) and body['code']
    assert isinstance(body['message'], str) and body['message']
    assert body['details'] is None or isinstance(body['details'], (dict, list))

def _equity(i: int) -> EquityPosition:
    return EquityPosition(type='equity', id=f'eq-{i}', symbol='AAPL', quantity=1.0)

def _book(n: int) -> dict[str, Any]:
    return Portfolio(id='workload-book', name='Workload Book', positions=[_equity(i) for i in range(n)]).model_dump(mode='json')

def _scenario(i: int) -> dict[str, Any]:
    return {'name': f'S{i}', 'equity_shock': -0.01}

def test_default_caps_match_documented_env_defaults() -> None:
    assert workload_mod.DEFAULT_MAX_POSITIONS == 500
    assert workload_mod.DEFAULT_MAX_SCENARIOS == 50
    assert workload_mod.DEFAULT_MAX_REQUEST_BYTES == 1048576
    assert workload_mod.max_positions() == 500
    assert workload_mod.max_scenarios() == 50
    assert workload_mod.max_request_bytes() == 1048576

def test_caps_read_env_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RISKFORGE_MAX_POSITIONS', '3')
    monkeypatch.setenv('RISKFORGE_MAX_SCENARIOS', '7')
    monkeypatch.setenv('RISKFORGE_MAX_REQUEST_BYTES', '2048')
    assert workload_mod.max_positions() == 3
    assert workload_mod.max_scenarios() == 7
    assert workload_mod.max_request_bytes() == 2048

def test_invalid_or_non_positive_env_falls_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RISKFORGE_MAX_POSITIONS', 'nope')
    monkeypatch.setenv('RISKFORGE_MAX_SCENARIOS', '0')
    monkeypatch.setenv('RISKFORGE_MAX_REQUEST_BYTES', '-1')
    assert workload_mod.max_positions() == workload_mod.DEFAULT_MAX_POSITIONS
    assert workload_mod.max_scenarios() == workload_mod.DEFAULT_MAX_SCENARIOS
    assert workload_mod.max_request_bytes() == workload_mod.DEFAULT_MAX_REQUEST_BYTES

def test_payload_inspector_rejects_oversize_positions() -> None:
    with pytest.raises(workload_mod.WorkloadLimitExceeded) as exc:
        workload_mod.enforce_parsed_payload({'id': 'x', 'name': 'x', 'positions': [{}] * 3}, max_positions=2, max_scenarios=50)
    assert exc.value.field == 'positions'
    assert exc.value.actual == 3
    assert exc.value.limit == 2

def test_payload_inspector_rejects_nested_portfolio_positions() -> None:
    nested = {'previous_portfolio': _book(1), 'current_portfolio': _book(3)}
    with pytest.raises(workload_mod.WorkloadLimitExceeded) as exc:
        workload_mod.enforce_parsed_payload(nested, max_positions=2, max_scenarios=50)
    assert exc.value.field == 'positions'
    assert exc.value.actual == 3

def test_payload_inspector_rejects_scenarios_list_and_top_level_array() -> None:
    with pytest.raises(workload_mod.WorkloadLimitExceeded) as exc:
        workload_mod.enforce_parsed_payload({'portfolio': _book(1), 'scenarios': [_scenario(i) for i in range(3)]}, max_positions=500, max_scenarios=2)
    assert exc.value.field == 'scenarios'
    assert exc.value.actual == 3
    with pytest.raises(workload_mod.WorkloadLimitExceeded) as exc:
        workload_mod.enforce_parsed_payload([_scenario(i) for i in range(4)], max_positions=500, max_scenarios=3)
    assert exc.value.field == 'scenarios'
    assert exc.value.actual == 4

def test_payload_inspector_allows_sample_shaped_payloads() -> None:
    workload_mod.enforce_parsed_payload(SAMPLE_PORTFOLIO.model_dump(mode='json'), max_positions=500, max_scenarios=50)
    workload_mod.enforce_parsed_payload({'portfolio': SAMPLE_PORTFOLIO.model_dump(mode='json'), 'scenarios': [_scenario(0)]}, max_positions=500, max_scenarios=50)

def test_sample_portfolio_still_accepted_on_portfolio_bearing_routes() -> None:
    payload = SAMPLE_PORTFOLIO.model_dump(mode='json')
    with TestClient(app) as client:
        snapshot = client.post('/api/v1/market/snapshot', json=payload)
        summary = client.post('/api/v1/risk/summary', json=payload)
        custom = client.post('/api/v1/risk/stress/custom', json={'portfolio': payload, 'scenarios': [_scenario(0)]})
    assert snapshot.status_code == 200
    assert summary.status_code == 200
    assert custom.status_code == 200

def test_oversize_positions_rejected_with_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RISKFORGE_MAX_POSITIONS', '2')
    with TestClient(app) as client:
        resp = client.post('/api/v1/market/snapshot', json=_book(3))
    assert resp.status_code == 413
    body = resp.json()
    _assert_error_shape(body)
    assert body['code'] == 'payload_too_large'
    assert 'position' in body['message'].lower()
    assert isinstance(body['details'], dict)
    assert body['details']['limit'] == 2
    assert body['details']['actual'] == 3

def test_oversize_positions_rejected_on_legacy_risk_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """risk.py is not edited; the shared dependency still covers it."""
    monkeypatch.setenv('RISKFORGE_MAX_POSITIONS', '2')
    with TestClient(app) as client:
        resp = client.post('/risk/var', json=_book(3))
    assert resp.status_code == 413
    _assert_error_shape(resp.json())

def test_exactly_max_positions_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RISKFORGE_MAX_POSITIONS', '2')
    from app.api import deps
    from tests.market_fixtures import FixedMarketProvider, equity_spot_market
    previous = deps.portfolio_service.market_data
    deps.portfolio_service.market_data = FixedMarketProvider(equity_spot_market('AAPL', 190.0))
    try:
        with TestClient(app) as client:
            resp = client.post('/api/v1/market/snapshot', json=_book(2))
        assert resp.status_code == 200
    finally:
        deps.portfolio_service.market_data = previous

def test_oversize_scenarios_rejected_on_custom_stress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RISKFORGE_MAX_SCENARIOS', '1')
    payload = {'portfolio': _book(1), 'scenarios': [_scenario(0), _scenario(1)]}
    with TestClient(app) as client:
        resp = client.post('/api/v1/risk/stress/evaluate/custom', json=payload)
    assert resp.status_code == 413
    body = resp.json()
    _assert_error_shape(body)
    assert body['code'] == 'payload_too_large'
    assert 'scenario' in body['message'].lower()
    assert isinstance(body['details'], dict)
    assert body['details']['limit'] == 1
    assert body['details']['actual'] == 2

def test_oversized_request_body_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RISKFORGE_MAX_REQUEST_BYTES', '64')
    raw = b'{"id":"x","name":"x","positions":[],"pad":"' + b'a' * 200 + b'"}'
    with TestClient(app) as client:
        resp = client.post('/api/v1/market/snapshot', content=raw, headers={'Content-Type': 'application/json'})
    assert resp.status_code == 413
    body = resp.json()
    _assert_error_shape(body)
    assert body['code'] == 'payload_too_large'
    assert 'body' in body['message'].lower() or 'size' in body['message'].lower()
    assert isinstance(body['details'], dict)
    assert body['details']['limit'] == 64
    assert body['details']['actual'] >= 64

def test_get_routes_are_not_blocked() -> None:
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/api/v1/portfolio').status_code == 200

def test_workload_http_exception_uses_existing_envelope_helper() -> None:
    """Raised detail must be the same {code,message,details} shape errors.py expects."""
    exc = workload_mod.workload_http_exception(message='Request exceeds maximum positions', details={'field': 'positions', 'limit': 2, 'actual': 3})
    assert exc.status_code == 413
    assert exc.detail == error_payload(code='payload_too_large', message='Request exceeds maximum positions', details={'field': 'positions', 'limit': 2, 'actual': 3})

def test_payload_inspector_rejects_what_if_adds_that_grow_book_past_cap() -> None:
    """Computed book is positions plus add-with-position, not the positions list alone."""
    payload = {'portfolio': _book(1), 'changes': [{'operation': 'add', 'position': _equity(10).model_dump(mode='json')}, {'operation': 'add', 'position': _equity(11).model_dump(mode='json')}, {'operation': 'add', 'position': _equity(12).model_dump(mode='json')}]}
    with pytest.raises(workload_mod.WorkloadLimitExceeded) as exc:
        workload_mod.enforce_parsed_payload(payload, max_positions=2, max_scenarios=50)
    assert exc.value.field == 'positions'
    assert exc.value.actual == 4
    assert exc.value.limit == 2

def test_what_if_adds_over_position_cap_rejected_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RISKFORGE_MAX_POSITIONS', '2')
    payload = {'portfolio': _book(1), 'changes': [{'operation': 'add', 'position': _equity(10).model_dump(mode='json')}, {'operation': 'add', 'position': _equity(11).model_dump(mode='json')}, {'operation': 'add', 'position': _equity(12).model_dump(mode='json')}]}
    with TestClient(app) as client:
        resp = client.post('/api/v1/risk/what-if', json=payload)
    assert resp.status_code == 413
    body = resp.json()
    _assert_error_shape(body)
    assert body['code'] == 'payload_too_large'
    assert 'position' in body['message'].lower()
    assert isinstance(body['details'], dict)
    assert body['details']['limit'] == 2
    assert body['details']['actual'] == 4

def _padded_snapshot_bytes(target: int) -> bytes:
    """Valid Portfolio JSON of at least ``target`` bytes (typed-body fixture)."""
    book = _book(0)
    pad = max(target, 1)
    while True:
        book['name'] = 'n' * pad
        raw = json.dumps(book, separators=(',', ':')).encode()
        if len(raw) >= target:
            return raw
        pad += target - len(raw)

def _asgi_post_chunked_typed_body(chunks: list[bytes], *, path: str='/api/v1/market/snapshot') -> tuple[int, dict[str, Any], list[tuple[int, bool]]]:
    """Full-app ASGI POST with no Content-Length; log every raw receive.

    Hits the live FastAPI app (typed ``Portfolio`` body on market/snapshot).
    Must not construct a bare ``Request`` or call ``enforce_workload_limits``.
    """
    receive_log: list[tuple[int, bool]] = []
    chunk_iter = iter(chunks)

    async def receive() -> dict[str, Any]:
        try:
            chunk = next(chunk_iter)
            more = True
        except StopIteration:
            chunk = b''
            more = False
        receive_log.append((len(chunk), more))
        return {'type': 'http.request', 'body': chunk, 'more_body': more}
    messages: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)
    scope: dict[str, Any] = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST', 'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'query_string': b'', 'headers': [(b'host', b'test'), (b'content-type', b'application/json')], 'client': ('testclient', 50000), 'server': ('testserver', 80), 'state': {}}

    async def _invoke() -> None:
        await app(scope, receive, send)
    with TestClient(app):
        asyncio.run(_invoke())
    status = next((m['status'] for m in messages if m['type'] == 'http.response.start'))
    raw = b''.join((m.get('body', b'') for m in messages if m['type'] == 'http.response.body'))
    parsed: dict[str, Any] = json.loads(raw) if raw else {}
    return (status, parsed, receive_log)

def test_full_app_chunked_typed_body_stops_before_fastapi_joins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live ``POST /api/v1/market/snapshot``: cap on ASGI receive, not after Pydantic.

    Acc 5 / Finding 2. No Content-Length. Valid JSON offered in 80-byte chunks
    (270-byte body). A post-join cap 413s with ``actual=270`` after draining
    every chunk. A stream cap 413s after the first oversize chunk and does not
    retain the tail.
    """
    monkeypatch.setenv('RISKFORGE_MAX_REQUEST_BYTES', '64')
    raw = _padded_snapshot_bytes(270)
    assert len(raw) >= 270
    chunks = [raw[i:i + 80] for i in range(0, len(raw), 80)]
    assert len(chunks) >= 4
    offered = sum((len(c) for c in chunks))
    status, body, receive_log = _asgi_post_chunked_typed_body(chunks)
    assert status == 413
    _assert_error_shape(body)
    assert body['code'] == 'payload_too_large'
    assert isinstance(body['details'], dict)
    assert body['details']['field'] == 'body'
    assert body['details']['limit'] == 64
    assert body['details']['actual'] != offered
    assert body['details']['actual'] <= 80
    received_body = sum((n for n, _ in receive_log if n))
    assert receive_log[0] == (80, True)
    assert received_body == 80
    assert received_body < offered
    assert len(receive_log) == 1

def test_full_app_chunked_invalid_json_over_cap_is_413_not_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid JSON over the byte cap must 413 on the live typed-body route.

    FastAPI body parsing first yields 422 and never runs the dependency.
    """
    monkeypatch.setenv('RISKFORGE_MAX_REQUEST_BYTES', '64')
    chunks = [b'x' * 80, b'x' * 80, b'x' * 80, b'x' * 5]
    offered = sum((len(c) for c in chunks))
    status, body, receive_log = _asgi_post_chunked_typed_body(chunks)
    assert status == 413
    assert status != 422
    _assert_error_shape(body)
    assert body['code'] == 'payload_too_large'
    assert isinstance(body['details'], dict)
    assert body['details']['actual'] != offered
    assert body['details']['actual'] <= 80
    received_body = sum((n for n, _ in receive_log if n))
    assert receive_log[0] == (80, True)
    assert received_body == 80
    assert len(receive_log) == 1

def test_deeply_nested_json_under_byte_cap_is_not_500() -> None:
    node: dict[str, Any] = {}
    for _ in range(1200):
        node = {'a': node}
    raw = json.dumps(node).encode()
    assert len(raw) < workload_mod.DEFAULT_MAX_REQUEST_BYTES
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post('/api/v1/market/snapshot', content=raw, headers={'Content-Type': 'application/json'})
    assert resp.status_code != 500
    assert resp.status_code in {413, 422}
    _assert_error_shape(resp.json())
