from __future__ import annotations

import pytest

from app.domain.models import (
    EquityPosition,
    MarketSnapshot,
    Portfolio,
    VaRMethodology,
)
from app.interfaces.pricing import LegacyDemoPricingAdapter
from app.market.demo_snapshot import (
    ConflictingSampleMarkError,
    MissingMarketDataError,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService


def _equity_book() -> tuple[Portfolio, EquityPosition]:
    position = EquityPosition(
        type="equity",
        id="eq",
        symbol="AUTH",
        quantity=10.0,
        price=999.0,
    )
    return Portfolio(id="authority", name="authority", positions=[position]), position


def test_snapshots_change_pv_without_mutating_legacy_trade() -> None:
    _, position = _equity_book()
    original = position.model_dump(mode="json")
    market_a = MarketSnapshot(id="a", equity_spots={"AUTH": 100.0})
    market_b = MarketSnapshot(id="b", equity_spots={"AUTH": 120.0})
    pricing = BuiltinPricingEngine()

    pv_a = pricing.value(position, market_a).market_value
    pv_b = pricing.value(position, market_b).market_value

    assert pv_a == 1_000.0
    assert pv_b == 1_200.0
    assert pv_a != pv_b
    assert position.model_dump(mode="json") == original


def test_supplied_snapshot_beats_trade_local_equity_spot() -> None:
    _, position = _equity_book()
    market = MarketSnapshot(id="authoritative", equity_spots={"AUTH": 101.0})

    valuation = BuiltinPricingEngine().value(position, market)

    assert valuation.market_value == 1_010.0
    assert valuation.market_value != position.quantity * position.price


def test_named_legacy_pricing_adapter_isolates_no_market_compatibility() -> None:
    _, position = _equity_book()

    valuation = LegacyDemoPricingAdapter(BuiltinPricingEngine()).value(position)

    assert valuation.market_value == position.quantity * position.price


class _RecordingPricingEngine(BuiltinPricingEngine):
    def __init__(self) -> None:
        self.markets: list[MarketSnapshot | None] = []

    def value(self, position, market=None):
        self.markets.append(market)
        return super().value(position, market)


class _CountingMarketProvider:
    def __init__(self, snapshot: MarketSnapshot) -> None:
        self.resolved = snapshot
        self.calls = 0

    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        self.calls += 1
        return self.resolved


def test_portfolio_service_passes_one_resolved_snapshot_to_summary_var_and_es() -> None:
    portfolio, _ = _equity_book()
    snapshot = MarketSnapshot(id="service", equity_spots={"AUTH": 105.0})
    pricing = _RecordingPricingEngine()
    service = PortfolioService(
        pricing,
        HistoricalRiskEngine(seed=1, observations=8),
    )
    provider = _CountingMarketProvider(snapshot)
    service.market_data = provider

    service.summary(portfolio, methodology=VaRMethodology.LINEAR)
    assert provider.calls == 1
    assert pricing.markets
    assert all(market is snapshot for market in pricing.markets)

    pricing.markets.clear()
    service.var_report(portfolio, methodology=VaRMethodology.LINEAR)
    assert provider.calls == 2
    assert pricing.markets
    assert all(market is snapshot for market in pricing.markets)

    pricing.markets.clear()
    service.es_contributions(portfolio, methodology=VaRMethodology.LINEAR)
    assert provider.calls == 3
    assert pricing.markets
    assert all(market is snapshot for market in pricing.markets)


@pytest.mark.parametrize(
    "market",
    [
        MarketSnapshot(id="empty"),
        MarketSnapshot(id="spy-only", equity_spots={"SPY": 565.0}),
    ],
    ids=["empty", "spy-only"],
)
def test_missing_equity_spot_raises_when_market_is_supplied(market: MarketSnapshot) -> None:
    _, position = _equity_book()

    with pytest.raises(MissingMarketDataError):
        BuiltinPricingEngine().value(position, market)


@pytest.mark.parametrize(
    "market",
    [
        MarketSnapshot(id="empty"),
        MarketSnapshot(id="spy-only", equity_spots={"SPY": 565.0}),
    ],
    ids=["empty", "spy-only"],
)
def test_linear_var_raises_when_supplied_snapshot_omits_equity_spot(
    market: MarketSnapshot,
) -> None:
    portfolio, _ = _equity_book()

    with pytest.raises(MissingMarketDataError):
        HistoricalRiskEngine(seed=1, observations=8).calculate(
            portfolio,
            BuiltinPricingEngine(),
            methodology=VaRMethodology.LINEAR,
            market=market,
        )


@pytest.mark.parametrize("book_id", ["custom-superset", SAMPLE_PORTFOLIO.id])
def test_sample_plus_extra_aapl_does_not_bind_incomplete_canned_snapshot(
    book_id: str,
) -> None:
    extra = EquityPosition(
        type="equity",
        id="eq-aapl-extra",
        symbol="AAPL",
        quantity=10.0,
        price=1000.0,
    )
    book = SAMPLE_PORTFOLIO.model_copy(
        update={
            "id": book_id,
            "positions": [*SAMPLE_PORTFOLIO.positions, extra],
        }
    )

    try:
        snapshot = demo_market_snapshot(book)
    except (MissingMarketDataError, ConflictingSampleMarkError):
        return

    assert snapshot.id != "demo:global-macro"
    assert "AAPL" in snapshot.equity_spots
    assert BuiltinPricingEngine().value(extra, snapshot).market_value == 10_000.0


def test_portfolio_service_passes_resolved_snapshot_to_contributors_and_compare() -> None:
    portfolio, _ = _equity_book()
    snapshot = MarketSnapshot(id="service", equity_spots={"AUTH": 105.0})
    pricing = _RecordingPricingEngine()
    service = PortfolioService(
        pricing,
        HistoricalRiskEngine(seed=1, observations=8),
    )
    provider = _CountingMarketProvider(snapshot)
    service.market_data = provider

    service.contributors(portfolio)
    assert provider.calls == 1
    assert pricing.markets
    assert all(market is snapshot for market in pricing.markets)

    pricing.markets.clear()
    service.compare_var_methodologies(
        portfolio,
        methodologies=[VaRMethodology.LINEAR],
    )
    assert provider.calls == 2
    assert pricing.markets
    assert all(market is snapshot for market in pricing.markets)
