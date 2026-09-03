from abc import ABC, abstractmethod

from app.domain.models import MarketSnapshot, Portfolio, Position, StressScenario, Valuation
from app.market.demo_snapshot import DemoSampleMarksSnapshotAdapter
from app.market.snapshot import shock_snapshot


class PricingEngine(ABC):
    """Production pricing contract.

    Risk/application callers must provide ``market`` explicitly. Concrete
    engines temporarily retain optional arguments for direct legacy unit tests;
    new no-market callers must use :class:`LegacyDemoPricingAdapter`.
    """

    @abstractmethod
    def value(self, position: Position, market: MarketSnapshot) -> Valuation:
        raise NotImplementedError

    def shocked_value(self, position: Position, scenario: StressScenario, market: MarketSnapshot | None = None) -> float:
        # Default implementation values against a shocked immutable market snapshot.
        if market is None:
            market = DemoSampleMarksSnapshotAdapter().snapshot(
                Portfolio(id="single", name="single", positions=[position])
            )
        return self.value(position, shock_snapshot(market, scenario)).market_value

    def value_portfolio(self, portfolio: Portfolio, market: MarketSnapshot | None = None) -> list[Valuation]:
        if market is None:
            legacy = LegacyDemoPricingAdapter(self)
            return [legacy.value(position) for position in portfolio.positions]
        return [self.value(position, market) for position in portfolio.positions]


class LegacyDemoPricingAdapter:
    """Explicit compatibility boundary for direct pricing from one trade's marks."""

    def __init__(self, pricing: PricingEngine):
        self.pricing = pricing
        self.market_data = DemoSampleMarksSnapshotAdapter()

    def value(self, position: Position) -> Valuation:
        portfolio = Portfolio(id="legacy_single", name="legacy_single", positions=[position])
        return self.pricing.value(position, self.market_data.snapshot(portfolio))
