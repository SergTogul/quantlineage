"""R0.5.3 leftover — opt-in HistoricalFactorPanel wiring into historical risk.

Default ``HistoricalRiskEngine()`` / ``create_historical_dataset()`` stay on
``projection="four_macro_demo"``. This file exercises an explicit panel-backed
path so two names or two tenors can shock independently.

RF-005 stays open until the default production path uses the panel.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.domain.models import (
    BondPosition,
    EquityPosition,
    MarketSnapshot,
    Portfolio,
    VaRMethodology,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_panel import HistoricalFactorPanel
from app.risk.factor_types import EquitySpot, RateZero
from app.risk.historical import (
    HistoricalRiskEngine,
    approximate_pnl_from_panel,
    full_revaluation_pnl_from_panel,
)
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.scenarios import iter_panel_shocked_snapshots

AAA = EquitySpot("AAA")
BBB = EquitySpot("BBB")
USD_2Y = RateZero("USD", "2Y")
USD_10Y = RateZero("USD", "10Y")
AS_OF = date(2024, 1, 2)
PRICING = BuiltinPricingEngine()


def _equity_book() -> tuple[Portfolio, MarketSnapshot]:
    book = Portfolio(
        id="eq2",
        name="two equities",
        positions=[
            EquityPosition(type="equity", id="aaa", symbol="AAA", quantity=10.0, price=100.0),
            EquityPosition(type="equity", id="bbb", symbol="BBB", quantity=10.0, price=100.0),
        ],
    )
    market = MarketSnapshot(
        id="eq2",
        equity_spots={"AAA": 100.0, "BBB": 100.0},
        rates={"USD": 0.04},
    )
    return book, market


def _bond_book() -> tuple[Portfolio, MarketSnapshot]:
    book = Portfolio(
        id="rates2",
        name="two tenors",
        positions=[
            BondPosition(
                type="bond",
                id="usd2y",
                issuer="T2",
                face_value=100.0,
                quantity=1.0,
                maturity_years=2.0,
                yield_rate=0.03,
                duration=1.9,
                currency="USD",
            ),
            BondPosition(
                type="bond",
                id="usd10y",
                issuer="T10",
                face_value=100.0,
                quantity=1.0,
                maturity_years=10.0,
                yield_rate=0.04,
                duration=8.5,
                currency="USD",
            ),
        ],
    )
    market = MarketSnapshot(
        id="rates2",
        rates={"USD": 0.04},
        key_rates={"USD": {"2Y": 0.03, "10Y": 0.04}},
    )
    return book, market


def _equity_panel(*, aaa: float, bbb: float) -> HistoricalFactorPanel:
    return HistoricalFactorPanel.from_pairs(dates=[AS_OF], rows=[[(AAA, aaa), (BBB, bbb)]])


def _tenor_panel(*, usd2y: float, usd10y: float) -> HistoricalFactorPanel:
    return HistoricalFactorPanel.from_pairs(
        dates=[AS_OF],
        rows=[[(USD_2Y, usd2y), (USD_10Y, usd10y)]],
    )


def test_panel_shocked_snapshot_applies_independent_equity_returns():
    """AAA +10% and BBB −20% in one observation — not a broadcast."""
    _, market = _equity_book()
    panel = _equity_panel(aaa=0.10, bbb=-0.20)
    shocked = list(iter_panel_shocked_snapshots(market, panel))
    assert len(shocked) == 1
    assert shocked[0].equity_spots["AAA"] == pytest.approx(110.0)
    assert shocked[0].equity_spots["BBB"] == pytest.approx(80.0)
    assert shocked[0].equity_spots["AAA"] != shocked[0].equity_spots["BBB"]


def test_panel_shocked_snapshot_applies_independent_rate_tenors():
    """USD 2Y and USD 10Y receive different bp moves; scalar rates stay put."""
    _, market = _bond_book()
    panel = _tenor_panel(usd2y=10.0, usd10y=-25.0)
    shocked = list(iter_panel_shocked_snapshots(market, panel))
    assert len(shocked) == 1
    assert shocked[0].key_rates["USD"]["2Y"] == pytest.approx(0.031)
    assert shocked[0].key_rates["USD"]["10Y"] == pytest.approx(0.0375)
    assert shocked[0].key_rates["USD"]["2Y"] != shocked[0].key_rates["USD"]["10Y"]
    assert shocked[0].rates["USD"] == pytest.approx(0.04)


def test_approximate_pnl_from_panel_does_not_broadcast_equity_returns():
    book, market = _equity_book()
    aaa_ret, bbb_ret = 0.10, -0.20
    panel = _equity_panel(aaa=aaa_ret, bbb=bbb_ret)
    pnl = approximate_pnl_from_panel(
        book, PRICING, market, panel, methodology=VaRMethodology.LINEAR
    )
    vals = PRICING.value_portfolio(book, market)
    delta_aaa, delta_bbb = vals[0].delta, vals[1].delta
    expected = delta_aaa * aaa_ret + delta_bbb * bbb_ret
    broadcast_aaa = (delta_aaa + delta_bbb) * aaa_ret
    broadcast_bbb = (delta_aaa + delta_bbb) * bbb_ret
    assert pnl == pytest.approx(np.array([expected]), abs=1e-12)
    assert pnl[0] != pytest.approx(broadcast_aaa)
    assert pnl[0] != pytest.approx(broadcast_bbb)


def test_approximate_pnl_from_panel_does_not_broadcast_rate_tenors():
    book, market = _bond_book()
    bps_2y, bps_10y = 10.0, -25.0
    panel = _tenor_panel(usd2y=bps_2y, usd10y=bps_10y)
    pnl = approximate_pnl_from_panel(
        book, PRICING, market, panel, methodology=VaRMethodology.LINEAR
    )
    vals = PRICING.value_portfolio(book, market)
    dv01_2y, dv01_10y = vals[0].dv01, vals[1].dv01
    expected = dv01_2y * bps_2y + dv01_10y * bps_10y
    broadcast_2y = (dv01_2y + dv01_10y) * bps_2y
    broadcast_10y = (dv01_2y + dv01_10y) * bps_10y
    assert pnl == pytest.approx(np.array([expected]), abs=1e-12)
    assert pnl[0] != pytest.approx(broadcast_2y)
    assert pnl[0] != pytest.approx(broadcast_10y)


def test_full_revaluation_from_panel_does_not_broadcast_equity_returns():
    book, market = _equity_book()
    panel = _equity_panel(aaa=0.10, bbb=-0.20)
    pnl = full_revaluation_pnl_from_panel(book, PRICING, market, panel)
    # qty=10, spot=100 → AAA 110 (−wait) 10*110-10*100=+100; BBB 10*80-10*100=-200
    assert pnl == pytest.approx(np.array([-100.0]), abs=1e-12)
    broadcast_aaa = np.array([200.0])  # both names +10%
    broadcast_bbb = np.array([-400.0])  # both names −20%
    assert pnl[0] != pytest.approx(broadcast_aaa[0])
    assert pnl[0] != pytest.approx(broadcast_bbb[0])


def test_missing_required_equity_factor_fails_closed():
    """Panel supplied but BBB history missing — do not treat as 0."""
    book, market = _equity_book()
    panel = HistoricalFactorPanel.from_pairs(dates=[AS_OF], rows=[[(AAA, 0.10)]])
    with pytest.raises(ValueError, match="missing required factor"):
        approximate_pnl_from_panel(
            book, PRICING, market, panel, methodology=VaRMethodology.LINEAR
        )
    with pytest.raises(ValueError, match="missing required factor"):
        full_revaluation_pnl_from_panel(book, PRICING, market, panel)


def test_missing_required_rate_tenor_fails_closed():
    book, market = _bond_book()
    panel = HistoricalFactorPanel.from_pairs(dates=[AS_OF], rows=[[(USD_2Y, 10.0)]])
    with pytest.raises(ValueError, match="missing required factor"):
        approximate_pnl_from_panel(
            book, PRICING, market, panel, methodology=VaRMethodology.LINEAR
        )


def test_default_historical_engine_has_no_panel_and_broadcasts():
    """Default constructor still uses four-macro factor_observations()."""
    engine = HistoricalRiskEngine()
    assert engine.factor_panel is None
    book, market = _equity_book()
    series = FactorObservationSeries(
        equity_returns=np.array([-0.10]),
        vol_moves=np.array([0.0]),
        rate_moves_bps=np.array([0.0]),
        fx_returns=np.array([0.0]),
    )
    default = HistoricalRiskEngine(
        dataset=ArrayHistoricalDataset(series),
        methodology=VaRMethodology.LINEAR,
    )
    assert default.factor_panel is None
    result = default.calculate(book, PRICING, market=market)
    vals = PRICING.value_portfolio(book, market)
    # One aggregate equity return is applied to the sum of cash deltas.
    broadcast_pnl = (vals[0].delta + vals[1].delta) * -0.10
    assert broadcast_pnl < 0.0
    assert result["var_95"] == pytest.approx(-broadcast_pnl, abs=1e-12)


def test_engine_with_factor_panel_uses_per_name_moves():
    book, market = _equity_book()
    panel = _equity_panel(aaa=0.10, bbb=-0.20)
    engine = HistoricalRiskEngine(
        factor_panel=panel,
        methodology=VaRMethodology.LINEAR,
    )
    result = engine.calculate(book, PRICING, market=market)
    vals = PRICING.value_portfolio(book, market)
    panel_pnl = vals[0].delta * 0.10 + vals[1].delta * -0.20
    broadcast_pnl = (vals[0].delta + vals[1].delta) * 0.10
    assert result["var_95"] == pytest.approx(max(0.0, -panel_pnl), abs=1e-12)
    assert result["var_95"] != pytest.approx(max(0.0, -broadcast_pnl))
