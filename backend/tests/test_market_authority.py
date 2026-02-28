from __future__ import annotations

import pytest

from app.domain.models import (
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
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
from tests.quantlib_gate import import_quantlib


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


def _future_book() -> tuple[Portfolio, EquityFuturePosition]:
    position = EquityFuturePosition(
        type="equity_future",
        id="fut",
        symbol="AUTH",
        quantity=10.0,
        spot=999.0,
        multiplier=50.0,
        maturity_years=0.25,
        risk_free_rate=0.04,
        dividend_yield=0.0,
    )
    return Portfolio(id="authority", name="authority", positions=[position]), position


def _option_book() -> tuple[Portfolio, EuropeanOptionPosition]:
    position = EuropeanOptionPosition(
        type="european_option",
        id="opt",
        symbol="AUTH",
        quantity=10.0,
        spot=999.0,
        strike=100.0,
        maturity_years=1.0,
        volatility=0.20,
        risk_free_rate=0.03,
        option_type="call",
    )
    return Portfolio(id="authority", name="authority", positions=[position]), position


@pytest.mark.parametrize(
    "book_factory",
    [_future_book, _option_book],
    ids=["future", "option"],
)
@pytest.mark.parametrize(
    "market",
    [
        MarketSnapshot(id="empty"),
        MarketSnapshot(id="spy-only", equity_spots={"SPY": 565.0}),
    ],
    ids=["empty", "spy-only"],
)
def test_missing_equity_family_spot_raises_when_market_is_supplied(
    book_factory, market: MarketSnapshot
) -> None:
    _, position = book_factory()

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(position, market)
    assert raised.value.factor_key == f"equity_spots[{position.symbol}]"


@pytest.mark.parametrize(
    "book_factory",
    [_future_book, _option_book],
    ids=["future", "option"],
)
@pytest.mark.parametrize(
    "market",
    [
        MarketSnapshot(id="empty"),
        MarketSnapshot(id="spy-only", equity_spots={"SPY": 565.0}),
    ],
    ids=["empty", "spy-only"],
)
def test_quantlib_missing_equity_family_spot_raises_when_market_is_supplied(
    book_factory, market: MarketSnapshot
) -> None:
    import_quantlib()
    from app.pricing.quantlib import QuantLibPricingEngine

    _, position = book_factory()

    with pytest.raises(MissingMarketDataError) as raised:
        QuantLibPricingEngine().value(position, market)
    assert raised.value.factor_key == f"equity_spots[{position.symbol}]"


def test_supplied_snapshot_beats_trade_local_equity_future_spot() -> None:
    _, position = _future_book()
    original = position.model_dump(mode="json")
    market = MarketSnapshot(id="authoritative", equity_spots={"AUTH": 101.0})

    valuation = BuiltinPricingEngine().value(position, market)
    local = BuiltinPricingEngine().value(position)

    assert valuation.market_value != local.market_value
    assert valuation.market_value != position.quantity * position.multiplier * position.spot
    assert position.model_dump(mode="json") == original


def test_supplied_snapshot_beats_trade_local_equity_option_spot() -> None:
    _, position = _option_book()
    original = position.model_dump(mode="json")
    market = MarketSnapshot(id="authoritative", equity_spots={"AUTH": 101.0})

    valuation = BuiltinPricingEngine().value(position, market)
    local = BuiltinPricingEngine().value(position)

    assert valuation.market_value != local.market_value
    assert position.model_dump(mode="json") == original


def test_quantlib_supplied_snapshot_beats_trade_local_equity_future_spot() -> None:
    import_quantlib()
    from app.pricing.quantlib import QuantLibPricingEngine

    _, position = _future_book()
    original = position.model_dump(mode="json")
    market = MarketSnapshot(id="authoritative", equity_spots={"AUTH": 101.0})
    engine = QuantLibPricingEngine()

    valuation = engine.value(position, market)
    local = engine.value(position)

    assert valuation.market_value != local.market_value
    assert position.model_dump(mode="json") == original


def test_quantlib_supplied_snapshot_beats_trade_local_equity_option_spot() -> None:
    import_quantlib()
    from app.pricing.quantlib import QuantLibPricingEngine

    _, position = _option_book()
    original = position.model_dump(mode="json")
    market = MarketSnapshot(id="authoritative", equity_spots={"AUTH": 101.0})
    engine = QuantLibPricingEngine()

    valuation = engine.value(position, market)
    local = engine.value(position)

    assert valuation.market_value != local.market_value
    assert position.model_dump(mode="json") == original
