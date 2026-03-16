"""Curve / key-rate consumption in Builtin (+ QuantLib when installed) IR pricing.

Conventions
-----------
- Continuous zeros from ``MarketSnapshot.curves`` / ``key_rates`` (Actual/365-style).
- Without curves/key_rates, bonds use continuous compounding on Actual365Fixed
  year fraction ``max(1, round(T*365))/365`` (M1.12; matches QuantLib ZCB).
- Tenor ``RateZero`` bumps must change PV for maturity-matched instruments and
  leave off-pillar bumps ~flat (true isolation vs parallel).
"""

from __future__ import annotations

import math

import pytest

from app.domain.models import (
    BondPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    SwapPosition,
)
from app.market.curves import (
    CurveBootstrapInstrument,
    attach_bootstrapped_curve,
    attach_standard_usd_curves,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import RateZero

builtin = BuiltinPricingEngine()


def _bond_10y() -> BondPosition:
    return BondPosition(
        type="bond",
        id="b10",
        issuer="UST",
        face_value=1_000_000.0,
        quantity=1.0,
        maturity_years=10.0,
        yield_rate=0.04,
        duration=8.0,
    )


def _swap_5y() -> SwapPosition:
    return SwapPosition(
        type="swap",
        id="s5",
        notional=5_000_000.0,
        maturity_years=5.0,
        fixed_rate=0.04,
        market_swap_rate=0.04,
        pay_fixed=True,
        duration=4.3,
    )


def test_bond_falls_back_to_continuous_act365_without_curves():
    pos = _bond_10y()
    market = MarketSnapshot(id="flat", rates={"USD": 0.05})
    pv = builtin.value(pos, market).market_value
    # 10Y → round(10*365)/365 = 10 exactly; continuous DF.
    assert pv == pytest.approx(1_000_000.0 * math.exp(-0.05 * 10.0), rel=1e-12)


def test_bond_uses_continuous_df_when_usd_curves_attached():
    pos = _bond_10y()
    market = attach_standard_usd_curves(MarketSnapshot(id="c", rates={"USD": 0.04}), ois_rate=0.04)
    pv = builtin.value(pos, market).market_value
    assert pv == pytest.approx(1_000_000.0 * math.exp(-0.04 * 10.0), rel=1e-12)


def test_tenor_bump_changes_bond_pv_off_pillar_does_not():
    pos = _bond_10y()
    market = attach_standard_usd_curves(MarketSnapshot(id="c", rates={"USD": 0.04}), ois_rate=0.04)
    base = builtin.value(pos, market).market_value
    up_10 = builtin.value(pos, market.bump(RateZero("USD", "10Y"), 0.0025)).market_value
    up_2 = builtin.value(pos, market.bump(RateZero("USD", "2Y"), 0.0025)).market_value
    assert up_10 < base
    assert abs(base - up_10) > 100.0
    assert up_2 == pytest.approx(base, rel=1e-12)
    # Parallel moves PV at least as much as the maturity pillar on a flat curve.
    parallel = builtin.value(pos, market.bump(RateZero("USD", "PARALLEL"), 0.0025)).market_value
    assert abs(base - parallel) >= abs(base - up_10) - 1e-6


def test_tenor_bump_changes_swap_pv_differently_by_pillar():
    pos = _swap_5y()
    market = attach_standard_usd_curves(
        MarketSnapshot(id="c", rates={"USD": 0.04}), ois_rate=0.04, sofr_rate=0.041
    )
    base = builtin.value(pos, market).market_value
    up_5 = builtin.value(pos, market.bump(RateZero("USD", "5Y"), 0.0025)).market_value
    up_10 = builtin.value(pos, market.bump(RateZero("USD", "10Y"), 0.0025)).market_value
    # Payer: higher 5Y zero raises PV; 10Y pillar does not touch z(5).
    assert up_5 > base
    assert up_10 == pytest.approx(base, rel=1e-12)


def test_ir_future_uses_projection_curve_tenor():
    pos = InterestRateFuturePosition(
        type="ir_future",
        id="ed",
        quantity=10,
        pv01=25.0,
        quoted_rate=0.041,
        forward_rate=0.041,
        maturity_years=1.0,
    )
    market = attach_standard_usd_curves(
        MarketSnapshot(id="c", rates={"USD": 0.04}, ir_future_quotes={"USD": 0.041}),
        ois_rate=0.04,
        sofr_rate=0.041,
    )
    base = builtin.value(pos, market).market_value
    assert base == pytest.approx(0.0, abs=1e-9)
    up_1y = builtin.value(pos, market.bump(RateZero("USD", "1Y"), 0.0025)).market_value
    # Long STIR loses when forward rises; both OIS and SOFR zeros bump together.
    assert up_1y < base
    up_10 = builtin.value(pos, market.bump(RateZero("USD", "10Y"), 0.0025)).market_value
    # Maturity at 1Y node: 10Y pillar does not change z(1).
    assert up_10 == pytest.approx(base, rel=1e-12)


def test_bootstrapped_curve_feeds_builtin_bond_and_swap_pricing():
    market = attach_bootstrapped_curve(
        MarketSnapshot(id="boot", rates={"USD": 0.01}),
        currency="USD",
        curve_type="discount",
        name="USD_BOOT",
        instruments=[
            CurveBootstrapInstrument(kind="deposit", tenor="6M", rate=0.04),
            CurveBootstrapInstrument(kind="zero", tenor="1Y", rate=0.041),
            CurveBootstrapInstrument(kind="zero", tenor="2Y", rate=0.042),
            CurveBootstrapInstrument(kind="zero", tenor="5Y", rate=0.045),
        ],
    )

    bond = BondPosition(
        type="bond",
        id="b2",
        issuer="UST",
        face_value=1_000_000.0,
        quantity=1.0,
        maturity_years=2.0,
        yield_rate=0.01,
        duration=1.9,
    )
    swap = SwapPosition(
        type="swap",
        id="s5_boot",
        notional=5_000_000.0,
        maturity_years=5.0,
        fixed_rate=0.04,
        market_swap_rate=0.01,
        pay_fixed=True,
        duration=4.3,
    )

    assert builtin.value(bond, market).market_value == pytest.approx(1_000_000.0 * math.exp(-0.042 * 2.0))
    assert builtin.value(swap, market).market_value == pytest.approx((0.045 - 0.04) * 5_000_000.0 * 4.3)


@pytest.fixture
def ql_engine():
    from tests.quantlib_gate import import_quantlib

    import_quantlib()
    from app.pricing.quantlib import QuantLibPricingEngine

    return QuantLibPricingEngine()


def test_ql_tenor_bump_changes_bond_pv(ql_engine):
    pos = _bond_10y()
    market = attach_standard_usd_curves(MarketSnapshot(id="c", rates={"USD": 0.04}), ois_rate=0.04)
    base = ql_engine.value(pos, market).market_value
    up_10 = ql_engine.value(pos, market.bump(RateZero("USD", "10Y"), 0.0025)).market_value
    up_2 = ql_engine.value(pos, market.bump(RateZero("USD", "2Y"), 0.0025)).market_value
    assert up_10 < base
    assert abs(base - up_10) > 100.0
    assert up_2 == pytest.approx(base, rel=1e-8)
