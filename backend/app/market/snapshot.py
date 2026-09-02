from __future__ import annotations
from abc import ABC, abstractmethod
from app.domain.models import (
    BondPosition, EquityFuturePosition, EquityPosition, EuropeanOptionPosition,
    FXForwardPosition, FXOptionPosition, MarketSnapshot, Portfolio, StressScenario, SwapPosition,
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
            elif isinstance(p, (FXForwardPosition, FXOptionPosition)):
                fx[p.pair] = p.spot
                if isinstance(p, FXOptionPosition): fxv[p.pair] = p.volatility
                rates[p.pair[-3:]] = p.domestic_rate
                rates[p.pair[:3]] = p.foreign_rate
        return MarketSnapshot(id="position_marks", equity_spots=eq, equity_vols=vols, fx_spots=fx, fx_vols=fxv, rates=rates)


def shock_snapshot(base: MarketSnapshot, scenario: StressScenario) -> MarketSnapshot:
    eq = {k: v * (1 + scenario.equity_shocks.get(k, scenario.equity_shock)) for k, v in base.equity_spots.items()}
    vols = {k: max(1e-6, v * (1 + scenario.vol_shocks.get(k, scenario.vol_shock))) for k, v in base.equity_vols.items()}
    fx = {k: v * (1 + scenario.fx_shocks.get(k, scenario.fx_shock)) for k, v in base.fx_spots.items()}
    fxv = {k: max(1e-6, v * (1 + scenario.vol_shocks.get(k, scenario.vol_shock))) for k, v in base.fx_vols.items()}
    rates = {k: v + scenario.rate_shocks_bps.get(k, scenario.rates_shift_bps) / 10000.0 for k, v in base.rates.items()}
    return base.model_copy(update={"id": f"{base.id}:{scenario.id or scenario.name}", "equity_spots": eq, "equity_vols": vols, "fx_spots": fx, "fx_vols": fxv, "rates": rates})
