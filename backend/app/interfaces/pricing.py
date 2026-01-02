from abc import ABC, abstractmethod
from app.domain.models import MarketSnapshot, Portfolio, Position, StressScenario, Valuation
from app.market.snapshot import PositionMarketDataProvider, shock_snapshot


class PricingEngine(ABC):
    @abstractmethod
    def value(self, position: Position, market: MarketSnapshot | None = None) -> Valuation:
        raise NotImplementedError

    def shocked_value(self, position: Position, scenario: StressScenario, market: MarketSnapshot | None = None) -> float:
        # Default implementation values against a shocked immutable market snapshot.
        if market is None:
            market = PositionMarketDataProvider().snapshot(Portfolio(id="single", name="single", positions=[position]))
        return self.value(position, shock_snapshot(market, scenario)).market_value

    def value_portfolio(self, portfolio: Portfolio, market: MarketSnapshot | None = None) -> list[Valuation]:
        return [self.value(position, market) for position in portfolio.positions]
