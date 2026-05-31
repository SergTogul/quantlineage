"""Scenario contribution decomposition (M3.4 / M4.1).

For each stress scenario, attribute stress P&L by portfolio / desk / strategy /
book / trade and by risk factor. Hierarchy rollups are exact sums of trade P&L.
Desk and strategy keys use ``resolve_desk`` / ``resolve_strategy`` so
per-position placement overrides portfolio defaults. Risk-factor contributions
reuse the joint trade/scenario P&L (one shocked snapshot) and the additive
Greek split from the same base valuations, plus an ``interaction`` residual so
the factor dimension reconciles to portfolio stress P&L.

Inputs: canonical ``Scenario`` after a one-shot ``to_canonical_scenario``
adapt at the engine/HTTP boundary. Pricing goes through ``PricingEngine`` /
shocked snapshots — no instrument formulas here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Union

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    Position,
    ScenarioContribution,
    ScenarioContributionBreakdown,
    StressScenario,
    Valuation,
)
from app.interfaces.pricing import PricingEngine
from app.risk.factor_types import EquitySpot, RateZero
from app.risk.hierarchy_placement import resolve_desk, resolve_strategy
from app.risk.historical import (
    _panel_linear_contribution,
    require_explicit_market,
    required_factors_for_position,
)
from app.risk.scenario_engine import apply_scenario
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    to_canonical_scenario,
)
from app.risk.shock_units import decimal_rate_to_bps
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
    return to_canonical_scenario(scenario, base)


def _portfolio_pnl_by_position(
    portfolio: Portfolio,
    pricing: PricingEngine,
    scenario: Scenario,
    market: MarketSnapshot,
    base_by_position: dict[str, float],
) -> dict[str, float]:
    # One shocked snapshot per scenario, then revalue every position — do not
    # rebuild via shocked_value per trade. Canonical Scenario applies directly
    # (no scenario_to_stress collapse).
    shocked = apply_scenario(market, scenario)
    return {
        p.id: pricing.value(p, shocked).market_value - base_by_position[p.id]
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


def _factor_keys_for_position(position: Position) -> set[str] | None:
    """Risk-factor keys this position is sensitive to, or None if unmapped."""
    try:
        return {factor.key for factor in required_factors_for_position(position)}
    except TypeError:
        return None


def _linear_shock_pnl(valuation: Valuation, shock: FactorShock) -> float:
    """Additive Greek P&L for one typed shock (same units as panel LINEAR/Δ-Γ)."""
    factor = shock.factor
    move = decimal_rate_to_bps(shock.amount) if isinstance(factor, RateZero) else float(shock.amount)
    pnl = _panel_linear_contribution(factor, valuation, move)
    if isinstance(factor, EquitySpot):
        pnl += 0.5 * float(valuation.gamma) * move * move
    return pnl


def _factor_isolated_pnl(
    portfolio: Portfolio,
    formal: Scenario,
    base_valuations: dict[str, Valuation],
    total_pnl: float,
) -> tuple[dict[str, float], dict[str, str]]:
    """Family P&L from base Greeks + shocks; interaction vs joint scenario P&L.

    Does not apply isolated-factor sub-scenarios or reprice the book per factor.
    """
    grouped = _group_shocks_by_factor_key(formal.shocks)
    if not grouped:
        return {}, {}

    factor_pnl: dict[str, float] = {}
    labels: dict[str, str] = {_INTERACTION_KEY: _INTERACTION_LABEL}
    for key, shocks in grouped.items():
        attributed = 0.0
        for position in portfolio.positions:
            keys = _factor_keys_for_position(position)
            valuation = base_valuations[position.id]
            for shock in shocks:
                if keys is not None and shock.factor.key not in keys:
                    continue
                attributed += _linear_shock_pnl(valuation, shock)
        factor_pnl[key] = attributed
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

        ``market`` must be an explicit ``MarketSnapshot``. Omitted or ``None``
        raises the same ``ValueError`` as VaR / hierarchy (no demo inference).

        Parameters
        ----------
        by_trade_pnl:
            Optional precomputed position P&L under the full scenario (avoids
            a second full revaluation when called from ``StressEngine.evaluate``).
        """
        base_market = require_explicit_market(market)
        formal = _to_formal(scenario, base_market)
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

        base_valuations = {
            p.id: pricing.value(p, base_market) for p in portfolio.positions
        }
        base_by_position = {pid: v.market_value for pid, v in base_valuations.items()}
        trade_pnl = by_trade_pnl if by_trade_pnl is not None else _portfolio_pnl_by_position(
            portfolio, pricing, formal, base_market, base_by_position
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
            portfolio, formal, base_valuations, portfolio_pnl
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
