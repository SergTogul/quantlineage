from __future__ import annotations
from collections import defaultdict
from app.domain.models import (
    BondPosition, EquityFuturePosition, EquityPosition, EuropeanOptionPosition,
    FXForwardPosition, FXOptionPosition, Portfolio, RiskFactorExposure, SwapPosition,
)
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import MarketDataProvider, PositionMarketDataProvider


class RiskFactorEngine:
    def __init__(self, market_data: MarketDataProvider | None = None):
        self.market_data = market_data or PositionMarketDataProvider()

    def calculate(self, portfolio: Portfolio, pricing: PricingEngine) -> list[RiskFactorExposure]:
        market = self.market_data.snapshot(portfolio)
        agg: dict[tuple[str,str,str], float] = defaultdict(float)
        for p in portfolio.positions:
            v = pricing.value(p, market)
            if isinstance(p, (EquityPosition, EquityFuturePosition, EuropeanOptionPosition)):
                agg[(p.symbol,"equity",p.symbol)] += v.delta
                if v.vega: agg[(f"{p.symbol}:VOL","vol",p.symbol)] += v.vega
            elif isinstance(p, (BondPosition, SwapPosition)):
                ccy = p.currency
                tenor = f"{round(p.maturity_years)}Y"
                agg[(f"{ccy}:RATE","rate",tenor)] += v.dv01
            elif isinstance(p, (FXForwardPosition, FXOptionPosition)):
                agg[(p.pair,"fx",p.pair)] += v.fx_delta
                if v.vega: agg[(f"{p.pair}:VOL","vol",p.pair)] += v.vega
        return [RiskFactorExposure(factor=k[0], factor_type=k[1], bucket=k[2], exposure=x) for k,x in sorted(agg.items())]
