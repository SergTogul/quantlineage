from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import MarketSnapshot, Portfolio, StressScenario
from app.market.demo_snapshot import DemoSampleMarksSnapshotAdapter


class MarketDataProvider(ABC):
    @abstractmethod
    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        raise NotImplementedError


class PositionMarketDataProvider(MarketDataProvider):
    """Deprecated compatibility name for validated demo sample-mark adaptation.

    Compatibility choice for R0.2-A: the default wrapper raises on competing
    marks. Demo portfolios use ``sample.demo_market_snapshot`` explicitly; no
    legacy last-writer-wins mode remains on the production-facing API.
    """

    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        return DemoSampleMarksSnapshotAdapter().snapshot(portfolio)


def shock_snapshot(base: MarketSnapshot, scenario: StressScenario) -> MarketSnapshot:
    """Apply a StressScenario via the M3.2 multi-factor :mod:`scenario_engine`."""
    from app.risk.scenario_engine import apply_scenario

    return apply_scenario(base, scenario)
