"""Golden / reference QuantLib comparisons for M1.8.

Uses ``pytest.importorskip`` so environments without QuantLib still run the
Builtin property suite. Tolerances are relative unless noted; analytic Black–
Scholes references use a closed-form Normal CDF independent of the adapters.
"""

from __future__ import annotations

import math
from datetime import date
from statistics import NormalDist

import pytest

ql = pytest.importorskip("QuantLib")

from app.domain.models import BondPosition, EuropeanOptionPosition, FXOptionPosition, SwapPosition
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine

_N = NormalDist()


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


@pytest.fixture
def ql_engine():
    return QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))


@pytest.mark.parametrize(
    "option_type,spot,strike,t,vol,r,q,qty",
    [
        ("call", 100.0, 100.0, 1.0, 0.20, 0.03, 0.0, 100.0),
        ("put", 100.0, 100.0, 1.0, 0.20, 0.03, 0.0, 50.0),
        ("call", 120.0, 100.0, 0.5, 0.25, 0.01, 0.02, 10.0),
        ("put", 80.0, 100.0, 0.75, 0.30, 0.04, 0.01, 25.0),
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
    assert v.market_value == pytest.approx(expected, rel=2e-3, abs=1e-6)


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
    assert ql_v.market_value == pytest.approx(bi_v.market_value, rel=2e-3)
    assert ql_v.delta == pytest.approx(bi_v.delta, rel=2e-3)
    assert ql_v.gamma == pytest.approx(bi_v.gamma, rel=2e-3)
    assert ql_v.vega == pytest.approx(bi_v.vega, rel=2e-3)


def test_ql_zero_coupon_bond_pv_matches_discount_formula(ql_engine):
    face, t, y = 1_000_000.0, 5.0, 0.04
    p = BondPosition(
        type="bond",
        id="b",
        issuer="UST",
        face_value=face,
        maturity_years=t,
        yield_rate=y,
        duration=4.5,
    )
    expected = face / ((1.0 + y) ** t)
    # QuantLib uses continuous/Actual365 discounting; allow a wider band vs simple
    # compound reference while still checking scale and sign of DV01.
    v = ql_engine.value(p)
    assert v.market_value == pytest.approx(expected, rel=5e-2)
    assert v.market_value > 0
    assert v.dv01 < 0


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
    assert v.market_value == pytest.approx(expected, rel=2e-3, abs=1e-6)
    bi = BuiltinPricingEngine().value(p)
    assert v.market_value == pytest.approx(bi.market_value, rel=2e-3)
    assert v.fx_delta == pytest.approx(bi.fx_delta, rel=2e-3)
