"""Pricing consumes MarketSnapshot.vol_surfaces when present.

Conventions
-----------
- Surface lookup: bilinear vol at (maturity_years, strike/spot).
- Absent surface → scalar equity_vols / fx_vols (or trade mark).
- ``MarketSnapshot.bump`` / ``apply`` rewrite attached grids for typed vol shocks;
  pricing always reads the grid payload when attached.
"""

from __future__ import annotations

import pytest

from app.domain.models import EuropeanOptionPosition, FXOptionPosition, MarketSnapshot
from app.market.vol_surfaces import (
    VolSurface,
    attach_vol_surface,
    build_equity_vol_surface,
    build_fx_vol_surface,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.surface_vol import option_vol_from_snapshot
from app.risk.factor_types import EquityVol, FXVol

try:
    from app.pricing.quantlib import QuantLibPricingEngine

    _ql_engine = QuantLibPricingEngine()
except Exception:  # noqa: BLE001 — optional local QuantLib
    _ql_engine = None


def _skewed_equity_surface(name: str = "ABC", atm: float = 0.20, skew: float = 0.50) -> VolSurface:
    """Non-flat smile: ATM unchanged, OTM/ITM wings tilted via skew_shock."""
    return build_equity_vol_surface(name, atm).skew_shock(skew)


def test_option_vol_fallback_without_surface():
    market = MarketSnapshot(equity_vols={"ABC": 0.22}, equity_spots={"ABC": 100.0})
    # Callers pass scalar equity_vols / fx_vols as fallback (engines do this).
    vol = option_vol_from_snapshot(
        market, name="ABC", maturity_years=1.0, strike=110.0, spot=100.0, fallback=0.22
    )
    assert vol == pytest.approx(0.22)
    assert market.vol_surfaces.get("ABC") is None


def test_builtin_equity_option_pv_differs_on_skewed_surface():
    """OTM call (K/S=1.1): skewed surface vol ≠ scalar ATM → PV must differ."""
    opt = EuropeanOptionPosition(
        type="european_option",
        id="o",
        symbol="ABC",
        quantity=1,
        spot=100.0,
        strike=110.0,
        maturity_years=1.0,
        volatility=0.20,
        risk_free_rate=0.03,
        option_type="call",
    )
    scalar = MarketSnapshot(
        equity_spots={"ABC": 100.0},
        equity_vols={"ABC": 0.20},
        rates={"USD": 0.03},
        dividend_yields={"ABC": 0.0},
    )
    skewed = _skewed_equity_surface("ABC", atm=0.20, skew=0.50)
    # ATM stays 0.20; moneyness 1.1 → 0.20 + 0.50*0.1 = 0.25
    assert skewed.vol(1.0, 1.1) == pytest.approx(0.25)
    assert skewed.atm_vol() == pytest.approx(0.20)

    with_surface = attach_vol_surface(scalar, skewed)
    engine = BuiltinPricingEngine()
    pv_scalar = engine.value(opt, scalar).market_value
    pv_surface = engine.value(opt, with_surface).market_value
    assert pv_surface != pytest.approx(pv_scalar)
    assert pv_surface > pv_scalar  # higher OTM vol → higher call premium


def test_builtin_flat_surface_matches_scalar_atm():
    opt = EuropeanOptionPosition(
        type="european_option",
        id="o",
        symbol="ABC",
        quantity=1,
        spot=100.0,
        strike=100.0,
        maturity_years=1.0,
        volatility=0.20,
        risk_free_rate=0.03,
        option_type="call",
    )
    scalar = MarketSnapshot(
        equity_spots={"ABC": 100.0},
        equity_vols={"ABC": 0.20},
        rates={"USD": 0.03},
        dividend_yields={"ABC": 0.0},
    )
    flat = attach_vol_surface(scalar, build_equity_vol_surface("ABC", 0.20))
    engine = BuiltinPricingEngine()
    assert engine.value(opt, flat).market_value == pytest.approx(engine.value(opt, scalar).market_value)


def test_builtin_flat_surfaces_match_scalar_after_typed_vol_apply():
    eq_opt = EuropeanOptionPosition(
        type="european_option",
        id="eqo",
        symbol="ABC",
        quantity=1,
        spot=100.0,
        strike=100.0,
        maturity_years=1.0,
        volatility=0.20,
        risk_free_rate=0.03,
        option_type="call",
    )
    fx_opt = FXOptionPosition(
        type="fx_option",
        id="fxo",
        pair="EURUSD",
        notional_base=1_000_000,
        spot=1.10,
        strike=1.10,
        maturity_years=1.0,
        volatility=0.10,
        domestic_rate=0.04,
        foreign_rate=0.03,
        option_type="call",
    )
    scalar = MarketSnapshot(
        equity_spots={"ABC": 100.0},
        equity_vols={"ABC": 0.20},
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.10},
        rates={"USD": 0.04, "EUR": 0.03},
        dividend_yields={"ABC": 0.0},
    )
    with_surfaces = attach_vol_surface(
        attach_vol_surface(scalar, build_equity_vol_surface("ABC", 0.20)),
        build_fx_vol_surface("EURUSD", 0.10),
    )

    bumped_scalar = scalar.apply([(EquityVol("ABC"), 0.25), (FXVol("EURUSD"), 0.25)])
    bumped_surfaces = with_surfaces.apply([(EquityVol("ABC"), 0.25), (FXVol("EURUSD"), 0.25)])

    engine = BuiltinPricingEngine()
    assert engine.value(eq_opt, bumped_surfaces).market_value == pytest.approx(
        engine.value(eq_opt, bumped_scalar).market_value
    )
    assert engine.value(fx_opt, bumped_surfaces).market_value == pytest.approx(
        engine.value(fx_opt, bumped_scalar).market_value
    )


def test_builtin_fx_option_pv_differs_on_skewed_surface():
    opt = FXOptionPosition(
        type="fx_option",
        id="fxo",
        pair="EURUSD",
        notional_base=1_000_000,
        spot=1.10,
        strike=1.21,  # moneyness ≈ 1.1
        maturity_years=1.0,
        volatility=0.10,
        domestic_rate=0.04,
        foreign_rate=0.03,
        option_type="call",
    )
    scalar = MarketSnapshot(
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.10},
        rates={"USD": 0.04, "EUR": 0.03},
    )
    skewed = build_fx_vol_surface("EURUSD", 0.10).skew_shock(0.50)
    with_surface = attach_vol_surface(scalar, skewed)
    engine = BuiltinPricingEngine()
    pv_scalar = engine.value(opt, scalar).market_value
    pv_surface = engine.value(opt, with_surface).market_value
    assert pv_surface != pytest.approx(pv_scalar)
    assert pv_surface > pv_scalar


@pytest.mark.skipif(_ql_engine is None, reason="QuantLib not available")
def test_quantlib_equity_option_pv_differs_on_skewed_surface():
    opt = EuropeanOptionPosition(
        type="european_option",
        id="o",
        symbol="ABC",
        quantity=1,
        spot=100.0,
        strike=110.0,
        maturity_years=1.0,
        volatility=0.20,
        risk_free_rate=0.03,
        option_type="call",
    )
    scalar = MarketSnapshot(
        equity_spots={"ABC": 100.0},
        equity_vols={"ABC": 0.20},
        rates={"USD": 0.03},
        dividend_yields={"ABC": 0.0},
    )
    with_surface = attach_vol_surface(scalar, _skewed_equity_surface("ABC", 0.20, 0.50))
    pv_scalar = _ql_engine.value(opt, scalar).market_value
    pv_surface = _ql_engine.value(opt, with_surface).market_value
    assert pv_surface != pytest.approx(pv_scalar)
    assert pv_surface > pv_scalar
