from __future__ import annotations

from collections import defaultdict

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    RiskFactorExposure,
    Valuation,
)
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import MarketDataProvider
from app.pricing.instrument_capabilities import named_risk_factors
from app.risk.factor_types import (
    EquitySpot,
    EquityVol,
    FXSpot,
    FXVol,
    RateZero,
    RiskFactor,
    factor_sort_key,
)
from app.sample import DemoPortfolioMarketDataProvider


def _sensitivity_for_factor(factor: RiskFactor, valuation: Valuation) -> float:
    if isinstance(factor, EquitySpot):
        return float(valuation.delta)
    if isinstance(factor, FXSpot):
        return float(valuation.fx_delta)
    if isinstance(factor, (EquityVol, FXVol)):
        return float(valuation.vega)
    if isinstance(factor, RateZero):
        return float(valuation.dv01)
    raise TypeError(f"unsupported risk factor type: {type(factor)!r}")


class RiskFactorEngine:
    def __init__(self, market_data: MarketDataProvider | None = None):
        self.market_data = market_data or DemoPortfolioMarketDataProvider()

    def calculate_typed(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot | None = None,
    ) -> list[tuple[RiskFactor, float]]:
        """Aggregate exposures keyed by typed :class:`RiskFactor` instances."""
        market = market or self.market_data.snapshot(portfolio)
        agg: dict[RiskFactor, float] = defaultdict(float)
        for p in portfolio.positions:
            factors = named_risk_factors(p)
            v = pricing.value(p, market)
            for factor in factors:
                amount = _sensitivity_for_factor(factor, v)
                if isinstance(factor, (EquityVol, FXVol)) and not amount:
                    continue
                agg[factor] += amount
        return sorted(agg.items(), key=lambda item: factor_sort_key(item[0]))

    def calculate(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot | None = None,
    ) -> list[RiskFactorExposure]:
        """API-facing exposures; ``factor`` remains a stable string key."""
        return [
            RiskFactorExposure(
                factor=factor.key,
                factor_type=factor.factor_type,
                bucket=factor.bucket,
                exposure=exposure,
            )
            for factor, exposure in self.calculate_typed(portfolio, pricing, market)
        ]
