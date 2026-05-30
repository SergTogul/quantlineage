from __future__ import annotations

from collections import defaultdict

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
    RiskFactorExposure,
    SwapPosition,
)
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import MarketDataProvider
from app.pricing.instrument_capabilities import get_capability
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
            get_capability(getattr(p, "type", None))
            v = pricing.value(p, market)
            if isinstance(p, (EquityPosition, EquityFuturePosition, EuropeanOptionPosition)):
                agg[EquitySpot(p.symbol)] += v.delta
                if v.vega:
                    agg[EquityVol(underlying=p.symbol)] += v.vega
            elif isinstance(p, (BondPosition, SwapPosition, InterestRateFuturePosition)):
                tenor = f"{round(p.maturity_years)}Y"
                agg[RateZero(currency=p.currency, tenor=tenor)] += v.dv01
            elif isinstance(p, (FXForwardPosition, FXOptionPosition)):
                agg[FXSpot(p.pair)] += v.fx_delta
                if v.vega:
                    agg[FXVol(pair=p.pair)] += v.vega
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
