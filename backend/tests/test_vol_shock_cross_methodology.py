"""Review Test D — relative EquityVol shocks are relative change of vol level.

Canonical convention (historical EquityVol / FXVol):
``new_vol = old_vol * (1 + relative_move)`` via ``MarketSnapshot.bump``.

Vega is quoted per 1 vol point (0.01 absolute vol). Approximate P&L must
convert relative moves with the base vol:

    absolute vol-point move = base_vol * relative_move * 100

Example: base_vol=0.20, relative_move=0.10 → 2.0 vol points, not 10.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.domain.models import EuropeanOptionPosition, MarketSnapshot, Portfolio, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_panel import HistoricalFactorPanel
from app.risk.factor_types import EquitySpot, EquityVol
from app.risk.historical import (
    approximate_pnl_series,
    approximate_position_pnls_from_panel,
)
from app.risk.scenarios import iter_panel_shocked_snapshots

_SYMBOL = "XYZ"
_BASE_VOL = 0.20
_RELATIVE_MOVE = 0.10
_VOL_POINTS = _BASE_VOL * _RELATIVE_MOVE * 100.0  # 2.0, not 10.0
_AS_OF = date(2024, 1, 2)


def _option() -> EuropeanOptionPosition:
    return EuropeanOptionPosition(
        type="european_option",
        id="call",
        symbol=_SYMBOL,
        quantity=10.0,
        strike=100.0,
        maturity_years=1.0,
        option_type="call",
    )


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        id="vol-cross",
        equity_spots={_SYMBOL: 100.0},
        equity_vols={_SYMBOL: _BASE_VOL},
        rates={"USD": 0.03},
        dividend_yields={_SYMBOL: 0.0},
    )


def _vol_panel() -> HistoricalFactorPanel:
    return HistoricalFactorPanel.from_pairs(
        dates=[_AS_OF],
        rows=[[(EquitySpot(_SYMBOL), 0.0), (EquityVol(underlying=_SYMBOL), _RELATIVE_MOVE)]],
    )


def test_full_revaluation_bump_and_panel_apply_vol_to_22_percent():
    """+10% relative of 20% vol → 22% (not +10 vol points to 30%)."""
    market = _market()
    shocked = market.bump(EquityVol(underlying=_SYMBOL), _RELATIVE_MOVE)
    assert shocked.equity_vols[_SYMBOL] == pytest.approx(0.22, abs=1e-12)
    assert shocked.equity_vols[_SYMBOL] != pytest.approx(0.30, abs=1e-12)

    panel_shocked = next(iter(iter_panel_shocked_snapshots(market, _vol_panel())))
    assert panel_shocked.equity_vols[_SYMBOL] == pytest.approx(0.22, abs=1e-12)


def test_linear_delta_gamma_vega_term_uses_two_vol_points_not_ten():
    """Approximate vega P&L ≈ vega * 2, not vega * 10."""
    pos = _option()
    market = _market()
    pricing = BuiltinPricingEngine()
    val = pricing.value(pos, market)
    zeros = np.array([0.0])
    expected = val.vega * _VOL_POINTS
    wrong_ten_points = val.vega * (_RELATIVE_MOVE * 100.0)
    assert pytest.approx(2.0, abs=1e-12) == _VOL_POINTS
    assert expected != pytest.approx(wrong_ten_points, abs=1e-9)

    for meth in (VaRMethodology.LINEAR, VaRMethodology.DELTA_GAMMA):
        pnl = approximate_pnl_series(
            delta=val.delta,
            gamma=val.gamma,
            vega=val.vega,
            dv01=val.dv01,
            fx_delta=val.fx_delta,
            equity_ret=zeros,
            vol_pct=np.array([_RELATIVE_MOVE]),
            rates_bps=zeros,
            fx_ret=zeros,
            methodology=meth,
            base_vol=_BASE_VOL,
            scenario_backend="python",
        )
        assert pnl[0] == pytest.approx(expected, rel=1e-12, abs=1e-9)
        assert pnl[0] != pytest.approx(wrong_ten_points, abs=1e-9)

    book = Portfolio(id="opt", name="opt", positions=[pos])
    by_pos = approximate_position_pnls_from_panel(
        book, pricing, market, _vol_panel(), methodology=VaRMethodology.LINEAR
    )
    assert by_pos[pos.id][0] == pytest.approx(expected, rel=1e-12, abs=1e-9)
    assert by_pos[pos.id][0] != pytest.approx(wrong_ten_points, abs=1e-9)


def test_forgotten_base_vol_yields_zero_vol_pnl():
    """Default base_vol=0 is safer than the old relative×100 bug."""
    pnl = approximate_pnl_series(
        delta=0.0,
        gamma=0.0,
        vega=25.0,
        dv01=0.0,
        fx_delta=0.0,
        equity_ret=np.array([0.0]),
        vol_pct=np.array([_RELATIVE_MOVE]),
        rates_bps=np.array([0.0]),
        fx_ret=np.array([0.0]),
        methodology=VaRMethodology.LINEAR,
        scenario_backend="python",
    )
    assert pnl[0] == pytest.approx(0.0, abs=1e-12)
    assert pnl[0] != pytest.approx(25.0 * 10.0, abs=1e-9)
