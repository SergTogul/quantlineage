from abc import ABC, abstractmethod

from app.domain.models import MarketSnapshot, Portfolio, Position, StressScenario, Valuation
from app.market.snapshot import shock_snapshot


def _require_explicit_market(market: MarketSnapshot | None) -> MarketSnapshot:
    if market is None:
        raise ValueError("production risk calculation requires an explicit MarketSnapshot")
    return market


class PricingEngine(ABC):
    """Production pricing contract.

    Callers must provide ``market`` explicitly. Position DTOs carry economics
    only; live marks live exclusively on ``MarketSnapshot``.
    """

    @abstractmethod
    def value(self, position: Position, market: MarketSnapshot) -> Valuation:
        raise NotImplementedError

    def shocked_value(
        self,
        position: Position,
        scenario: StressScenario,
        market: MarketSnapshot | None = None,
    ) -> float:
        market = _require_explicit_market(market)
        return self.value(position, shock_snapshot(market, scenario)).market_value

    def value_portfolio(
        self, portfolio: Portfolio, market: MarketSnapshot | None = None
    ) -> list[Valuation]:
        market = _require_explicit_market(market)
        return [self.value(position, market) for position in portfolio.positions]
