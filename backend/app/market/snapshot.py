from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import (
    BondPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    Portfolio,
    StressScenario,
    SwapPosition,
)


class MarketDataProvider(ABC):
    @abstractmethod
    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        raise NotImplementedError


class PositionMarketDataProvider(MarketDataProvider):
    """Builds an immutable snapshot from trade marks. Replaceable by live/DB market data."""
    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        eq, vols, fx, fxv, rates = {}, {}, {}, {}, {"USD": 0.04}
        for p in portfolio.positions:
            if isinstance(p, EquityPosition): eq[p.symbol] = p.price
            elif isinstance(p, (EuropeanOptionPosition, EquityFuturePosition)):
                eq[p.symbol] = p.spot
                if isinstance(p, EuropeanOptionPosition): vols[p.symbol] = p.volatility
                rates["USD"] = p.risk_free_rate
            elif isinstance(p, BondPosition): rates[p.currency] = p.yield_rate
            elif isinstance(p, SwapPosition): rates[p.currency] = p.market_swap_rate
            elif isinstance(p, InterestRateFuturePosition): rates[p.currency] = p.forward_rate
            elif isinstance(p, (FXForwardPosition, FXOptionPosition)):
                fx[p.pair] = p.spot
                if isinstance(p, FXOptionPosition): fxv[p.pair] = p.volatility
                rates[p.pair[-3:]] = p.domestic_rate
                rates[p.pair[:3]] = p.foreign_rate
        return MarketSnapshot(id="position_marks", equity_spots=eq, equity_vols=vols, fx_spots=fx, fx_vols=fxv, rates=rates)


def shock_snapshot(base: MarketSnapshot, scenario: StressScenario) -> MarketSnapshot:
    """Apply a StressScenario via the M3.2 multi-factor :mod:`scenario_engine`."""
    from app.risk.scenario_engine import apply_scenario

    return apply_scenario(base, scenario)
