"""RF-001 Phase B: Position DTOs carry economics only; value() requires MarketSnapshot."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models import BondPosition, EquityPosition, MarketSnapshot, SwapPosition
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine

MSG = 'production risk calculation requires an explicit MarketSnapshot'

def _equity() -> EquityPosition:
    return EquityPosition(type='equity', id='e1', symbol='AAA', quantity=10.0)

def _equity_market(spot: float=100.0) -> MarketSnapshot:
    return MarketSnapshot(id='m', equity_spots={'AAA': spot}, rates={'USD': 0.04})

def test_builtin_value_omitted_market_raises() -> None:
    engine = BuiltinPricingEngine()
    with pytest.raises(ValueError, match=MSG):
        engine.value(_equity())

def test_builtin_value_market_none_raises() -> None:
    engine = BuiltinPricingEngine()
    with pytest.raises(ValueError, match=MSG):
        engine.value(_equity(), None)

def test_quantlib_value_omitted_market_raises() -> None:
    engine = QuantLibPricingEngine()
    with pytest.raises(ValueError, match=MSG):
        engine.value(_equity())

def test_quantlib_value_market_none_raises() -> None:
    engine = QuantLibPricingEngine()
    with pytest.raises(ValueError, match=MSG):
        engine.value(_equity(), None)

def test_builtin_value_with_explicit_snapshot() -> None:
    engine = BuiltinPricingEngine()
    assert engine.value(_equity(), _equity_market(50.0)).market_value == pytest.approx(500.0)

def test_position_dto_rejects_embedded_mark_fields() -> None:
    """RF-001 Phase B: competing USD rates cannot live on Position DTOs."""
    with pytest.raises(ValidationError) as bond_exc:
        BondPosition(
            type='bond',
            id='bond-usd',
            issuer='UST',
            face_value=1000000,
            maturity_years=2.0,
            duration=1.9,
            yield_rate=0.05,
        )
    assert any(e.get('type') == 'extra_forbidden' for e in bond_exc.value.errors())
    with pytest.raises(ValidationError) as swap_exc:
        SwapPosition(
            type='swap',
            id='swap-usd',
            notional=1000000,
            maturity_years=2.0,
            fixed_rate=0.04,
            duration=1.9,
            market_swap_rate=0.045,
        )
    assert any(e.get('type') == 'extra_forbidden' for e in swap_exc.value.errors())
    with pytest.raises(ValidationError) as eq_exc:
        EquityPosition(type='equity', id='e', symbol='AAA', quantity=1.0, price=100.0)
    assert any(e.get('type') == 'extra_forbidden' for e in eq_exc.value.errors())
    assert 'yield_rate' not in BondPosition.model_fields
    assert 'market_swap_rate' not in SwapPosition.model_fields
    assert 'price' not in EquityPosition.model_fields
