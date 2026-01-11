from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    RiskContribution,
    VaRMethodology,
    VaRMethodResult,
    VaRReport,
)
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import PositionMarketDataProvider
from app.risk.historical import approximate_pnl_series
from app.risk.historical_data import HistoricalMarketDataset, SyntheticHistoricalDataset
from app.risk.marginal_var import parametric_component_var, parametric_marginal_var
from app.risk.scenarios import historical_shocked_snapshots


class VaRAnalytics:
    def __init__(
        self,
        seed: int = 7,
        observations: int = 750,
        dataset: HistoricalMarketDataset | None = None,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    ):
        self.seed, self.observations = seed, observations
        self.dataset: HistoricalMarketDataset = dataset or SyntheticHistoricalDataset(
            seed=seed, observations=observations
        )
        self.methodology = methodology
        self._market_data = PositionMarketDataProvider()

    def _factor_history(self):
        obs = self.dataset.factor_observations()
        return obs.equity_returns, obs.vol_moves, obs.rate_moves_bps, obs.fx_returns

    def _position_pnls(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        methodology: VaRMethodology,
        market: MarketSnapshot | None,
    ) -> dict[str, np.ndarray]:
        if methodology is VaRMethodology.FULL_REVALUATION:
            assert market is not None
            return self._full_reval_position_pnls(portfolio, pricing, market)
        er, vp, rb, fx = self._factor_history()
        out: dict[str, np.ndarray] = {}
        for p in portfolio.positions:
            # Legacy Greek path: position-embedded marks (no shared snapshot).
            v = pricing.value(p)
            out[p.id] = approximate_pnl_series(
                delta=v.delta,
                gamma=v.gamma,
                vega=v.vega,
                dv01=v.dv01,
                fx_delta=v.fx_delta,
                equity_ret=er,
                vol_pct=vp,
                rates_bps=rb,
                fx_ret=fx,
                methodology=methodology,
            )
        return out

    def _full_reval_position_pnls(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot,
    ) -> dict[str, np.ndarray]:
        base = {p.id: pricing.value(p, market).market_value for p in portfolio.positions}
        shocked = historical_shocked_snapshots(market, self.dataset)
        out = {p.id: np.empty(len(shocked), dtype=float) for p in portfolio.positions}
        for i, snap in enumerate(shocked):
            for p in portfolio.positions:
                out[p.id][i] = pricing.value(p, snap).market_value - base[p.id]
        return out

    def report(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        confidence: float = 0.99,
        methodology: VaRMethodology | None = None,
        market: MarketSnapshot | None = None,
    ) -> VaRReport:
        meth = methodology if methodology is not None else self.methodology
        base_market = (
            market
            if market is not None
            else (self._market_data.snapshot(portfolio) if meth is VaRMethodology.FULL_REVALUATION else None)
        )
        pos = self._position_pnls(portfolio, pricing, meth, base_market)
        n = next(iter(pos.values())).shape[0] if pos else self.dataset.factor_observations().n_observations
        total = sum(pos.values(), start=np.zeros(n))
        losses = -total
        var = float(max(0, np.quantile(losses, confidence)))
        tail = losses[losses >= var]
        es = float(max(var, tail.mean() if len(tail) else var))
        sd = float(np.std(total, ddof=1)) if n > 1 else 0.0
        z = NormalDist().inv_cdf(confidence)
        pvar = max(0, z * sd)
        # Normal ES: sigma * phi(z)/(1-alpha)
        pes = max(pvar, sd * (math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)) / (1 - confidence))
        # Component / Marginal VaR: Euler allocation of parametric VaR (see marginal_var.py).
        # P&L series follow `meth` (LINEAR / DELTA_GAMMA / FULL_REVALUATION); allocation
        # always reconciles to parametric VaR of that series, not historical quantile VaR.
        # Historical ES contribution (M2.5): mean(-pnl_i | loss >= VaR); sums to hist ES.
        tail_mask = losses >= var
        if n and not np.any(tail_mask):
            tail_mask = np.ones(n, dtype=bool)
        contributions = []
        for pid, pnl in pos.items():
            component = parametric_component_var(pnl, total, pvar)
            marginal = parametric_marginal_var(pnl, total, z)
            es_comp = float((-pnl[tail_mask]).mean()) if n else 0.0
            contributions.append(
                RiskContribution(
                    position_id=pid,
                    component_var=component,
                    contribution_pct=component / pvar * 100 if pvar else 0,
                    component_es=es_comp,
                    es_contribution_pct=es_comp / es * 100 if es else 0.0,
                    marginal_var=marginal,
                )
            )
        contributions.sort(key=lambda x: abs(x.component_var), reverse=True)
        return VaRReport(
            portfolio_id=portfolio.id,
            methodology=meth,
            methods=[
                VaRMethodResult(method="historical", confidence=confidence, var=var, expected_shortfall=es),
                VaRMethodResult(method="parametric", confidence=confidence, var=pvar, expected_shortfall=pes),
            ],
            contributions=contributions,
        )
