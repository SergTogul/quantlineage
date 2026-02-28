"""Scenario contribution decomposition (M3.4 / M4.1).

For each stress scenario, attribute stress P&L by portfolio / desk / strategy /
book / trade and by risk factor. Hierarchy rollups are exact sums of trade P&L.
Desk and strategy keys use ``resolve_desk`` / ``resolve_strategy`` so
per-position placement overrides portfolio defaults. Risk-factor contributions
use factor-isolated full revaluation plus an ``interaction`` residual so the
factor dimension also reconciles to portfolio stress P&L.

Inputs: formal ``Scenario`` (preferred) or legacy ``StressScenario``. Pricing
goes through ``PricingEngine`` / shocked snapshots — no instrument formulas here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Union

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    ScenarioContribution,
    ScenarioContributionBreakdown,
    StressScenario,
)
from app.interfaces.pricing import PricingEngine
from app.risk.hierarchy_placement import resolve_desk, resolve_strategy
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    scenario_from_stress,
    scenario_to_stress,
)
from app.sample import DemoAggregateMarketDataProvider

ScenarioLike = Union[Scenario, StressScenario]

# Cross-factor residual key — always present when any factor shocks exist.
_INTERACTION_KEY = "interaction"
_INTERACTION_LABEL = "Cross-factor interaction"


def _pct(component: float, total: float) -> float:
    return component / total * 100.0 if total else 0.0


def _items_from_pnl_map(
    pnl_by_key: dict[str, float],
    portfolio_pnl: float,
    *,
    labels: dict[str, str] | None = None,
) -> list[ScenarioContribution]:
    labels = labels or {}
    items = [
        ScenarioContribution(
            key=key,
            label=labels.get(key, key),
            pnl=pnl,
            contribution_pct=_pct(pnl, portfolio_pnl),
        )
        for key, pnl in pnl_by_key.items()
    ]
    items.sort(key=lambda x: abs(x.pnl), reverse=True)
    return items


def _reconciliation_error(contributions: list[ScenarioContribution], portfolio_pnl: float) -> float:
    return float(abs(sum(c.pnl for c in contributions) - portfolio_pnl))


def _trade_label(position) -> str:
    pos_type = getattr(position, "type", "trade")
    if hasattr(position, "symbol"):
        return f"{position.symbol} {pos_type}"
    if hasattr(position, "pair"):
        return f"{position.pair} {pos_type}"
    if hasattr(position, "issuer"):
        return f"{position.issuer} {pos_type}"
    if hasattr(position, "currency"):
        return f"{position.currency} {pos_type}"
    return str(position.id)


def _to_formal(scenario: ScenarioLike, base: MarketSnapshot) -> Scenario:
    if isinstance(scenario, Scenario):
        return scenario
    return scenario_from_stress(scenario, base)


def _to_stress(scenario: ScenarioLike, base: MarketSnapshot) -> StressScenario:
    if isinstance(scenario, StressScenario):
        return scenario
    return scenario_to_stress(scenario)


def _portfolio_pnl_by_position(
    portfolio: Portfolio,
    pricing: PricingEngine,
    stress: StressScenario,
    market: MarketSnapshot,
    base_by_position: dict[str, float],
) -> dict[str, float]:
    return {
        p.id: pricing.shocked_value(p, stress, market) - base_by_position[p.id]
        for p in portfolio.positions
    }


def _group_shocks_by_factor_key(shocks: tuple[FactorShock, ...]) -> dict[str, list[FactorShock]]:
    """Bucket typed shocks by ``RiskFactor.key`` (stable API factor id)."""
    grouped: dict[str, list[FactorShock]] = {}
    for shock in shocks:
        if not shock.amount:
            continue
        key = shock.factor.key
        grouped.setdefault(key, []).append(shock)
    return grouped


def _factor_label(shocks: list[FactorShock]) -> str:
    factor = shocks[0].factor
    ftype = factor.factor_type
    if ftype == "equity":
        return f"Equity {factor.key}"
    if ftype == "vol":
        return f"Vol {factor.key}"
    if ftype == "rate":
        return f"Rates {factor.key}"
    if ftype == "fx":
        return f"FX {factor.key}"
    return factor.key


def _factor_isolated_pnl(
    portfolio: Portfolio,
    pricing: PricingEngine,
    formal: Scenario,
    market: MarketSnapshot,
    base_by_position: dict[str, float],
    total_pnl: float,
) -> tuple[dict[str, float], dict[str, str]]:
    """Factor-isolated full-reval P&L + interaction residual, and display labels."""
    grouped = _group_shocks_by_factor_key(formal.shocks)
    if not grouped:
        return {}, {}

    factor_pnl: dict[str, float] = {}
    labels: dict[str, str] = {_INTERACTION_KEY: _INTERACTION_LABEL}
    for key, shocks in grouped.items():
        iso = Scenario(
            id=f"{formal.id}__{key}",
            name=f"{formal.name} [{key}]",
            category=formal.category,
            description=formal.description,
            shocks=tuple(shocks),
            threshold=formal.threshold,
            metadata={"isolated_factor": key},
        )
        iso_stress = scenario_to_stress(iso)
        by_pos = _portfolio_pnl_by_position(portfolio, pricing, iso_stress, market, base_by_position)
        factor_pnl[key] = sum(by_pos.values())
        labels[key] = _factor_label(shocks)

    factor_pnl[_INTERACTION_KEY] = total_pnl - sum(factor_pnl.values())
    return factor_pnl, labels


class ScenarioAttributionEngine:
    """Decompose stress scenario P&L by hierarchy and risk factor (M3.4)."""

    def __init__(self) -> None:
        self.market_data = DemoAggregateMarketDataProvider()

    def decompose(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        scenario: ScenarioLike,
        *,
        market: MarketSnapshot | None = None,
        by_trade_pnl: dict[str, float] | None = None,
    ) -> ScenarioContributionBreakdown:
        """Attribute one scenario's stress P&L across hierarchy and factors.

        Parameters
        ----------
        by_trade_pnl:
            Optional precomputed position P&L under the full scenario (avoids
            a second full revaluation when called from ``StressEngine.evaluate``).
        """
        base_market = market if market is not None else self.market_data.snapshot(portfolio)
        formal = _to_formal(scenario, base_market)
        stress = _to_stress(scenario, base_market)
        scenario_id = formal.id

        if not portfolio.positions:
            empty: list[ScenarioContribution] = []
            return ScenarioContributionBreakdown(
                scenario_id=scenario_id,
                portfolio_pnl=0.0,
                by_portfolio=empty,
                by_desk=empty,
                by_strategy=empty,
                by_book=empty,
                by_trade=empty,
                by_risk_factor=empty,
            )

        base_by_position = {
            p.id: pricing.value(p, base_market).market_value for p in portfolio.positions
        }
        trade_pnl = by_trade_pnl if by_trade_pnl is not None else _portfolio_pnl_by_position(
            portfolio, pricing, stress, base_market, base_by_position
        )
        # Ensure every position appears (zero if missing from caller map).
        trade_pnl = {p.id: float(trade_pnl.get(p.id, 0.0)) for p in portfolio.positions}
        portfolio_pnl = float(sum(trade_pnl.values()))

        pos_by_id = {p.id: p for p in portfolio.positions}
        trade_labels = {p.id: _trade_label(p) for p in portfolio.positions}

        book_pnl: dict[str, float] = defaultdict(float)
        desk_pnl: dict[str, float] = defaultdict(float)
        strategy_pnl: dict[str, float] = defaultdict(float)
        for pid, pnl in trade_pnl.items():
            pos = pos_by_id[pid]
            book_pnl[pos.book] += pnl
            desk_pnl[resolve_desk(pos, portfolio)] += pnl
            strategy_pnl[resolve_strategy(pos, portfolio)] += pnl

        by_trade = _items_from_pnl_map(trade_pnl, portfolio_pnl, labels=trade_labels)
        by_book = _items_from_pnl_map(dict(book_pnl), portfolio_pnl)
        by_strategy = _items_from_pnl_map(dict(strategy_pnl), portfolio_pnl)
        by_desk = _items_from_pnl_map(dict(desk_pnl), portfolio_pnl)
        by_portfolio = _items_from_pnl_map(
            {portfolio.id: portfolio_pnl},
            portfolio_pnl,
            labels={portfolio.id: portfolio.name},
        )

        factor_pnl, factor_labels = _factor_isolated_pnl(
            portfolio, pricing, formal, base_market, base_by_position, portfolio_pnl
        )
        by_risk_factor = (
            _items_from_pnl_map(factor_pnl, portfolio_pnl, labels=factor_labels)
            if factor_pnl
            else []
        )

        return ScenarioContributionBreakdown(
            scenario_id=scenario_id,
            portfolio_pnl=portfolio_pnl,
            by_portfolio=by_portfolio,
            by_desk=by_desk,
            by_strategy=by_strategy,
            by_book=by_book,
            by_trade=by_trade,
            by_risk_factor=by_risk_factor,
            reconciliation_error_portfolio=_reconciliation_error(by_portfolio, portfolio_pnl),
            reconciliation_error_desk=_reconciliation_error(by_desk, portfolio_pnl),
            reconciliation_error_strategy=_reconciliation_error(by_strategy, portfolio_pnl),
            reconciliation_error_book=_reconciliation_error(by_book, portfolio_pnl),
            reconciliation_error_trade=_reconciliation_error(by_trade, portfolio_pnl),
            reconciliation_error_risk_factor=_reconciliation_error(by_risk_factor, portfolio_pnl),
        )


__all__ = ["ScenarioAttributionEngine", "ScenarioLike"]
