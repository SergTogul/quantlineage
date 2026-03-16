"""Golden / reference QuantLib comparisons (M1.8 baseline + M9.4 expand).

Uses ``tests.quantlib_gate.import_quantlib`` so environments without QuantLib
still skip these goldens, unless ``RISKFORGE_REQUIRE_QUANTLIB=1`` (R0.1.6).

Numerical conventions (documented for M9.4)
-------------------------------------------
- **Day count / discounting (QL adapter):** FlatForward continuous zeros with
  ``Actual365Fixed``; maturity dates are ``eval + max(1, round(T*365))`` calendar
  days (NullCalendar). Sub-day ``T < ~1/365`` clamps exercise to **1 calendar day**.
- **Equity / FX options:** Analytic Black–Scholes / Garman–Kohlhagen via
  QuantLib ``AnalyticEuropeanEngine``. Closed-form references use
  ``statistics.NormalDist`` (independent of both adapters). Date-rounded
  exercise vs continuous ``T`` ⇒ relative band **rel=2e-3** (abs=1e-6).
- **Equity future / FX forward:** Algebraic CIP via QL FlatForward DFs with
  **Time(years)** discount — identical to Builtin ⇒ **rel=1e-12, abs=1e-9**.
- **IR future:** Algebraic STIR mark ``qty * pv01 * (quoted - forward) * 1e4``
  (same formula in both engines) ⇒ **rel=1e-12, abs=1e-9**.
- **ZC bond (M1.12 closed):** Both adapters use continuous compounding. QuantLib
  ``ZeroCouponBond`` + ``FlatForward(Continuous, Actual365Fixed)`` discounts on
  calendar-rounded maturity ``eval + max(1, round(T*365))``. Builtin scalar
  (no curve) uses the same year fraction ``max(1, round(T*365))/365`` and
  ``face * exp(-y * t_act)`` ⇒ **rel=1e-10** vs QL and vs continuous golden.
  With curves attached, Builtin still discounts at domain ``maturity_years``
  pillar T (curve scaffold); that path is covered in ``test_curve_pricing.py``.
  Historical annual compound ``face/(1+y)^T`` is **not** a reference.
- **IRS:** QL VanillaSwap (payer when ``pay_fixed=True``); at-market PV residual
  from Actual365Fixed fixed vs Actual360 float on a flat curve is **< 50bp of
  notional** (not machine-zero). Sign/monotonicity vs Builtin annuity model
  (not NPV-identical).
- Evaluation date is pinned per fixture (no wall-clock flakiness).
  Very short option tenors (``T ≲ 0.05``) amplify date-rounding vs continuous
  analytic; those cases live in ``test_quantlib_pricing.py`` with documented
  wider bands / clamp policy — not asserted here at 2e-3.

References: QuantLib AnalyticEuropeanEngine / DiscountingBondEngine / FlatForward;
algebraic CIP and STIR identities shared with ``BuiltinPricingEngine``.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import NormalDist

import pytest
from tests.quantlib_gate import import_quantlib

ql = import_quantlib()

from app.domain.models import (
    BondPosition,
    EquityFuturePosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    SwapPosition,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine

_N = NormalDist()

# Shared tolerance bands (see module docstring).
_OPT_REL = 2e-3
_OPT_ABS = 1e-6
_CIP_REL = 1e-12
_CIP_ABS = 1e-9
_BOND_CONTINUOUS_REL = 1e-10


def _bs_price(spot, strike, t, r, q, vol, option_type: str) -> float:
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (r - q + 0.5 * vol * vol) * t) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    df_r, df_q = math.exp(-r * t), math.exp(-q * t)
    if option_type == "call":
        return spot * df_q * _N.cdf(d1) - strike * df_r * _N.cdf(d2)
    return strike * df_r * _N.cdf(-d2) - spot * df_q * _N.cdf(-d1)


def _gk_price(spot, strike, t, rd, rf, vol, option_type: str) -> float:
    """Garman–Kohlhagen unit FX option premium (domestic per unit foreign)."""
    return _bs_price(spot, strike, t, rd, rf, vol, option_type)


def _ql_date(d: date):
    return ql.Date(d.day, d.month, d.year)


def _maturity_calendar_days(eval_date: date, years: float) -> date:
    """Mirror QuantLibPricingEngine._maturity_date (NullCalendar + round)."""
    days = max(1, round(years * 365.0))
    return eval_date + timedelta(days=days)


def _continuous_zc_bond_pv(face: float, y: float, eval_date: date, years: float) -> float:
    """Continuous Actual365Fixed DF on calendar-rounded maturity (QL bond convention)."""
    mat = _maturity_calendar_days(eval_date, years)
    dc = ql.Actual365Fixed()
    t_act = dc.yearFraction(_ql_date(eval_date), _ql_date(mat))
    return face * math.exp(-y * t_act)


@pytest.fixture
def eval_date() -> date:
    return date(2026, 9, 1)


@pytest.fixture
def ql_engine(eval_date):
    return QuantLibPricingEngine(evaluation_date=eval_date)


# ---------------------------------------------------------------------------
# Equity options — analytic BS + Builtin cross-check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "option_type,spot,strike,t,vol,r,q,qty",
    [
        ("call", 100.0, 100.0, 1.0, 0.20, 0.03, 0.0, 100.0),
        ("put", 100.0, 100.0, 1.0, 0.20, 0.03, 0.0, 50.0),
        ("call", 120.0, 100.0, 0.5, 0.25, 0.01, 0.02, 10.0),
        ("put", 80.0, 100.0, 0.75, 0.30, 0.04, 0.01, 25.0),
        # Deep ITM / OTM + non-integer tenor (calendar-day rounding stress)
        ("call", 150.0, 100.0, 0.37, 0.15, 0.02, 0.0, 5.0),
        ("put", 60.0, 100.0, 1.25, 0.35, 0.05, 0.02, 40.0),
        ("call", 100.0, 150.0, 2.0, 0.40, 0.01, 0.01, 20.0),
        ("put", 90.0, 100.0, 0.5, 0.25, 0.03, 0.0, 15.0),
    ],
)
def test_ql_option_matches_analytic_bs(ql_engine, option_type, spot, strike, t, vol, r, q, qty):
    p = EuropeanOptionPosition(
        type="european_option",
        id="golden-opt",
        symbol="XYZ",
        quantity=qty,
        spot=spot,
        strike=strike,
        maturity_years=t,
        volatility=vol,
        risk_free_rate=r,
        dividend_yield=q,
        option_type=option_type,
    )
    expected = qty * _bs_price(spot, strike, t, r, q, vol, option_type)
    v = ql_engine.value(p)
    assert v.market_value == pytest.approx(expected, rel=_OPT_REL, abs=_OPT_ABS)


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_ql_option_matches_builtin_golden(ql_engine, option_type):
    p = EuropeanOptionPosition(
        type="european_option",
        id="x",
        symbol="ABC",
        quantity=100,
        spot=100,
        strike=105,
        maturity_years=0.75,
        volatility=0.22,
        risk_free_rate=0.035,
        dividend_yield=0.01,
        option_type=option_type,
    )
    ql_v = ql_engine.value(p)
    bi_v = BuiltinPricingEngine().value(p)
    assert ql_v.market_value == pytest.approx(bi_v.market_value, rel=_OPT_REL)
    assert ql_v.delta == pytest.approx(bi_v.delta, rel=_OPT_REL)
    assert ql_v.gamma == pytest.approx(bi_v.gamma, rel=_OPT_REL)
    assert ql_v.vega == pytest.approx(bi_v.vega, rel=_OPT_REL)


@pytest.mark.parametrize(
    "eval_d",
    [
        date(2026, 9, 1),  # weekday baseline
        date(2026, 9, 5),  # Saturday (NullCalendar — still valid)
        date(2024, 2, 29),  # leap day
        date(2026, 12, 31),  # year-end
    ],
)
def test_ql_option_edge_evaluation_dates_match_analytic(eval_d):
    """Pinned eval dates (incl. weekend / leap day) — no wall-clock dependency."""
    engine = QuantLibPricingEngine(evaluation_date=eval_d)
    spot, strike, t, vol, r, q, qty = 100.0, 100.0, 0.5, 0.20, 0.03, 0.0, 10.0
    p = EuropeanOptionPosition(
        type="european_option",
        id="edge-date",
        symbol="XYZ",
        quantity=qty,
        spot=spot,
        strike=strike,
        maturity_years=t,
        volatility=vol,
        risk_free_rate=r,
        dividend_yield=q,
        option_type="call",
    )
    expected = qty * _bs_price(spot, strike, t, r, q, vol, "call")
    assert engine.value(p).market_value == pytest.approx(expected, rel=_OPT_REL, abs=_OPT_ABS)


def test_ql_option_near_one_day_tenor_finite(ql_engine):
    """T ≈ 1/365 → one calendar day exercise; premium finite and positive for ATM call."""
    t = 1.0 / 365.0
    p = EuropeanOptionPosition(
        type="european_option",
        id="1d",
        symbol="XYZ",
        quantity=1.0,
        spot=100.0,
        strike=100.0,
        maturity_years=t,
        volatility=0.25,
        risk_free_rate=0.03,
        option_type="call",
    )
    v = ql_engine.value(p)
    assert math.isfinite(v.market_value)
    assert v.market_value > 0.0
    # Analytic continuous-T reference still within option band (same calendar day).
    expected = _bs_price(100.0, 100.0, t, 0.03, 0.0, 0.25, "call")
    assert v.market_value == pytest.approx(expected, rel=_OPT_REL, abs=_OPT_ABS)


# ---------------------------------------------------------------------------
# Bond — continuous Actual365Fixed golden + Builtin↔QL scalar parity (M1.12)
# ---------------------------------------------------------------------------


def test_ql_zero_coupon_bond_matches_continuous_actual365(ql_engine, eval_date):
    """Tight golden: continuous Actual365Fixed on calendar-rounded maturity."""
    face, t, y = 1_000_000.0, 5.0, 0.04
    p = BondPosition(
        type="bond",
        id="b-cont",
        issuer="UST",
        face_value=face,
        maturity_years=t,
        yield_rate=y,
        duration=4.5,
    )
    expected = _continuous_zc_bond_pv(face, y, eval_date, t)
    v = ql_engine.value(p)
    assert v.market_value == pytest.approx(expected, rel=_BOND_CONTINUOUS_REL)
    assert v.dv01 < 0
    # Analytic 1bp bump on continuous DF
    bumped = _continuous_zc_bond_pv(face, y + 0.0001, eval_date, t)
    assert v.dv01 == pytest.approx(bumped - expected, rel=1e-8, abs=1e-4)


def test_builtin_ql_zero_coupon_bond_scalar_parity(ql_engine, eval_date):
    """M1.12: Builtin scalar continuous Act/365 Fixed matches QuantLib ZCB."""
    builtin = BuiltinPricingEngine()
    face, t, y = 1_000_000.0, 5.0, 0.04
    p = BondPosition(
        type="bond",
        id="b-parity",
        issuer="UST",
        face_value=face,
        maturity_years=t,
        yield_rate=y,
        duration=4.5,
    )
    # No curves → both engines on flat continuous yield.
    market = MarketSnapshot(id="flat", rates={"USD": y})
    ql_pv = ql_engine.value(p, market).market_value
    bi_pv = builtin.value(p, market).market_value
    expected = _continuous_zc_bond_pv(face, y, eval_date, t)
    assert ql_pv == pytest.approx(expected, rel=_BOND_CONTINUOUS_REL)
    assert bi_pv == pytest.approx(expected, rel=_BOND_CONTINUOUS_REL)
    assert bi_pv == pytest.approx(ql_pv, rel=_BOND_CONTINUOUS_REL)
    # Historical annual compound is no longer the Builtin convention.
    annual = face / ((1.0 + y) ** t)
    assert abs(bi_pv - expected) < abs(bi_pv - annual)


@pytest.mark.parametrize("years", [0.25, 1.0, 2.0, 7.0, 10.0])
def test_builtin_ql_bond_tenor_ladder_scalar_parity(ql_engine, eval_date, years):
    """Fractional and integer tenors: Builtin scalar ≡ QL continuous Act/365."""
    builtin = BuiltinPricingEngine()
    face, y = 500_000.0, 0.035
    p = BondPosition(
        type="bond",
        id=f"b-parity-{years}",
        issuer="UST",
        face_value=face,
        maturity_years=years,
        yield_rate=y,
        duration=max(0.1, years * 0.9),
    )
    expected = _continuous_zc_bond_pv(face, y, eval_date, years)
    ql_pv = ql_engine.value(p).market_value
    bi_pv = builtin.value(p).market_value
    assert ql_pv == pytest.approx(expected, rel=_BOND_CONTINUOUS_REL)
    assert bi_pv == pytest.approx(expected, rel=_BOND_CONTINUOUS_REL)
    assert bi_pv == pytest.approx(ql_pv, rel=_BOND_CONTINUOUS_REL)


@pytest.mark.parametrize("years", [0.25, 1.0, 2.0, 7.0, 10.0])
def test_ql_bond_tenor_ladder_matches_continuous(ql_engine, eval_date, years):
    face, y = 500_000.0, 0.035
    p = BondPosition(
        type="bond",
        id=f"b-{years}",
        issuer="UST",
        face_value=face,
        maturity_years=years,
        yield_rate=y,
        duration=max(0.1, years * 0.9),
    )
    expected = _continuous_zc_bond_pv(face, y, eval_date, years)
    assert ql_engine.value(p).market_value == pytest.approx(expected, rel=_BOND_CONTINUOUS_REL)


def test_ql_bond_higher_yield_lowers_pv(ql_engine):
    p = BondPosition(
        type="bond",
        id="b-y",
        issuer="UST",
        face_value=1_000_000.0,
        maturity_years=5.0,
        yield_rate=0.03,
        duration=4.5,
    )
    low = ql_engine.value(p).market_value
    high = ql_engine.value(p.model_copy(update={"yield_rate": 0.05})).market_value
    assert high < low


# ---------------------------------------------------------------------------
# IRS — payer / receiver economics (QL VanillaSwap; not Builtin NPV-identical)
# ---------------------------------------------------------------------------


def test_ql_pay_fixed_swap_rises_when_rates_rise(ql_engine):
    """QuantLib maps pay_fixed=True to standard payer economics."""
    p = SwapPosition(
        type="swap",
        id="s",
        notional=1_000_000,
        maturity_years=5,
        fixed_rate=0.04,
        market_swap_rate=0.04,
        pay_fixed=True,
        duration=4,
    )
    base = ql_engine.value(p).market_value
    higher = ql_engine.value(p.model_copy(update={"market_swap_rate": 0.05})).market_value
    assert higher > base


def test_ql_at_market_payer_swap_near_zero(ql_engine):
    """Flat curve + fixed=market: NPV residual from Actual365Fixed vs Actual360.

    Not expected to be machine-zero; document residual as fraction of notional
    (< 50bp of notional on a 5Y annual/semiannual VanillaSwap).
    """
    notional = 10_000_000.0
    p = SwapPosition(
        type="swap",
        id="s-atm",
        notional=notional,
        maturity_years=5,
        fixed_rate=0.04,
        market_swap_rate=0.04,
        pay_fixed=True,
        duration=4,
    )
    v = ql_engine.value(p)
    assert abs(v.market_value) / notional < 0.005
    assert v.dv01 > 0  # payer: +1bp rates → positive PV change


def test_ql_receive_fixed_opposite_payer(ql_engine):
    payer = SwapPosition(
        type="swap",
        id="pay",
        notional=1_000_000,
        maturity_years=5,
        fixed_rate=0.03,
        market_swap_rate=0.04,
        pay_fixed=True,
        duration=4,
    )
    receiver = payer.model_copy(update={"id": "rcv", "pay_fixed": False})
    pv_p = ql_engine.value(payer).market_value
    pv_r = ql_engine.value(receiver).market_value
    assert pv_p == pytest.approx(-pv_r, rel=1e-10, abs=1e-6)
    assert pv_p > 0  # pay fixed below market


@pytest.mark.parametrize("years", [1.0, 2.0, 10.0])
def test_ql_swap_tenors_payer_dv01_positive(ql_engine, years):
    p = SwapPosition(
        type="swap",
        id=f"s-{years}",
        notional=2_000_000,
        maturity_years=years,
        fixed_rate=0.04,
        market_swap_rate=0.04,
        pay_fixed=True,
        duration=max(0.5, years * 0.8),
    )
    assert ql_engine.value(p).dv01 > 0


# ---------------------------------------------------------------------------
# Equity future / FX forward — CIP algebraic identity (exact vs Builtin)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spot,mult,t,r,q,qty",
    [
        (500.0, 50.0, 0.25, 0.04, 0.01, 10.0),
        (100.0, 1.0, 1.0, 0.02, 0.0, -5.0),
        (2500.0, 5.0, 0.08, 0.05, 0.02, 2.0),
        (80.0, 100.0, 2.0, 0.01, 0.03, 1.0),  # q > r → forward < spot
    ],
)
def test_ql_equity_future_matches_cip_algebra(ql_engine, spot, mult, t, r, q, qty):
    p = EquityFuturePosition(
        type="equity_future",
        id="fut",
        symbol="IDX",
        quantity=qty,
        spot=spot,
        multiplier=mult,
        maturity_years=t,
        risk_free_rate=r,
        dividend_yield=q,
    )
    forward = spot * math.exp((r - q) * t)
    expected_mv = qty * mult * forward
    v = ql_engine.value(p)
    assert v.market_value == pytest.approx(expected_mv, rel=_CIP_REL, abs=_CIP_ABS)
    bi = BuiltinPricingEngine().value(p)
    assert v.market_value == pytest.approx(bi.market_value, rel=_CIP_REL, abs=_CIP_ABS)
    assert v.delta == pytest.approx(bi.delta, rel=_CIP_REL, abs=_CIP_ABS)
    assert v.dv01 == pytest.approx(expected_mv * t * 0.0001, rel=_CIP_REL, abs=_CIP_ABS)


@pytest.mark.parametrize(
    "spot,strike,t,rd,rf,notional",
    [
        (1.10, 1.105, 0.5, 0.04, 0.03, 1_000_000.0),
        (1.25, 1.25, 1.0, 0.02, 0.02, 500_000.0),  # ATM forward ≈ spot when rd=rf
        (150.0, 148.0, 0.25, 0.01, 0.05, 100_000.0),  # JPY-style level
        (0.85, 0.90, 2.0, 0.05, 0.01, 250_000.0),
    ],
)
def test_ql_fx_forward_matches_cip_algebra(ql_engine, spot, strike, t, rd, rf, notional):
    p = FXForwardPosition(
        type="fx_forward",
        id="fxf",
        pair="EURUSD",
        notional_base=notional,
        spot=spot,
        strike=strike,
        maturity_years=t,
        domestic_rate=rd,
        foreign_rate=rf,
    )
    forward = spot * math.exp((rd - rf) * t)
    expected = notional * (forward - strike) * math.exp(-rd * t)
    v = ql_engine.value(p)
    assert v.market_value == pytest.approx(expected, rel=_CIP_REL, abs=_CIP_ABS)
    bi = BuiltinPricingEngine().value(p)
    assert v.market_value == pytest.approx(bi.market_value, rel=_CIP_REL, abs=_CIP_ABS)
    assert v.fx_delta == pytest.approx(notional * spot, rel=_CIP_REL, abs=_CIP_ABS)


def test_ql_fx_forward_respects_market_snapshot(ql_engine):
    p = FXForwardPosition(
        type="fx_forward",
        id="fxf-mkt",
        pair="EURUSD",
        notional_base=1_000_000,
        spot=1.10,
        strike=1.10,
        maturity_years=1.0,
        domestic_rate=0.04,
        foreign_rate=0.03,
    )
    market = MarketSnapshot(
        fx_spots={"EURUSD": 1.20},
        rates={"USD": 0.05, "EUR": 0.02},
    )
    ql_v = ql_engine.value(p, market)
    bi_v = BuiltinPricingEngine().value(p, market)
    assert ql_v.market_value == pytest.approx(bi_v.market_value, rel=_CIP_REL, abs=_CIP_ABS)
    assert ql_v.market_value != pytest.approx(ql_engine.value(p).market_value, abs=1.0)


# ---------------------------------------------------------------------------
# FX options — Garman–Kohlhagen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_ql_fx_option_matches_garman_kohlhagen(ql_engine, option_type):
    notional, spot, strike, t, vol, rd, rf = 250_000.0, 1.10, 1.12, 0.4, 0.12, 0.04, 0.03
    p = FXOptionPosition(
        type="fx_option",
        id="fxo",
        pair="EURUSD",
        notional_base=notional,
        spot=spot,
        strike=strike,
        maturity_years=t,
        volatility=vol,
        domestic_rate=rd,
        foreign_rate=rf,
        option_type=option_type,
    )
    expected = notional * _gk_price(spot, strike, t, rd, rf, vol, option_type)
    v = ql_engine.value(p)
    assert v.market_value == pytest.approx(expected, rel=_OPT_REL, abs=_OPT_ABS)
    bi = BuiltinPricingEngine().value(p)
    assert v.market_value == pytest.approx(bi.market_value, rel=_OPT_REL)
    assert v.fx_delta == pytest.approx(bi.fx_delta, rel=_OPT_REL)


@pytest.mark.parametrize(
    "option_type,spot,strike,t",
    [
        ("call", 1.10, 1.00, 0.37),  # ITM call, non-integer T
        ("put", 1.10, 1.25, 1.5),
        ("call", 1.10, 1.10, 0.25),  # short-ish ATM (still within 2e-3 band)
    ],
)
def test_ql_fx_option_moneyness_ladder(ql_engine, option_type, spot, strike, t):
    notional, vol, rd, rf = 100_000.0, 0.15, 0.04, 0.02
    p = FXOptionPosition(
        type="fx_option",
        id="fxo-m",
        pair="EURUSD",
        notional_base=notional,
        spot=spot,
        strike=strike,
        maturity_years=t,
        volatility=vol,
        domestic_rate=rd,
        foreign_rate=rf,
        option_type=option_type,
    )
    expected = notional * _gk_price(spot, strike, t, rd, rf, vol, option_type)
    assert ql_engine.value(p).market_value == pytest.approx(expected, rel=_OPT_REL, abs=_OPT_ABS)


# ---------------------------------------------------------------------------
# IR future — algebraic STIR mark
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "qty,pv01,quoted,forward",
    [
        (10.0, 25.0, 0.042, 0.040),
        (-5.0, 25.0, 0.035, 0.040),
        (1.0, 12.5, 0.050, 0.050),  # flat → zero MV
    ],
)
def test_ql_ir_future_matches_stir_algebra(ql_engine, qty, pv01, quoted, forward):
    p = InterestRateFuturePosition(
        type="ir_future",
        id="ed",
        currency="USD",
        quantity=qty,
        pv01=pv01,
        quoted_rate=quoted,
        forward_rate=forward,
        maturity_years=0.25,
    )
    expected = qty * pv01 * (quoted - forward) * 10000.0
    v = ql_engine.value(p)
    assert v.market_value == pytest.approx(expected, rel=_CIP_REL, abs=_CIP_ABS)
    assert v.dv01 == pytest.approx(-qty * pv01, rel=_CIP_REL, abs=_CIP_ABS)
    bi = BuiltinPricingEngine().value(p)
    assert v.market_value == pytest.approx(bi.market_value, rel=_CIP_REL, abs=_CIP_ABS)


def test_ql_ir_future_higher_forward_lowers_long_mv(ql_engine):
    p = InterestRateFuturePosition(
        type="ir_future",
        id="ed2",
        currency="USD",
        quantity=10,
        pv01=25.0,
        quoted_rate=0.042,
        forward_rate=0.040,
        maturity_years=0.25,
    )
    base = ql_engine.value(p).market_value
    shocked = ql_engine.value(
        p, MarketSnapshot(rates={"USD": 0.045}, ir_future_quotes={"USD": 0.042})
    )
    assert shocked.market_value < base


# ---------------------------------------------------------------------------
# Determinism / PricingEngine seam
# ---------------------------------------------------------------------------


def test_ql_golden_deterministic_replay(ql_engine):
    """Same inputs → identical Valuation dump (no process-global date leakage)."""
    p = EuropeanOptionPosition(
        type="european_option",
        id="det",
        symbol="ABC",
        quantity=10,
        spot=100,
        strike=100,
        maturity_years=1.0,
        volatility=0.2,
        risk_free_rate=0.03,
        option_type="call",
    )
    a = ql_engine.value(p).model_dump()
    b = ql_engine.value(p).model_dump()
    assert a == b


def test_ql_engine_preserves_pricing_engine_interface(ql_engine):
    from app.interfaces.pricing import PricingEngine

    assert isinstance(ql_engine, PricingEngine)
    assert hasattr(ql_engine, "value") and hasattr(ql_engine, "shocked_value")
