"""Cap/floor pricing conventions and reference checks for M1.9.

Rates, strikes, and volatility are decimals. Vega is reported per 1 vol point
(0.01 absolute volatility). The independent reference below is the same
Black-76 optionlet identity used for cap/floor market conventions; parity
tolerance is tight because both paths are deterministic double-precision math.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from types import SimpleNamespace

import pytest

from app.domain.models import CapFloorPosition, MarketSnapshot, Portfolio, SwaptionPosition
from app.market.demo_snapshot import SampleMarksRemovedError
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
        "option_type": "cap",
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
        "option_type": "payer",
        "payment_frequency_per_year": 2,
    }
    data.update(updates)
    return SwaptionPosition(**data)


def _ir_market(
    *,
    discount: float = 0.035,
    forward: float = 0.04,
    vol: float = 0.20,
    market_id: str = "ir-opt",
) -> MarketSnapshot:
    return MarketSnapshot(
        id=market_id,
        rates={"USD": discount},
        projection_rates={"USD": forward},
        ir_vols={"USD": vol},
    )


def _marks(forward: float, discount: float, volatility: float) -> SimpleNamespace:
    return SimpleNamespace(
        forward_rate=forward,
        forward_swap_rate=forward,
        discount_rate=discount,
        volatility=volatility,
    )


def _black76_strip_reference(p: CapFloorPosition, m: SimpleNamespace) -> float:
    periods = max(1, round(p.maturity_years * p.payment_frequency_per_year))
    accrual = p.maturity_years / periods
    unit_pv = 0.0
    for i in range(1, periods + 1):
        payment_time = i * accrual
        option_expiry = max(1.0 / 365.0, payment_time - accrual)
        df = math.exp(-m.discount_rate * payment_time)
        sqrt_t = math.sqrt(option_expiry)
        d1 = (
            math.log(m.forward_rate / p.strike)
            + 0.5 * m.volatility * m.volatility * option_expiry
        ) / (m.volatility * sqrt_t)
        d2 = d1 - m.volatility * sqrt_t
        if p.option_type == "cap":
            optionlet = m.forward_rate * _N.cdf(d1) - p.strike * _N.cdf(d2)
        else:
            optionlet = p.strike * _N.cdf(-d2) - m.forward_rate * _N.cdf(-d1)
        unit_pv += df * accrual * optionlet
    return p.quantity * p.notional * unit_pv


def _swaption_black76_reference(p: SwaptionPosition, m: SimpleNamespace) -> float:
    periods = max(1, round(p.swap_tenor_years * p.payment_frequency_per_year))
    accrual = p.swap_tenor_years / periods
    annuity = sum(
        accrual * math.exp(-m.discount_rate * (p.option_maturity_years + i * accrual))
        for i in range(1, periods + 1)
    )
    sqrt_t = math.sqrt(p.option_maturity_years)
    d1 = (
        math.log(m.forward_swap_rate / p.strike)
        + 0.5 * m.volatility * m.volatility * p.option_maturity_years
    ) / (m.volatility * sqrt_t)
    d2 = d1 - m.volatility * sqrt_t
    if p.option_type == "payer":
        unit = m.forward_swap_rate * _N.cdf(d1) - p.strike * _N.cdf(d2)
    else:
        unit = p.strike * _N.cdf(-d2) - m.forward_swap_rate * _N.cdf(-d1)
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
    market = _ir_market()
    marks = _marks(0.04, 0.035, 0.20)

    valuation = BuiltinPricingEngine().value(cap, market)

    assert valuation.market_value == pytest.approx(
        _black76_strip_reference(cap, marks),
        rel=1e-12,
        abs=1e-8,
    )


def test_builtin_swaption_matches_independent_black76_reference():
    swaption = _swaption()
    market = _ir_market()
    marks = _marks(0.04, 0.035, 0.20)

    valuation = BuiltinPricingEngine().value(swaption, market)

    assert valuation.market_value == pytest.approx(
        _swaption_black76_reference(swaption, marks),
        rel=1e-12,
        abs=1e-8,
    )


def test_builtin_cap_floor_sign_and_parity_invariants():
    engine = BuiltinPricingEngine()
    market = _ir_market()
    cap = _cap(option_type="cap")
    floor = _cap(id="usd-floor", option_type="floor")

    cap_v = engine.value(cap, market)
    floor_v = engine.value(floor, market)

    assert cap_v.market_value > 0.0
    assert floor_v.market_value > 0.0
    assert cap_v.vega > 0.0
    assert floor_v.vega > 0.0
    # ATM cap and floor with identical flat forward/discount/vol assumptions
    # have equal Black-76 time value period-by-period.
    assert cap_v.market_value == pytest.approx(floor_v.market_value, rel=1e-12, abs=1e-8)


def test_builtin_swaption_payer_receiver_sign_and_parity_invariants():
    engine = BuiltinPricingEngine()
    market = _ir_market()
    payer = _swaption(option_type="payer")
    receiver = _swaption(id="usd-receiver-swaption", option_type="receiver")

    payer_v = engine.value(payer, market)
    receiver_v = engine.value(receiver, market)

    assert payer_v.market_value > 0.0
    assert receiver_v.market_value > 0.0
    assert payer_v.vega > 0.0
    assert receiver_v.vega > 0.0
    assert payer_v.market_value == pytest.approx(receiver_v.market_value, rel=1e-12, abs=1e-8)


def test_builtin_cap_floor_rate_and_vol_monotonicity():
    engine = BuiltinPricingEngine()
    cap = _cap()
    floor = _cap(id="usd-floor", option_type="floor")

    base_market = _ir_market(discount=0.04, forward=0.04, vol=0.20)
    higher_rate_market = _ir_market(discount=0.045, forward=0.045, vol=0.20)
    higher_vol_market = _ir_market(discount=0.04, forward=0.04, vol=0.25)

    assert engine.value(cap, higher_rate_market).market_value > engine.value(cap, base_market).market_value
    assert engine.value(floor, higher_rate_market).market_value < engine.value(floor, base_market).market_value
    assert engine.value(cap, higher_vol_market).market_value > engine.value(cap, base_market).market_value


def test_builtin_swaption_rate_and_vol_monotonicity():
    engine = BuiltinPricingEngine()
    payer = _swaption()
    receiver = _swaption(id="usd-receiver-swaption", option_type="receiver")

    base_market = _ir_market(discount=0.04, forward=0.04, vol=0.20)
    # Higher forward via projection; discount held at 0.04 (matches prior test shape).
    higher_rate_market = MarketSnapshot(
        id="swaption-fwd-up",
        rates={"USD": 0.04},
        projection_rates={"USD": 0.045},
        ir_vols={"USD": 0.20},
    )
    higher_vol_market = _ir_market(discount=0.04, forward=0.04, vol=0.25)

    assert engine.value(payer, higher_rate_market).market_value > engine.value(payer, base_market).market_value
    assert engine.value(receiver, higher_rate_market).market_value < engine.value(receiver, base_market).market_value
    assert engine.value(payer, higher_vol_market).market_value > engine.value(payer, base_market).market_value


def test_builtin_cap_floor_respects_snapshot_rate_inputs():
    engine = BuiltinPricingEngine()
    cap = _cap()
    base = _ir_market(discount=0.03, forward=0.04, vol=0.20)
    shocked = MarketSnapshot(
        id="cap-shock",
        rates={"USD": 0.03},
        projection_rates={"USD": 0.05},
        ir_vols={"USD": 0.20},
    )

    assert engine.value(cap, shocked).market_value > engine.value(cap, base).market_value


def test_builtin_swaption_respects_snapshot_rate_inputs():
    engine = BuiltinPricingEngine()
    payer = _swaption()
    base = _ir_market(discount=0.03, forward=0.04, vol=0.20)
    shocked = MarketSnapshot(
        id="swaption-shock",
        rates={"USD": 0.03},
        projection_rates={"USD": 0.05},
        ir_vols={"USD": 0.20},
    )

    assert engine.value(payer, shocked).market_value > engine.value(payer, base).market_value


def test_position_market_snapshot_no_longer_reads_cap_floor_marks():
    """Phase B: PositionMarketDataProvider cannot LWW marks from economics-only DTOs."""
    cap = _cap()
    with pytest.raises(SampleMarksRemovedError):
        PositionMarketDataProvider().snapshot(
            Portfolio(id="ir-options", name="IR Options", positions=[cap])
        )


def test_position_market_snapshot_no_longer_reads_swaption_marks():
    swaption = _swaption()
    with pytest.raises(SampleMarksRemovedError):
        PositionMarketDataProvider().snapshot(
            Portfolio(id="ir-options", name="IR Options", positions=[swaption])
        )


def test_explicit_cap_floor_market_preserves_forward_discount_and_vol():
    market = _ir_market(discount=0.03, forward=0.05, vol=0.20)
    assert market.rates["USD"] == pytest.approx(0.03)
    assert market.projection_rates["USD"] == pytest.approx(0.05)
    assert market.ir_vols["USD"] == pytest.approx(0.20)


def test_explicit_swaption_market_preserves_forward_discount_and_vol():
    market = _ir_market(discount=0.03, forward=0.05, vol=0.20)
    assert market.rates["USD"] == pytest.approx(0.03)
    assert market.projection_rates["USD"] == pytest.approx(0.05)
    assert market.ir_vols["USD"] == pytest.approx(0.20)
