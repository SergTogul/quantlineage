"""RF-001 Phase A: Builtin/QuantLib value() require an explicit MarketSnapshot."""

from __future__ import annotations

import pytest

from app.domain.models import EquityPosition, MarketSnapshot
from app.interfaces.pricing import LegacyDemoPricingAdapter
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine

MSG = "production risk calculation requires an explicit MarketSnapshot"


def _equity() -> EquityPosition:
    return EquityPosition(type="equity", id="e1", symbol="AAA", quantity=10.0, price=100.0)


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


def test_legacy_demo_adapter_still_prices_from_dto_marks() -> None:
    engine = BuiltinPricingEngine()
    pv = LegacyDemoPricingAdapter(engine).value(_equity()).market_value
    assert pv == pytest.approx(1000.0)


def test_builtin_value_with_explicit_snapshot_ignores_dto_price() -> None:
    engine = BuiltinPricingEngine()
    market = MarketSnapshot(id="m", equity_spots={"AAA": 50.0}, rates={"USD": 0.04})
    assert engine.value(_equity(), market).market_value == pytest.approx(500.0)
