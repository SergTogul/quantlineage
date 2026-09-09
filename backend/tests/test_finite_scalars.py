"""R0.11.2 / SEC-006: reject non-finite financial scalars at the domain/API boundary."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.models import (
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    MarketSnapshot,
    Portfolio,
)
from app.sample import DEMO_PORTFOLIOS, SAMPLE_PORTFOLIO


def _equity(*, quantity: float=10.0, price: float=100.0) -> EquityPosition:
    return EquityPosition(type='equity', id='eq-1', symbol='AAPL', quantity=quantity, price=price)

def test_equity_quantity_nan_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        EquityPosition(type='equity', id='eq-1', symbol='AAPL', quantity=float('nan'))

def test_equity_price_inf_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as exc:
        _equity(price=float('inf'))
    assert any(e.get('type') == 'extra_forbidden' for e in exc.value.errors())

def test_equity_price_negative_inf_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as exc:
        _equity(price=float('-inf'))
    assert any(e.get('type') == 'extra_forbidden' for e in exc.value.errors())

def test_maturity_years_inf_raises_even_when_gt_zero_would_pass() -> None:
    """Field(gt=0) is true for +Infinity; finiteness must still reject it."""
    with pytest.raises(ValidationError):
        EuropeanOptionPosition(type='european_option', id='opt-1', symbol='AAPL', quantity=1.0, strike=100.0, maturity_years=float('inf'), option_type='call')

def test_invalid_fx_pair_shape_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        FXForwardPosition(type='fx_forward', id='fxf-1', pair='not-a-pair', notional_base=1000000, strike=1.105, maturity_years=0.5)

def test_market_snapshot_rejects_invalid_fx_spot_pair_key() -> None:
    with pytest.raises(ValidationError):
        MarketSnapshot(fx_spots={'EUR/USD': 1.1}, rates={'USD': 0.04})

def test_market_snapshot_empty_fx_spots_remain_valid() -> None:
    snap = MarketSnapshot(fx_spots={}, rates={'USD': 0.04})
    assert dict(snap.fx_spots) == {}

def test_market_snapshot_rejects_non_finite_spot() -> None:
    with pytest.raises(ValidationError):
        MarketSnapshot(equity_spots={'AAPL': float('nan')})

def _var_body(*, quantity_token: str) -> bytes:
    payload = {'id': 'finite-scalar-book', 'name': 'Finite Scalar Book', 'positions': [{'type': 'equity', 'id': 'eq-1', 'symbol': 'AAPL', 'quantity': 10}]}
    raw = json.dumps(payload)
    return raw.replace('"quantity": 10', f'"quantity": {quantity_token}').encode()

def _assert_json_safe_validation_422(response) -> None:
    """422 envelope must be JSON-serializable (no raw NaN/Inf in details)."""
    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {'code', 'message', 'details'}
    assert body['code'] == 'validation_error'
    assert isinstance(body['message'], str) and body['message']
    assert isinstance(body['details'], dict)
    json.dumps(body, allow_nan=False)
    errors = body['details'].get('errors')
    assert isinstance(errors, list) and errors
    for err in errors:
        value = err.get('input') if isinstance(err, dict) else None
        if isinstance(value, float):
            assert value == value and abs(value) != float('inf')

@pytest.mark.parametrize('token', ['NaN', 'Infinity', '-Infinity'])
def test_var_endpoint_rejects_non_finite_json_price(token: str) -> None:
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/v1/risk/var', content=_var_body(quantity_token=token), headers={'Content-Type': 'application/json'})
    _assert_json_safe_validation_422(response)

def _tiny_portfolio() -> dict:
    return {'id': 'finite-scalar-book', 'name': 'Finite Scalar Book', 'positions': [{'type': 'equity', 'id': 'eq-1', 'symbol': 'AAPL', 'quantity': 10}]}

def _formal_custom_body(*, amount_token: str='-0.10', max_loss_token: str='0.05') -> bytes:
    payload = {'portfolio': _tiny_portfolio(), 'scenarios': [{'id': 'formal-finite', 'name': 'Formal finite', 'category': 'factor', 'shocks': [{'factor_type': 'equity', 'key': 'AAPL', 'amount': '__AMOUNT__', 'bucket': 'AAPL'}], 'max_loss_pct': '__MAX_LOSS__'}]}
    raw = json.dumps(payload)
    return raw.replace('"__AMOUNT__"', amount_token).replace('"__MAX_LOSS__"', max_loss_token).encode()
_FORMAL_ROUTES = ('/api/v1/risk/stress/formal/custom', '/api/v1/risk/stress/formal/evaluate/custom')

@pytest.mark.parametrize('path', _FORMAL_ROUTES)
@pytest.mark.parametrize('token', ['NaN', 'Infinity', '-Infinity'])
def test_formal_custom_rejects_non_finite_json_amount(path: str, token: str) -> None:
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(path, content=_formal_custom_body(amount_token=token), headers={'Content-Type': 'application/json'})
    _assert_json_safe_validation_422(response)

@pytest.mark.parametrize('path', _FORMAL_ROUTES)
@pytest.mark.parametrize('token', ['NaN', 'Infinity', '-Infinity'])
def test_formal_custom_rejects_non_finite_json_max_loss_pct(path: str, token: str) -> None:
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(path, content=_formal_custom_body(max_loss_token=token), headers={'Content-Type': 'application/json'})
    _assert_json_safe_validation_422(response)

def test_sample_and_demo_portfolios_still_validate() -> None:
    Portfolio.model_validate(SAMPLE_PORTFOLIO.model_dump())
    for portfolio in DEMO_PORTFOLIOS:
        Portfolio.model_validate(portfolio.model_dump())
