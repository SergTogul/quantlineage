from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import MarketSnapshot, Portfolio, StressScenario
from app.market.demo_snapshot import DemoSampleMarksSnapshotAdapter


class MarketDataProvider(ABC):
    @abstractmethod
    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        raise NotImplementedError


class PositionMarketDataProvider(MarketDataProvider):
    """Deprecated name retained for import compatibility.

    Sample marks no longer live on Position DTOs. ``snapshot`` always raises
    ``SampleMarksRemovedError``; callers must supply an explicit
    ``MarketSnapshot`` (or use ``sample.demo_market_snapshot`` for canned demos).
    """

    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        return DemoSampleMarksSnapshotAdapter().snapshot(portfolio)


def shock_snapshot(base: MarketSnapshot, scenario: StressScenario) -> MarketSnapshot:
    """Apply a StressScenario via the M3.2 multi-factor :mod:`scenario_engine`."""
    from app.risk.scenario_engine import apply_scenario

    return apply_scenario(base, scenario)
