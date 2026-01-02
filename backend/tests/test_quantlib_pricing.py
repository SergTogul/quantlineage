import math
from datetime import date

import pytest

ql = pytest.importorskip("QuantLib")

from app.domain.models import BondPosition, EquityPosition, EuropeanOptionPosition, StressScenario, SwapPosition
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine


@pytest.fixture
def engine():
    return QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))


def test_equity_value(engine):
    p = EquityPosition(type="equity", id="e", symbol="ABC", quantity=10, price=25)
    v = engine.value(p)
    assert v.market_value == 250
    assert v.delta == 250


def test_european_option_matches_builtin_closely(engine):
    p = EuropeanOptionPosition(
        type="european_option", id="o", symbol="ABC", quantity=100,
        spot=100, strike=100, maturity_years=1, volatility=.2,
        risk_free_rate=.03, option_type="call"
    )
    ql_v = engine.value(p)
    builtin_v = BuiltinPricingEngine().value(p)
    assert ql_v.market_value == pytest.approx(builtin_v.market_value, rel=2e-3)
    assert ql_v.delta == pytest.approx(builtin_v.delta, rel=2e-3)
    assert ql_v.gamma == pytest.approx(builtin_v.gamma, rel=2e-3)
    assert ql_v.vega == pytest.approx(builtin_v.vega, rel=2e-3)


def test_long_zero_coupon_bond_has_negative_dv01(engine):
    p = BondPosition(type="bond", id="b", issuer="UST", face_value=1_000_000,
                     maturity_years=5, yield_rate=.04, duration=4.5)
    v = engine.value(p)
    assert v.market_value > 0
    assert v.dv01 < 0


def test_pay_fixed_swap_value_increases_when_rates_rise(engine):
    p = SwapPosition(type="swap", id="s", notional=1_000_000, maturity_years=5,
                     fixed_rate=.04, market_swap_rate=.04, pay_fixed=True, duration=4)
    base = engine.value(p).market_value
    higher = engine.value(p.model_copy(update={"market_swap_rate": .05})).market_value
    assert higher > base


def test_stress_revalues_option(engine):
    p = EuropeanOptionPosition(
        type="european_option", id="o", symbol="ABC", quantity=10,
        spot=100, strike=100, maturity_years=1, volatility=.2,
        risk_free_rate=.03, option_type="put"
    )
    scenario = StressScenario(name="down-vol-up", equity_shock=-.1, vol_shock=.25)
    assert engine.shocked_value(p, scenario) != engine.value(p).market_value
