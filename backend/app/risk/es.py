"""Expected Shortfall contributions (M2.5).

Historical ES contribution uses the portfolio-tail conditional mean of each
entity's loss. Because expectation is linear, position (and hierarchy rollups
built from them) sum exactly to portfolio ES.

Risk-factor contributions:
- ``LINEAR`` / ``DELTA_GAMMA``: additive Greek P&L terms (equity/vol/rate/fx)
- ``FULL_REVALUATION``: factor-isolated full reval P&L plus an ``interaction``
  residual so contributions still reconcile to portfolio ES

When ``factor_panel`` is set (R0.5.5), approximate and full-reval factor paths
consume per-name / per-tenor panel columns instead of four-macro broadcast.
Missing required panel factors fail closed (not silent zeros into interaction).
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
from app.pricing.cache import bypass_valuation_lru
from app.risk.factor_panel import HistoricalFactorPanel
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero, RiskFactor
from app.risk.hierarchy_placement import resolve_desk, resolve_strategy
from app.risk.historical import (
    _panel_linear_contribution,
    require_explicit_market,
    require_panel_covers_portfolio,
    required_factors_for_position,
)
from app.risk.historical_data import HistoricalMarketDataset, SyntheticHistoricalDataset
from app.risk.scenarios import (
    AggregateFactorChange,
    FactorChange,
    MarketScenario,
    apply_market_scenario,
    expand_aggregate_change,
    factor_changes_from_panel_observation,
    iter_aggregate_changes,
    market_scenario_from_change,
)
from app.risk.shock_units import relative_vol_move_to_vol_points
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


def _factor_family(factor: RiskFactor) -> str:
    if isinstance(factor, EquitySpot):
        return "equity"
    if isinstance(factor, (EquityVol, FXVol)):
        return "vol"
    if isinstance(factor, RateZero):
        return "rate"
    if isinstance(factor, FXSpot):
        return "fx"
    raise TypeError(f"unsupported risk factor type: {type(factor)!r}")


def _aggregate_factor_pnl_linear(
    portfolio: Portfolio,
    pricing: PricingEngine,
    market: MarketSnapshot,
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
        v = pricing.value(p, market)
        out["equity"] += v.delta * equity_ret
        if methodology is VaRMethodology.DELTA_GAMMA:
            out["equity"] += 0.5 * v.gamma * equity_ret * equity_ret
        out["vol"] += v.vega * relative_vol_move_to_vol_points(vol_pct)
        out["rate"] += v.dv01 * rates_bps
        out["fx"] += v.fx_delta * fx_ret
    return out


def _aggregate_factor_pnl_from_panel(
    portfolio: Portfolio,
    pricing: PricingEngine,
    market: MarketSnapshot,
    panel: HistoricalFactorPanel,
    methodology: VaRMethodology,
) -> dict[str, np.ndarray]:
    """Additive Greek factor P&L from per-name / per-tenor panel columns."""
    require_panel_covers_portfolio(portfolio, panel)
    vals = pricing.value_portfolio(portfolio, market)
    if len(vals) != len(portfolio.positions):
        raise ValueError("valuation count does not match portfolio positions")
    position_factors = [required_factors_for_position(p) for p in portfolio.positions]
    out = {k: np.zeros(panel.n_observations, dtype=float) for k in _FACTOR_KEYS}
    use_gamma = methodology is VaRMethodology.DELTA_GAMMA
    for i, observation in enumerate(panel.observations):
        for factors, valuation in zip(position_factors, vals, strict=True):
            for factor in factors:
                move = observation.change(factor)
                family = _factor_family(factor)
                out[family][i] += _panel_linear_contribution(factor, valuation, move)
                if use_gamma and isinstance(factor, EquitySpot):
                    out[family][i] += 0.5 * float(valuation.gamma) * move * move
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

    with bypass_valuation_lru():
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


def _aggregate_factor_pnl_full_reval_from_panel(
    portfolio: Portfolio,
    pricing: PricingEngine,
    base_market: MarketSnapshot,
    panel: HistoricalFactorPanel,
    total_pnl: np.ndarray,
) -> dict[str, np.ndarray]:
    """Panel factor-isolated full-reval P&L plus explicit interaction residual.

    Required portfolio factors must exist on the panel (fail closed). Isolation
    applies only that family's typed panel shocks — not four-macro broadcast.
    """
    require_panel_covers_portfolio(portfolio, panel)
    n = panel.n_observations
    factor_pnl = {k: np.zeros(n, dtype=float) for k in _FACTOR_KEYS}
    base_mv = sum(v.market_value for v in pricing.value_portfolio(portfolio, base_market))

    with bypass_valuation_lru():
        for i, observation in enumerate(panel.observations):
            # Ensure the observation can resolve every required factor before isolating.
            for factor in (
                f for p in portfolio.positions for f in required_factors_for_position(p)
            ):
                observation.change(factor)
            all_shocks = factor_changes_from_panel_observation(observation)
            by_family: dict[str, list[FactorChange]] = {k: [] for k in _FACTOR_KEYS}
            for shock in all_shocks:
                by_family[_factor_family(shock.factor)].append(shock)
            for key in _FACTOR_KEYS:
                shocks = tuple(by_family[key])
                if not shocks:
                    factor_pnl[key][i] = 0.0
                    continue
                scenario = MarketScenario(
                    id=f"es_panel_{key}_{i}",
                    name=f"Panel {key} isolation {i}",
                    shocks=shocks,
                )
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
        factor_panel: HistoricalFactorPanel | None = None,
    ):
        self.seed = seed
        self.observations = observations
        self.dataset: HistoricalMarketDataset = dataset or SyntheticHistoricalDataset(
            seed=seed, observations=observations
        )
        self.methodology = methodology
        self.factor_panel = factor_panel
        self._var = VaRAnalytics(
            seed=seed,
            observations=observations,
            dataset=self.dataset,
            methodology=methodology,
            factor_panel=factor_panel,
        )

    def report(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        confidence: float = 0.99,
        methodology: VaRMethodology | None = None,
        market: MarketSnapshot | None = None,
    ) -> ESContributionReport:
        meth = methodology if methodology is not None else self.methodology
        base_market = require_explicit_market(market)
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

        if self.factor_panel is not None:
            if meth is VaRMethodology.FULL_REVALUATION:
                factor_pnl = _aggregate_factor_pnl_full_reval_from_panel(
                    portfolio, pricing, base_market, self.factor_panel, total_pnl
                )
            else:
                factor_pnl = _aggregate_factor_pnl_from_panel(
                    portfolio, pricing, base_market, self.factor_panel, meth
                )
        elif meth is VaRMethodology.FULL_REVALUATION:
            factor_pnl = _aggregate_factor_pnl_full_reval(
                portfolio, pricing, base_market, self.dataset, total_pnl
            )
        else:
            obs = self.dataset.factor_observations()
            factor_pnl = _aggregate_factor_pnl_linear(
                portfolio,
                pricing,
                base_market,
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
