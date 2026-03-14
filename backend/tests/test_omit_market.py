"""Production VaR / ES / full-reval must not infer a market when market is omitted."""

from __future__ import annotations

import pytest

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.es import ESContributionAnalytics
from app.risk.historical import HistoricalRiskEngine
from app.risk.var import VaRAnalytics
from app.sample import demo_market_snapshot

PRICING = BuiltinPricingEngine()
BOOK = Portfolio(
    id="omit-market",
    name="omit-market",
    positions=[
        EquityPosition(type="equity", id="unit", symbol="UNIT", quantity=1.0, price=1.0)
    ],
)


def test_historical_engine_calculate_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        HistoricalRiskEngine(seed=1, observations=8).calculate(BOOK, PRICING)


def test_historical_engine_calculate_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        HistoricalRiskEngine(seed=1, observations=8).calculate(BOOK, PRICING, market=None)


def test_var_analytics_report_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        VaRAnalytics(seed=1, observations=8).report(BOOK, PRICING)


def test_es_report_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ESContributionAnalytics(seed=1, observations=8).report(BOOK, PRICING)


def test_es_empty_book_omitted_market_raises() -> None:
    empty = Portfolio(id="empty", name="Empty", positions=[])
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ESContributionAnalytics(seed=1, observations=8).report(empty, PRICING)


def test_explicit_market_still_values() -> None:
    market = demo_market_snapshot(BOOK)
    result = HistoricalRiskEngine(seed=1, observations=8).calculate(
        BOOK, PRICING, market=market
    )
    assert result["market_value"] == pytest.approx(1.0)
    report = VaRAnalytics(seed=1, observations=8).report(BOOK, PRICING, market=market)
    assert report.portfolio_id == BOOK.id
    es = ESContributionAnalytics(seed=1, observations=8).report(
        BOOK, PRICING, market=market
    )
    assert es.portfolio_id == BOOK.id


def test_explicit_empty_snapshot_is_accepted_as_market() -> None:
    market = MarketSnapshot(id="empty")
    empty = Portfolio(id="empty", name="Empty", positions=[])
    es = ESContributionAnalytics(seed=1, observations=8).report(
        empty, PRICING, market=market
    )
    assert es.portfolio_es == 0.0
