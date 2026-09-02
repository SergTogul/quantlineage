"""Expected Shortfall contributions (M2.5).

Historical ES contribution uses the portfolio-tail conditional mean of each
entity's loss. Because expectation is linear, position (and hierarchy rollups
built from them) sum exactly to portfolio ES.

Risk-factor contributions:
- ``LINEAR`` / ``DELTA_GAMMA``: additive Greek P&L terms (equity/vol/rate/fx)
- ``FULL_REVALUATION``: factor-isolated full reval P&L plus an ``interaction``
  residual so contributions still reconcile to portfolio ES
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from app.domain.models import (
    ESContribution,
    ESContributionReport,
    MarketSnapshot,
    Portfolio,
    VaRMethodology,
)
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import PositionMarketDataProvider
from app.risk.historical_data import HistoricalMarketDataset, SyntheticHistoricalDataset
from app.risk.hierarchy_placement import resolve_desk, resolve_strategy
from app.risk.scenarios import (
    AggregateFactorChange,
    apply_market_scenario,
    expand_aggregate_change,
    iter_aggregate_changes,
    market_scenario_from_change,
)
from app.risk.var import VaRAnalytics

# Aggregate risk-factor families used for ES factor attribution.
_FACTOR_KEYS = ("equity", "vol", "rate", "fx")
_FACTOR_LABELS = {
    "equity": "Equity",
    "vol": "Volatility",
    "rate": "Rates",
    "fx": "FX",
    "interaction": "Cross-factor interaction",
}


def _tail_mask(losses: np.ndarray, confidence: float) -> tuple[float, np.ndarray]:
    """VaR at ``confidence`` and boolean mask of tail observations (loss >= VaR)."""
    if losses.size == 0:
        return 0.0, np.array([], dtype=bool)
    var = float(max(0.0, np.quantile(losses, confidence)))
    mask = losses >= var
    if not np.any(mask):
        # Flat / degenerate: treat all observations as the "tail" of zeros.
        mask = np.ones(losses.shape, dtype=bool)
    return var, mask


def _tail_mean_loss(pnl: np.ndarray, mask: np.ndarray) -> float:
    """Mean loss (-P&L) on selected tail scenarios."""
    if pnl.size == 0 or not np.any(mask):
        return 0.0
    return float((-pnl[mask]).mean())


def _contributions_from_pnl_map(
    pnl_by_key: dict[str, np.ndarray],
    mask: np.ndarray,
    portfolio_es: float,
    *,
    labels: dict[str, str] | None = None,
) -> list[ESContribution]:
    labels = labels or {}
    items: list[ESContribution] = []
    for key, pnl in pnl_by_key.items():
        component = _tail_mean_loss(pnl, mask)
        items.append(
            ESContribution(
                key=key,
                label=labels.get(key, key),
                component_es=component,
                contribution_pct=component / portfolio_es * 100.0 if portfolio_es else 0.0,
            )
        )
    items.sort(key=lambda x: abs(x.component_es), reverse=True)
    return items


def _reconciliation_error(contributions: list[ESContribution], portfolio_es: float) -> float:
    return float(abs(sum(c.component_es for c in contributions) - portfolio_es))


def _aggregate_factor_pnl_linear(
    portfolio: Portfolio,
    pricing: PricingEngine,
    methodology: VaRMethodology,
    equity_ret: np.ndarray,
    vol_pct: np.ndarray,
    rates_bps: np.ndarray,
    fx_ret: np.ndarray,
) -> dict[str, np.ndarray]:
    """Additive Greek factor P&L series (LINEAR / DELTA_GAMMA only)."""
    n = equity_ret.shape[0]
    out = {k: np.zeros(n, dtype=float) for k in _FACTOR_KEYS}
    for p in portfolio.positions:
        v = pricing.value(p)
        out["equity"] += v.delta * equity_ret
        if methodology is VaRMethodology.DELTA_GAMMA:
            out["equity"] += 0.5 * v.gamma * equity_ret * equity_ret
        out["vol"] += v.vega * (vol_pct * 100.0)
        out["rate"] += v.dv01 * rates_bps
        out["fx"] += v.fx_delta * fx_ret
    return out


def _aggregate_factor_pnl_full_reval(
    portfolio: Portfolio,
    pricing: PricingEngine,
    base_market: MarketSnapshot,
    dataset: HistoricalMarketDataset,
    total_pnl: np.ndarray,
) -> dict[str, np.ndarray]:
    """Factor-isolated full-reval P&L plus residual interaction.

    For each observation, apply only that aggregate factor family's shocks,
    reprice, and attribute P&L. Residual ``interaction`` = total − sum(factors)
    so contributions reconcile to full-revaluation portfolio ES.
    """
    series = dataset.factor_observations()
    changes = iter_aggregate_changes(series)
    n = len(changes)
    factor_pnl = {k: np.zeros(n, dtype=float) for k in _FACTOR_KEYS}
    base_mv = sum(v.market_value for v in pricing.value_portfolio(portfolio, base_market))

    for i, change in enumerate(changes):
        isolated = {
            "equity": AggregateFactorChange(change.index, change.equity_return, 0.0, 0.0, 0.0),
            "vol": AggregateFactorChange(change.index, 0.0, change.vol_move, 0.0, 0.0),
            "rate": AggregateFactorChange(change.index, 0.0, 0.0, change.rate_move_bps, 0.0),
            "fx": AggregateFactorChange(change.index, 0.0, 0.0, 0.0, change.fx_return),
        }
        for key, iso in isolated.items():
            if not expand_aggregate_change(iso, base_market):
                factor_pnl[key][i] = 0.0
                continue
            scenario = market_scenario_from_change(iso, base_market, id_prefix=f"es_{key}")
            snap = apply_market_scenario(base_market, scenario)
            shocked_mv = sum(v.market_value for v in pricing.value_portfolio(portfolio, snap))
            factor_pnl[key][i] = shocked_mv - base_mv

    residual = total_pnl - sum(factor_pnl[k] for k in _FACTOR_KEYS)
    factor_pnl["interaction"] = residual
    return factor_pnl


class ESContributionAnalytics:
    """Historical Expected Shortfall contributions by position / hierarchy / factor."""

    def __init__(
        self,
        seed: int = 7,
        observations: int = 750,
        dataset: HistoricalMarketDataset | None = None,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    ):
        self.seed = seed
        self.observations = observations
        self.dataset: HistoricalMarketDataset = dataset or SyntheticHistoricalDataset(
            seed=seed, observations=observations
        )
        self.methodology = methodology
        self._var = VaRAnalytics(
            seed=seed, observations=observations, dataset=self.dataset, methodology=methodology
        )
        self._market_data = PositionMarketDataProvider()

    def report(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        confidence: float = 0.99,
        methodology: VaRMethodology | None = None,
        market: MarketSnapshot | None = None,
    ) -> ESContributionReport:
        meth = methodology if methodology is not None else self.methodology
        if not portfolio.positions:
            return ESContributionReport(
                portfolio_id=portfolio.id,
                methodology=meth,
                confidence=confidence,
                portfolio_var=0.0,
                portfolio_es=0.0,
                by_position=[],
                by_book=[],
                by_strategy=[],
                by_desk=[],
                by_risk_factor=[],
            )

        base_market = (
            market
            if market is not None
            else (
                self._market_data.snapshot(portfolio)
                if meth is VaRMethodology.FULL_REVALUATION
                else None
            )
        )
        pos_pnl = self._var._position_pnls(portfolio, pricing, meth, base_market)
        n = next(iter(pos_pnl.values())).shape[0]
        total_pnl = sum(pos_pnl.values(), start=np.zeros(n))
        losses = -total_pnl
        var, mask = _tail_mask(losses, confidence)
        portfolio_es = float(max(var, losses[mask].mean() if np.any(mask) else var))

        by_position = _contributions_from_pnl_map(pos_pnl, mask, portfolio_es)

        book_pnl: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(n, dtype=float))
        desk_pnl: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(n, dtype=float))
        strategy_pnl: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(n, dtype=float))
        pos_by_id = {p.id: p for p in portfolio.positions}
        for pid, pnl in pos_pnl.items():
            pos = pos_by_id[pid]
            book_pnl[pos.book] += pnl
            desk_pnl[resolve_desk(pos, portfolio)] += pnl
            strategy_pnl[resolve_strategy(pos, portfolio)] += pnl
        by_book = _contributions_from_pnl_map(dict(book_pnl), mask, portfolio_es)
        by_strategy = _contributions_from_pnl_map(dict(strategy_pnl), mask, portfolio_es)
        by_desk = _contributions_from_pnl_map(dict(desk_pnl), mask, portfolio_es)

        if meth is VaRMethodology.FULL_REVALUATION:
            assert base_market is not None
            factor_pnl = _aggregate_factor_pnl_full_reval(
                portfolio, pricing, base_market, self.dataset, total_pnl
            )
        else:
            obs = self.dataset.factor_observations()
            factor_pnl = _aggregate_factor_pnl_linear(
                portfolio,
                pricing,
                meth,
                obs.equity_returns,
                obs.vol_moves,
                obs.rate_moves_bps,
                obs.fx_returns,
            )

        by_factor = _contributions_from_pnl_map(
            factor_pnl, mask, portfolio_es, labels=_FACTOR_LABELS
        )

        return ESContributionReport(
            portfolio_id=portfolio.id,
            methodology=meth,
            confidence=confidence,
            portfolio_var=var,
            portfolio_es=portfolio_es,
            by_position=by_position,
            by_book=by_book,
            by_strategy=by_strategy,
            by_desk=by_desk,
            by_risk_factor=by_factor,
            reconciliation_error_position=_reconciliation_error(by_position, portfolio_es),
            reconciliation_error_book=_reconciliation_error(by_book, portfolio_es),
            reconciliation_error_strategy=_reconciliation_error(by_strategy, portfolio_es),
            reconciliation_error_desk=_reconciliation_error(by_desk, portfolio_es),
            reconciliation_error_risk_factor=_reconciliation_error(by_factor, portfolio_es),
        )


__all__ = ["ESContributionAnalytics"]
