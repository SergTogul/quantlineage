"""Cap/floor pricing conventions and reference checks for M1.9.

Rates, strikes, and volatility are decimals. Vega is reported per 1 vol point
(0.01 absolute volatility). The independent reference below is the same
Black-76 optionlet identity used for cap/floor market conventions; parity
tolerance is tight because both paths are deterministic double-precision math.
"""

import math
from statistics import NormalDist

import pytest

from app.domain.models import CapFloorPosition, MarketSnapshot, Portfolio, SwaptionPosition
from app.market.snapshot import PositionMarketDataProvider
from app.pricing.builtin import BuiltinPricingEngine

_N = NormalDist()


def _cap(**updates) -> CapFloorPosition:
    data = {
        "type": "cap_floor",
        "id": "usd-cap",
        "currency": "USD",
        "notional": 1_000_000.0,
        "strike": 0.04,
        "maturity_years": 2.0,
        "volatility": 0.20,
        "option_type": "cap",
        "forward_rate": 0.04,
        "discount_rate": 0.035,
        "payment_frequency_per_year": 2,
    }
    data.update(updates)
    return CapFloorPosition(**data)


def _swaption(**updates) -> SwaptionPosition:
    data = {
        "type": "swaption",
        "id": "usd-payer-swaption",
        "currency": "USD",
        "notional": 1_000_000.0,
        "strike": 0.04,
        "option_maturity_years": 1.0,
        "swap_tenor_years": 5.0,
        "volatility": 0.20,
        "option_type": "payer",
        "forward_swap_rate": 0.04,
        "discount_rate": 0.035,
        "payment_frequency_per_year": 2,
    }
    data.update(updates)
    return SwaptionPosition(**data)


def _black76_strip_reference(p: CapFloorPosition) -> float:
    periods = max(1, round(p.maturity_years * p.payment_frequency_per_year))
    accrual = p.maturity_years / periods
    unit_pv = 0.0
    for i in range(1, periods + 1):
        payment_time = i * accrual
        option_expiry = max(1.0 / 365.0, payment_time - accrual)
        df = math.exp(-p.discount_rate * payment_time)
        sqrt_t = math.sqrt(option_expiry)
        d1 = (
            math.log(p.forward_rate / p.strike)
            + 0.5 * p.volatility * p.volatility * option_expiry
        ) / (p.volatility * sqrt_t)
        d2 = d1 - p.volatility * sqrt_t
        if p.option_type == "cap":
            optionlet = p.forward_rate * _N.cdf(d1) - p.strike * _N.cdf(d2)
        else:
            optionlet = p.strike * _N.cdf(-d2) - p.forward_rate * _N.cdf(-d1)
        unit_pv += df * accrual * optionlet
    return p.quantity * p.notional * unit_pv


def _swaption_black76_reference(p: SwaptionPosition) -> float:
    periods = max(1, round(p.swap_tenor_years * p.payment_frequency_per_year))
    accrual = p.swap_tenor_years / periods
    annuity = sum(
        accrual * math.exp(-p.discount_rate * (p.option_maturity_years + i * accrual))
        for i in range(1, periods + 1)
    )
    sqrt_t = math.sqrt(p.option_maturity_years)
    d1 = (
        math.log(p.forward_swap_rate / p.strike)
        + 0.5 * p.volatility * p.volatility * p.option_maturity_years
    ) / (p.volatility * sqrt_t)
    d2 = d1 - p.volatility * sqrt_t
    if p.option_type == "payer":
        unit = p.forward_swap_rate * _N.cdf(d1) - p.strike * _N.cdf(d2)
    else:
        unit = p.strike * _N.cdf(-d2) - p.forward_swap_rate * _N.cdf(-d1)
    return p.quantity * p.notional * annuity * unit


def test_cap_floor_position_round_trips_through_discriminated_union():
    portfolio = Portfolio(id="ir-options", name="IR Options", positions=[_cap()])

    restored = Portfolio.model_validate(portfolio.model_dump())

    assert isinstance(restored.positions[0], CapFloorPosition)
    assert restored.positions[0].option_type == "cap"


def test_swaption_position_round_trips_through_discriminated_union():
    portfolio = Portfolio(id="ir-options", name="IR Options", positions=[_swaption()])

    restored = Portfolio.model_validate(portfolio.model_dump())

    assert isinstance(restored.positions[0], SwaptionPosition)
    assert restored.positions[0].option_type == "payer"


def test_builtin_cap_floor_matches_independent_black76_reference():
    cap = _cap()

    valuation = BuiltinPricingEngine().value(cap)

    assert valuation.market_value == pytest.approx(
        _black76_strip_reference(cap),
        rel=1e-12,
        abs=1e-8,
    )


def test_builtin_swaption_matches_independent_black76_reference():
    swaption = _swaption()

    valuation = BuiltinPricingEngine().value(swaption)

    assert valuation.market_value == pytest.approx(
        _swaption_black76_reference(swaption),
        rel=1e-12,
        abs=1e-8,
    )


def test_builtin_cap_floor_sign_and_parity_invariants():
    engine = BuiltinPricingEngine()
    cap = _cap(option_type="cap")
    floor = _cap(id="usd-floor", option_type="floor")

    cap_v = engine.value(cap)
    floor_v = engine.value(floor)

    assert cap_v.market_value > 0.0
    assert floor_v.market_value > 0.0
    assert cap_v.vega > 0.0
    assert floor_v.vega > 0.0
    # ATM cap and floor with identical flat forward/discount/vol assumptions
    # have equal Black-76 time value period-by-period.
    assert cap_v.market_value == pytest.approx(floor_v.market_value, rel=1e-12, abs=1e-8)


def test_builtin_swaption_payer_receiver_sign_and_parity_invariants():
    engine = BuiltinPricingEngine()
    payer = _swaption(option_type="payer")
    receiver = _swaption(id="usd-receiver-swaption", option_type="receiver")

    payer_v = engine.value(payer)
    receiver_v = engine.value(receiver)

    assert payer_v.market_value > 0.0
    assert receiver_v.market_value > 0.0
    assert payer_v.vega > 0.0
    assert receiver_v.vega > 0.0
    assert payer_v.market_value == pytest.approx(receiver_v.market_value, rel=1e-12, abs=1e-8)


def test_builtin_cap_floor_rate_and_vol_monotonicity():
    engine = BuiltinPricingEngine()
    cap = _cap(forward_rate=0.04)
    floor = _cap(id="usd-floor", option_type="floor", forward_rate=0.04)

    higher_rate_market = MarketSnapshot(rates={"USD": 0.045}, projection_rates={"USD": 0.045})
    higher_vol_market = MarketSnapshot(rates={"USD": 0.04}, projection_rates={"USD": 0.04})

    assert engine.value(cap, higher_rate_market).market_value > engine.value(cap).market_value
    assert engine.value(floor, higher_rate_market).market_value < engine.value(floor).market_value
    assert engine.value(cap.model_copy(update={"volatility": 0.25}), higher_vol_market).market_value > (
        engine.value(cap, higher_vol_market).market_value
    )


def test_builtin_swaption_rate_and_vol_monotonicity():
    engine = BuiltinPricingEngine()
    payer = _swaption(forward_swap_rate=0.04)
    receiver = _swaption(id="usd-receiver-swaption", option_type="receiver", forward_swap_rate=0.04)

    higher_rate_market = MarketSnapshot(rates={"USD": 0.04}, projection_rates={"USD": 0.045})
    higher_vol_market = MarketSnapshot(rates={"USD": 0.04}, projection_rates={"USD": 0.04})

    assert engine.value(payer, higher_rate_market).market_value > engine.value(payer).market_value
    assert engine.value(receiver, higher_rate_market).market_value < engine.value(receiver).market_value
    assert engine.value(
        payer.model_copy(update={"volatility": 0.25}), higher_vol_market
    ).market_value > engine.value(payer, higher_vol_market).market_value


def test_builtin_cap_floor_respects_snapshot_rate_inputs():
    engine = BuiltinPricingEngine()
    cap = _cap(forward_rate=0.04, discount_rate=0.03)
    market = MarketSnapshot(rates={"USD": 0.03}, projection_rates={"USD": 0.05})

    base = engine.value(cap).market_value
    shocked = engine.value(cap, market).market_value

    assert shocked > base


def test_builtin_swaption_respects_snapshot_rate_inputs():
    engine = BuiltinPricingEngine()
    payer = _swaption(forward_swap_rate=0.04, discount_rate=0.03)
    market = MarketSnapshot(rates={"USD": 0.03}, projection_rates={"USD": 0.05})

    base = engine.value(payer).market_value
    shocked = engine.value(payer, market).market_value

    assert shocked > base


def test_position_market_snapshot_preserves_cap_floor_forward_and_discount_marks():
    cap = _cap(forward_rate=0.05, discount_rate=0.03)
    market = PositionMarketDataProvider().snapshot(
        Portfolio(id="ir-options", name="IR Options", positions=[cap])
    )

    assert market.rates["USD"] == pytest.approx(0.03)
    assert market.projection_rates["USD"] == pytest.approx(0.05)


def test_position_market_snapshot_preserves_swaption_forward_and_discount_marks():
    swaption = _swaption(forward_swap_rate=0.05, discount_rate=0.03)
    market = PositionMarketDataProvider().snapshot(
        Portfolio(id="ir-options", name="IR Options", positions=[swaption])
    )

    assert market.rates["USD"] == pytest.approx(0.03)
    assert market.projection_rates["USD"] == pytest.approx(0.05)
