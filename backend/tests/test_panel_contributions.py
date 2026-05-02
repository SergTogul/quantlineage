"""R0.5.5 — VaR/ES contributions against HistoricalFactorPanel.

When ``factor_panel`` is set, position and factor contributions use per-name /
per-tenor histories (not four-macro broadcast). Missing required factors fail
closed. ``factor_panel=None`` preserves the labeled four-macro fixture path.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.es import ESContributionAnalytics
from app.risk.factor_panel import HistoricalFactorPanel
from app.risk.factor_types import EquitySpot
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.var import VaRAnalytics
from app.services.portfolio_service import PortfolioService

AAA = EquitySpot("AAA")
BBB = EquitySpot("BBB")
AS_OF = date(2024, 1, 2)
PRICING = BuiltinPricingEngine()


def _equity_book() -> tuple[Portfolio, MarketSnapshot]:
    book = Portfolio(
        id="eq2",
        name="two equities",
        positions=[
            EquityPosition(type="equity", id="aaa", symbol="AAA", quantity=10.0),
            EquityPosition(type="equity", id="bbb", symbol="BBB", quantity=10.0),
        ],
    )
    market = MarketSnapshot(
        id="eq2",
        equity_spots={"AAA": 100.0, "BBB": 100.0},
        rates={"USD": 0.04},
    )
    return book, market


def _equity_panel(*, aaa: float, bbb: float) -> HistoricalFactorPanel:
    return HistoricalFactorPanel.from_pairs(
        dates=[AS_OF],
        rows=[[(AAA, aaa), (BBB, bbb)]],
    )


def test_var_position_contributions_differ_with_panel_histories():
    """Two equities with opposite returns must not share a broadcast contribution."""
    book, market = _equity_book()
    panel = _equity_panel(aaa=0.1, bbb=-0.2)
    report = VaRAnalytics(
        factor_panel=panel,
        methodology=VaRMethodology.LINEAR,
    ).report(book, PRICING, confidence=0.5, methodology=VaRMethodology.LINEAR, market=market)

    by_id = {c.position_id: c for c in report.contributions}
    # Historical ES contribution follows each name's panel return (not parametric VaR).
    assert by_id["aaa"].component_es != pytest.approx(by_id["bbb"].component_es)

    # Broadcast of AAA's return onto both names forces equal contributions (same qty/spot).
    broadcast = VaRAnalytics(
        dataset=ArrayHistoricalDataset(
            FactorObservationSeries(
                equity_returns=np.array([0.1]),
                vol_moves=np.array([0.0]),
                rate_moves_bps=np.array([0.0]),
                fx_returns=np.array([0.0]),
            )
        ),
        methodology=VaRMethodology.LINEAR,
    ).report(book, PRICING, confidence=0.5, methodology=VaRMethodology.LINEAR, market=market)
    bcast = {c.position_id: c for c in broadcast.contributions}
    assert bcast["aaa"].component_es == pytest.approx(bcast["bbb"].component_es)
    assert {by_id["aaa"].component_es, by_id["bbb"].component_es} != {
        bcast["aaa"].component_es,
        bcast["bbb"].component_es,
    }


def test_es_factor_contributions_use_panel_not_broadcast():
    book, market = _equity_book()
    panel = _equity_panel(aaa=0.1, bbb=-0.2)
    report = ESContributionAnalytics(
        factor_panel=panel,
        methodology=VaRMethodology.LINEAR,
    ).report(book, PRICING, confidence=0.5, methodology=VaRMethodology.LINEAR, market=market)

    assert abs(report.reconciliation_error_risk_factor) < 1e-9
    equity = next(c for c in report.by_risk_factor if c.key == "equity")
    vals = PRICING.value_portfolio(book, market)
    expected_equity_pnl = vals[0].delta * 0.1 + vals[1].delta * -0.2
    # One observation: factor ES contribution is mean(-pnl) on the portfolio tail.
    assert equity.component_es == pytest.approx(-expected_equity_pnl, abs=1e-12)

    broadcast_equity = (vals[0].delta + vals[1].delta) * 0.1
    assert equity.component_es != pytest.approx(-broadcast_equity)


def test_panel_missing_required_factor_fails_closed_for_contributions():
    book, market = _equity_book()
    panel = HistoricalFactorPanel.from_pairs(dates=[AS_OF], rows=[[(AAA, 0.1)]])
    with pytest.raises(ValueError, match="missing required factor"):
        VaRAnalytics(factor_panel=panel, methodology=VaRMethodology.LINEAR).report(
            book, PRICING, methodology=VaRMethodology.LINEAR, market=market
        )
    with pytest.raises(ValueError, match="missing required factor"):
        ESContributionAnalytics(factor_panel=panel, methodology=VaRMethodology.LINEAR).report(
            book, PRICING, methodology=VaRMethodology.LINEAR, market=market
        )


def test_var_es_four_macro_path_unchanged_without_panel():
    book, market = _equity_book()
    series = FactorObservationSeries(
        equity_returns=np.array([-0.1]),
        vol_moves=np.array([0.0]),
        rate_moves_bps=np.array([0.0]),
        fx_returns=np.array([0.0]),
    )
    dataset = ArrayHistoricalDataset(series)
    var_report = VaRAnalytics(
        dataset=dataset,
        factor_panel=None,
        methodology=VaRMethodology.LINEAR,
    ).report(book, PRICING, confidence=0.5, methodology=VaRMethodology.LINEAR, market=market)
    by_id = {c.position_id: c for c in var_report.contributions}
    # Four-macro broadcast: identical Greek-scaled P&L for equal delta names.
    assert by_id["aaa"].component_es == pytest.approx(by_id["bbb"].component_es)

    es_report = ESContributionAnalytics(
        dataset=dataset,
        factor_panel=None,
        methodology=VaRMethodology.LINEAR,
    ).report(book, PRICING, confidence=0.5, methodology=VaRMethodology.LINEAR, market=market)
    assert abs(es_report.reconciliation_error_risk_factor) < 1e-9
    equity = next(c for c in es_report.by_risk_factor if c.key == "equity")
    vals = PRICING.value_portfolio(book, market)
    broadcast_pnl = (vals[0].delta + vals[1].delta) * -0.1
    assert equity.component_es == pytest.approx(max(0.0, -broadcast_pnl), abs=1e-12)


def test_portfolio_service_shares_factor_panel_into_var_and_es():
    book, market = _equity_book()
    panel = _equity_panel(aaa=0.1, bbb=-0.2)
    risk = HistoricalRiskEngine(factor_panel=panel, methodology=VaRMethodology.LINEAR)

    class _FixedMarket:
        def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
            return market

    svc = PortfolioService(PRICING, risk, market_data=_FixedMarket())

    assert svc.var_engine.factor_panel is panel
    assert svc.es_engine.factor_panel is panel

    var_report = svc.var_report(book, methodology=VaRMethodology.LINEAR)
    by_id = {c.position_id: c for c in var_report.contributions}
    assert by_id["aaa"].component_es != pytest.approx(by_id["bbb"].component_es)

    es_report = svc.es_contributions(book, methodology=VaRMethodology.LINEAR, confidence=0.5)
    by_pos = {c.key: c for c in es_report.by_position}
    assert by_pos["aaa"].component_es != pytest.approx(by_pos["bbb"].component_es)
