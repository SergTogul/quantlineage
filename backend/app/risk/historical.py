from __future__ import annotations

import numpy as np

from app.domain.models import Portfolio
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine


class HistoricalRiskEngine(RiskEngine):
    """Historical-style risk using deterministic synthetic factor-return history.

    For the MVP this avoids an external market-data dependency while preserving
    the same interface a real historical-return provider will use later.
    """

    def __init__(self, seed: int = 7, observations: int = 750):
        self.seed = seed
        self.observations = observations

    def calculate(self, portfolio: Portfolio, pricing_engine: PricingEngine) -> dict[str, float]:
        vals = pricing_engine.value_portfolio(portfolio)
        mv = sum(v.market_value for v in vals)
        delta = sum(v.delta for v in vals)
        gamma = sum(v.gamma for v in vals)
        vega = sum(v.vega for v in vals)
        dv01 = sum(v.dv01 for v in vals)
        fx_delta = sum(v.fx_delta for v in vals)

        rng = np.random.default_rng(self.seed)
        equity_ret = rng.normal(0.0002, 0.013, self.observations)
        vol_pct = rng.normal(0.0, 0.07, self.observations)
        rates_bps = rng.normal(0.0, 7.0, self.observations)
        fx_ret = rng.normal(0.0, 0.006, self.observations)

        # Delta-gamma + vega + DV01 approximation. Risk layer is pricing-library agnostic.
        pnl = (
            delta * equity_ret
            + 0.5 * gamma * equity_ret * equity_ret
            + vega * (vol_pct * 100.0)
            + dv01 * rates_bps
            + fx_delta * fx_ret
        )
        losses = -pnl
        var95 = float(max(0.0, np.quantile(losses, 0.95)))
        var99 = float(max(0.0, np.quantile(losses, 0.99)))
        tail = losses[losses >= var99]
        es99 = float(max(0.0, tail.mean() if len(tail) else var99))
        return {
            "market_value": float(mv),
            "delta": float(delta),
            "gamma": float(gamma),
            "vega": float(vega),
            "dv01": float(dv01),
            "fx_delta": float(fx_delta),
            "var_95": var95,
            "var_99": var99,
            "expected_shortfall_99": es99,
        }
