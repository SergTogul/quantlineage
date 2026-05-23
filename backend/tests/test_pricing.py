import pytest
from tests.market_fixtures import equity_spot_market, usd_rate_market

from app.domain.models import (
    BondPosition,
    EquityPosition,
    EuropeanOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    SwapPosition,
)
from app.pricing.builtin import BuiltinPricingEngine

p = BuiltinPricingEngine()


def test_equity_value_and_delta():
    x = EquityPosition(type="equity", id="a", symbol="ABC", quantity=10)
    market = equity_spot_market("ABC", 25.0)
    v = p.value(x, market)
    assert v.market_value == 250
    assert v.delta == 250


def test_call_option_has_positive_gamma_and_vega():
    x = EuropeanOptionPosition(
        type="european_option",
        id="o",
        symbol="ABC",
        quantity=100,
        strike=100,
        maturity_years=1,
        option_type="call",
    )
    market = equity_spot_market("ABC", 100.0, rate=0.03, vol=0.2)
    v = p.value(x, market)
    assert v.market_value > 0
    assert v.delta > 0
    assert v.gamma > 0
    assert v.vega > 0


def test_put_delta_is_negative():
    x = EuropeanOptionPosition(
        type="european_option",
        id="o",
        symbol="ABC",
        quantity=10,
        strike=100,
        maturity_years=1,
        option_type="put",
    )
    market = equity_spot_market("ABC", 100.0, rate=0.03, vol=0.2)
    assert p.value(x, market).delta < 0


def test_bond_dv01_negative_for_long_bond():
    x = BondPosition(
        type="bond", id="b", issuer="UST", face_value=1000, maturity_years=5, duration=4.5
    )
    assert p.value(x, usd_rate_market(0.04)).dv01 < 0


def test_pay_fixed_swap_rises_when_market_rate_rises():
    """pay_fixed=True is standard payer economics (aligned with QuantLib)."""
    x = SwapPosition(
        type="swap",
        id="s",
        notional=1_000_000,
        maturity_years=5,
        fixed_rate=0.04,
        pay_fixed=True,
        duration=4,
    )
    base = p.value(x, usd_rate_market(0.04)).market_value
    shocked = p.value(x, usd_rate_market(0.05)).market_value
    assert shocked > base


def test_ir_future_long_loses_when_forward_rises():
    x = InterestRateFuturePosition(
        type="ir_future", id="ed", quantity=10, pv01=25.0, maturity_years=0.25
    )
    flat = MarketSnapshot(
        id="stir",
        rates={"USD": 0.04},
        projection_rates={"USD": 0.04},
        ir_future_quotes={"USD": 0.04},
    )
    base = p.value(x, flat)
    assert base.market_value == 0.0
    assert base.dv01 == -250.0
    higher = p.value(
        x,
        MarketSnapshot(
            id="stir-up",
            rates={"USD": 0.05},
            projection_rates={"USD": 0.05},
            ir_future_quotes={"USD": 0.04},
        ),
    )
    assert higher.market_value == pytest.approx(-10 * 25 * 0.01 * 10000)
