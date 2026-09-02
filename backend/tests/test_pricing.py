import math
from app.domain.models import BondPosition, EquityPosition, EuropeanOptionPosition, SwapPosition
from app.pricing.builtin import BuiltinPricingEngine

p = BuiltinPricingEngine()


def test_equity_value_and_delta():
    x = EquityPosition(type="equity", id="a", symbol="ABC", quantity=10, price=25)
    v = p.value(x)
    assert v.market_value == 250
    assert v.delta == 250


def test_call_option_has_positive_gamma_and_vega():
    x = EuropeanOptionPosition(type="european_option", id="o", symbol="ABC", quantity=100, spot=100, strike=100, maturity_years=1, volatility=.2, risk_free_rate=.03, option_type="call")
    v = p.value(x)
    assert v.market_value > 0
    assert v.delta > 0
    assert v.gamma > 0
    assert v.vega > 0


def test_put_delta_is_negative():
    x = EuropeanOptionPosition(type="european_option", id="o", symbol="ABC", quantity=10, spot=100, strike=100, maturity_years=1, volatility=.2, risk_free_rate=.03, option_type="put")
    assert p.value(x).delta < 0


def test_bond_dv01_negative_for_long_bond():
    x = BondPosition(type="bond", id="b", issuer="UST", face_value=1000, maturity_years=5, yield_rate=.04, duration=4.5)
    assert p.value(x).dv01 < 0


def test_pay_fixed_swap_rises_when_market_rate_falls():
    x = SwapPosition(type="swap", id="s", notional=1_000_000, maturity_years=5, fixed_rate=.04, market_swap_rate=.04, pay_fixed=True, duration=4)
    base = p.value(x).market_value
    shocked = p.value(x.model_copy(update={"market_swap_rate": .03})).market_value
    assert shocked > base
