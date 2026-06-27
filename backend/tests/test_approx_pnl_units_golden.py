"""R0.1.3 — exact one-factor approximate P&L unit goldens.

Pins the Historical VaR LINEAR / DELTA_GAMMA P&L contract in
``approximate_pnl_series`` (and the matching SensitivityEngine conventions).

Internal units (must not be confused at the call site). Conversions live in
``app.risk.shock_units`` — call sites must not inline ``* 100`` / ``/ 10_000``:

- equity / FX: relative return; ``0.01`` = +1%. Cash delta / FX delta.
- gamma: dollar gamma; DELTA_GAMMA adds ``0.5 * gamma * r^2``; LINEAR omits it.
- vol observations (``vol_pct`` / ``vol_moves``): relative vol move.
  Vega is quoted per 1 *vol point* (0.01 absolute vol). Conversion is
  ``base_vol * relative_move * 100`` via ``relative_vol_move_to_vol_points``.
  Example: base_vol=0.20, relative +4% (0.04) → 0.8 vol points.
- rates: ``rate_moves_bps`` are basis points; ``1.0`` = +1bp. DV01 is P&L per bp.
- SensitivityEngine rate bumps convert via ``bps_to_decimal_rate`` before
  ``MarketSnapshot.bump``.
- SensitivityEngine vol bumps are *absolute* decimal vol (``0.01`` = +1 vol point),
  which differs from ``MarketSnapshot.bump(EquityVol, amount)`` (relative).

These tests fail if DV01 is scaled ×100, vega is scaled ÷100, a percent is
treated as a whole number, or a bp is treated as a decimal rate.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    SwapPosition,
    VaRMethodology,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import RateZero
from app.risk.historical import approximate_pnl_series
from app.risk.sensitivities import SensitivityEngine

_PY = "python"


def _pnl(**kwargs) -> np.ndarray:
    n = 1
    zeros = dict(
        delta=0.0,
        gamma=0.0,
        vega=0.0,
        dv01=0.0,
        fx_delta=0.0,
        equity_ret=np.zeros(n),
        vol_pct=np.zeros(n),
        rates_bps=np.zeros(n),
        fx_ret=np.zeros(n),
        methodology=VaRMethodology.LINEAR,
        scenario_backend=_PY,
    )
    zeros.update(kwargs)
    return approximate_pnl_series(**zeros)


def test_equity_delta_relative_return_not_percent_points():
    """delta=100, r=-2% → P&L=-2. Treating -2 as a whole number yields -200."""
    pnl = _pnl(delta=100.0, equity_ret=np.array([-0.02]))
    assert pnl[0] == pytest.approx(-2.0, abs=1e-12)
    wrong_percent_as_whole = 100.0 * (-2.0)
    assert pnl[0] != pytest.approx(wrong_percent_as_whole, abs=1e-9)


def test_gamma_delta_gamma_term_is_half_gamma_r_squared():
    """DELTA_GAMMA: 0.5 * 40 * (0.10)**2 = 0.2. LINEAR must omit gamma."""
    r = np.array([0.10])
    dg = _pnl(gamma=40.0, equity_ret=r, methodology=VaRMethodology.DELTA_GAMMA)
    linear = _pnl(gamma=40.0, equity_ret=r, methodology=VaRMethodology.LINEAR)
    assert dg[0] == pytest.approx(0.2, abs=1e-12)
    assert linear[0] == pytest.approx(0.0, abs=1e-12)
    # Missing the 1/2 would yield 0.4.
    assert dg[0] != pytest.approx(40.0 * 0.10 * 0.10, abs=1e-9)


def test_vega_per_vol_point_uses_base_vol_times_relative_times_100():
    """vega=25 per vol point; relative +4% at base_vol=0.20 → 0.8 vol points → P&L=20.

    Old bug treated 0.04 relative as 4 vol points (P&L=100) with no base vol.
    """
    pnl = _pnl(vega=25.0, vol_pct=np.array([0.04]), base_vol=0.20)
    assert pnl[0] == pytest.approx(20.0, abs=1e-12)
    old_relative_times_100 = 25.0 * (0.04 * 100.0)
    assert pnl[0] != pytest.approx(old_relative_times_100, abs=1e-9)
    forgot_conversion = 25.0 * 0.04
    assert pnl[0] != pytest.approx(forgot_conversion, abs=1e-9)


def test_dv01_per_bp_not_times_100_or_decimal_rate():
    """dv01=-8.5 per bp; +10bp → P&L=-85.

    ×100 → -8500. Interpreting 10bp as 10% (0.10) or as 0.0010 decimal is wrong.
    """
    pnl = _pnl(dv01=-8.5, rates_bps=np.array([10.0]))
    assert pnl[0] == pytest.approx(-85.0, abs=1e-12)
    times_100 = -8.5 * 10.0 * 100.0
    bp_as_percent = -8.5 * 0.10
    bp_as_decimal_rate = -8.5 * (10.0 / 10_000.0)
    hundred_bp_as_100_percent = -8.5 * 1.0  # 100bp sent as 1.00
    assert pnl[0] != pytest.approx(times_100, abs=1e-9)
    assert pnl[0] != pytest.approx(bp_as_percent, abs=1e-9)
    assert pnl[0] != pytest.approx(bp_as_decimal_rate, abs=1e-9)
    # 100bp correct P&L vs 100bp-as-100% (1.0)
    pnl_100bp = _pnl(dv01=-8.5, rates_bps=np.array([100.0]))
    assert pnl_100bp[0] == pytest.approx(-850.0, abs=1e-12)
    assert pnl_100bp[0] != pytest.approx(hundred_bp_as_100_percent, abs=1e-9)


def test_fx_delta_relative_return_not_whole_percent():
    """fx_delta=50_000, FX -1% → P&L=-500. Sending 1.0 instead of 0.01 → -50_000."""
    pnl = _pnl(fx_delta=50_000.0, fx_ret=np.array([-0.01]))
    assert pnl[0] == pytest.approx(-500.0, abs=1e-12)
    percent_as_whole = 50_000.0 * (-1.0)
    assert pnl[0] != pytest.approx(percent_as_whole, abs=1e-9)


def test_combined_one_observation_is_sum_of_one_factor_terms():
    """Sanity: one-factor terms add; no hidden extra scale."""
    pnl = _pnl(
        delta=100.0,
        gamma=40.0,
        vega=25.0,
        dv01=-8.5,
        fx_delta=50_000.0,
        equity_ret=np.array([-0.02]),
        vol_pct=np.array([0.04]),
        rates_bps=np.array([10.0]),
        fx_ret=np.array([-0.01]),
        methodology=VaRMethodology.DELTA_GAMMA,
        base_vol=0.20,
    )
    expected = -2.0 + 0.5 * 40.0 * (-0.02) ** 2 + 20.0 + (-85.0) + (-500.0)
    assert pnl[0] == pytest.approx(expected, abs=1e-12)


def test_key_rate_dv01_is_exact_swap_annuity_times_one_bp():
    """Builtin payer swap: DV01 = notional × duration × 0.0001; +1bp 5Y P&L equals that."""
    pos = SwapPosition(
        type="swap",
        id="s",
        notional=5_000_000,
        maturity_years=5.0,
        fixed_rate=0.039,
        pay_fixed=True,
        duration=4.3,
    )
    market = MarketSnapshot(
        id="kr-swap-units",
        rates={"USD": 0.041},
        key_rates={"USD": {"5Y": 0.041, "10Y": 0.04}},
    )
    pricing = BuiltinPricingEngine()
    hand_dv01 = 5_000_000.0 * 4.3 * 0.0001  # +2150
    assert pricing.value(pos, market).dv01 == pytest.approx(hand_dv01, abs=1e-9)

    engine = SensitivityEngine(rate_bump_bps=1.0)
    portfolio = Portfolio(id="p", name="p", positions=[pos])
    kr = [
        m
        for m in engine.calculate(
            portfolio, pricing, measures=("key_rate_dv01",), market=market
        )
        if m.factor == RateZero("USD", "5Y")
    ]
    assert len(kr) == 1
    assert kr[0].unit == "per_bp"
    assert kr[0].value == pytest.approx(hand_dv01, abs=1e-9)

    base_pv = pricing.value(pos, market).market_value
    pnl_1bp = pricing.value(pos, market.bump(RateZero("USD", "5Y"), 0.0001)).market_value - base_pv
    assert pnl_1bp == pytest.approx(hand_dv01, abs=1e-9)

    pnl_off_pillar = (
        pricing.value(pos, market.bump(RateZero("USD", "10Y"), 0.0001)).market_value - base_pv
    )
    assert pnl_off_pillar == pytest.approx(0.0, abs=1e-9)

    pnl_100bp = pricing.value(pos, market.bump(RateZero("USD", "5Y"), 0.01)).market_value - base_pv
    pnl_as_percent = pricing.value(pos, market.bump(RateZero("USD", "5Y"), 1.0)).market_value - base_pv
    assert pnl_100bp == pytest.approx(100.0 * hand_dv01, abs=1e-9)
    assert pnl_as_percent == pytest.approx(10_000.0 * hand_dv01, abs=1e-6)
    assert pnl_as_percent != pytest.approx(pnl_100bp, abs=1.0)


def test_swap_dv01_times_bps_matches_approximate_pnl():
    """Analytic swap DV01 × bp series is the approximate rate P&L (no ×100)."""
    pos = SwapPosition(
        type="swap",
        id="s",
        notional=5_000_000,
        maturity_years=5.0,
        fixed_rate=0.039,
        pay_fixed=True,
        duration=4.3,
    )
    market = MarketSnapshot(
        id="swap-dv01",
        rates={"USD": 0.041},
        key_rates={"USD": {"5Y": 0.041, "10Y": 0.04}},
    )
    pricing = BuiltinPricingEngine()
    dv01 = pricing.value(pos, market).dv01
    rates = np.array([1.0, 25.0, -10.0, 100.0])
    pnl = _pnl(dv01=dv01, rates_bps=rates)
    np.testing.assert_allclose(pnl, dv01 * rates, atol=1e-12)
    assert not np.allclose(pnl, dv01 * rates * 100.0)
