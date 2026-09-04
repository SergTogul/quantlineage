"""First-class portfolio hierarchy (M4.1) with full risk aggregation (M4.2).

Tree: Firm → Portfolio → Desk → Strategy → Book → Trade.

Additive metrics (parent == sum children within abs 1e-9):
  market_value, delta, gamma, vega, dv01, fx_delta, stress scenario P&L.

Node-level metrics (computed on the position subset, not summed):
  var_95, var_99, expected_shortfall_99, limits.

Position-level ``desk`` / ``strategy`` override portfolio defaults when set.
Placement helpers live in ``hierarchy_placement`` (re-exported here for API stability).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from app.domain.models import (
    HierarchyLevel,
    HierarchyNode,
    HierarchyRef,
    LimitResult,
    MarketSnapshot,
    Portfolio,
    StressResult,
    StressScenario,
)
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.risk.hierarchy_placement import (
    filter_positions,
    hierarchy_node_id,
    portfolio_at,
    resolve_desk,
    resolve_strategy,
)
from app.risk.historical import HistoricalRiskEngine, require_explicit_market
from app.risk.limits import DEFAULT_LIMITS, LimitEngine
from app.risk.stress import DEFAULT_SCENARIOS, StressEngine


def _path(*parts: str) -> str:
    return "/".join(parts)


def _ref_path(portfolio: Portfolio, ref: HierarchyRef) -> str:
    path_parts = [portfolio.firm]
    if ref.level is not HierarchyLevel.FIRM:
        path_parts.append(portfolio.id)
    if ref.desk is not None and ref.level in (
        HierarchyLevel.DESK,
        HierarchyLevel.STRATEGY,
        HierarchyLevel.BOOK,
        HierarchyLevel.TRADE,
    ):
        path_parts.append(ref.desk)
    if ref.strategy is not None and ref.level in (
        HierarchyLevel.STRATEGY,
        HierarchyLevel.BOOK,
        HierarchyLevel.TRADE,
    ):
        path_parts.append(ref.strategy)
    if ref.book is not None and ref.level in (HierarchyLevel.BOOK, HierarchyLevel.TRADE):
        path_parts.append(ref.book)
    if ref.trade_id is not None and ref.level is HierarchyLevel.TRADE:
        path_parts.append(ref.trade_id)
    return _path(*path_parts)


class HierarchyEngine:
    """Build full-metric risk trees and compute risk at an arbitrary hierarchy node."""

    def __init__(
        self,
        risk: RiskEngine,
        *,
        stress_engine: StressEngine | None = None,
        limit_engine: LimitEngine | None = None,
        stress_scenarios: list[StressScenario] | None = None,
    ):
        self.risk = risk
        self.stress_engine = stress_engine or StressEngine()
        self.limit_engine = limit_engine or LimitEngine()
        self.stress_scenarios = list(
            stress_scenarios if stress_scenarios is not None else DEFAULT_SCENARIOS
        )

    def _metrics(
        self, portfolio: Portfolio, pricing: PricingEngine, market: MarketSnapshot
    ) -> dict:
        if isinstance(self.risk, HistoricalRiskEngine):
            return self.risk.calculate(portfolio, pricing, market=market)
        return self.risk.calculate(portfolio, pricing)

    def _stress(
        self, portfolio: Portfolio, pricing: PricingEngine, market: MarketSnapshot
    ) -> list[StressResult]:
        return self.stress_engine.run(
            portfolio, pricing, self.stress_scenarios, market=market
        )

    def _limits(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        risk: dict,
        market: MarketSnapshot,
        stress: Sequence[StressResult] | None = None,
    ) -> list[LimitResult]:
        enriched = dict(risk)
        if stress is not None and "stress_loss" not in enriched:
            enriched["stress_loss"] = max(
                0.0, max((-float(s.pnl) for s in stress), default=0.0)
            )
        return self.limit_engine.evaluate(
            portfolio,
            pricing,
            enriched,
            DEFAULT_LIMITS,
            market=market,
        )

    def _node(
        self,
        name: str,
        level: str,
        path: str,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot,
        children: Sequence[HierarchyNode] | None = None,
        *,
        node_id: str,
    ) -> HierarchyNode:
        r = self._metrics(portfolio, pricing, market)
        stress = self._stress(portfolio, pricing, market)
        return HierarchyNode(
            id=node_id,
            name=name,
            level=level,  # type: ignore[arg-type]
            path=path,
            market_value=float(r["market_value"]),
            delta=float(r.get("delta", 0.0)),
            gamma=float(r.get("gamma", 0.0)),
            vega=float(r.get("vega", 0.0)),
            dv01=float(r.get("dv01", 0.0)),
            fx_delta=float(r.get("fx_delta", 0.0)),
            var_95=float(r.get("var_95", 0.0)),
            var_99=float(r["var_99"]),
            expected_shortfall_99=float(r.get("expected_shortfall_99", 0.0)),
            stress=stress,
            limits=self._limits(portfolio, pricing, r, market, stress),
            children=list(children or []),
        )

    def risk_at(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        ref: HierarchyRef,
        market: MarketSnapshot | None = None,
    ) -> HierarchyNode:
        """Full metrics for one hierarchy node (no children)."""
        root_market = require_explicit_market(market)
        sub = portfolio_at(portfolio, ref)
        return self._node(
            sub.name,
            ref.level.value,
            _ref_path(portfolio, ref),
            sub,
            pricing,
            root_market,
            node_id=sub.id,
        )

    def build(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot | None = None,
    ) -> HierarchyNode:
        """Full Firm → … → Trade tree with NAV/Greeks/VaR/ES/stress/limits per node."""
        root_market = require_explicit_market(market)
        # desk -> strategy -> book -> [positions]
        tree: dict[str, dict[str, dict[str, list]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        for p in portfolio.positions:
            tree[resolve_desk(p, portfolio)][resolve_strategy(p, portfolio)][p.book].append(p)

        firm_path = portfolio.firm
        portfolio_path = _path(firm_path, portfolio.id)

        desk_nodes: list[HierarchyNode] = []
        for desk_name in sorted(tree):
            desk_path = _path(portfolio_path, desk_name)
            strategy_nodes: list[HierarchyNode] = []
            desk_positions: list = []
            for strategy_name in sorted(tree[desk_name]):
                strategy_path = _path(desk_path, strategy_name)
                book_nodes: list[HierarchyNode] = []
                strategy_positions: list = []
                for book_name in sorted(tree[desk_name][strategy_name]):
                    positions = tree[desk_name][strategy_name][book_name]
                    strategy_positions.extend(positions)
                    desk_positions.extend(positions)
                    book_path = _path(strategy_path, book_name)
                    trade_nodes = []
                    for p in sorted(positions, key=lambda x: x.id):
                        trade_pf = Portfolio(
                            id=hierarchy_node_id(
                                "trade",
                                firm=portfolio.firm,
                                portfolio_id=portfolio.id,
                                desk=desk_name,
                                strategy=strategy_name,
                                book=book_name,
                                trade_id=p.id,
                            ),
                            name=p.id,
                            positions=[p],
                            firm=portfolio.firm,
                            desk=desk_name,
                            strategy=strategy_name,
                        )
                        trade_nodes.append(
                            self._node(
                                p.id,
                                "trade",
                                _path(book_path, p.id),
                                trade_pf,
                                pricing,
                                root_market,
                                node_id=hierarchy_node_id(
                                    "trade",
                                    firm=portfolio.firm,
                                    portfolio_id=portfolio.id,
                                    desk=desk_name,
                                    strategy=strategy_name,
                                    book=book_name,
                                    trade_id=p.id,
                                ),
                            )
                        )
                    book_pf = Portfolio(
                        id=hierarchy_node_id(
                            "book",
                            firm=portfolio.firm,
                            portfolio_id=portfolio.id,
                            desk=desk_name,
                            strategy=strategy_name,
                            book=book_name,
                        ),
                        name=book_name,
                        positions=positions,
                        firm=portfolio.firm,
                        desk=desk_name,
                        strategy=strategy_name,
                    )
                    book_nodes.append(
                        self._node(
                            book_name,
                            "book",
                            book_path,
                            book_pf,
                            pricing,
                            root_market,
                            trade_nodes,
                            node_id=hierarchy_node_id(
                                "book",
                                firm=portfolio.firm,
                                portfolio_id=portfolio.id,
                                desk=desk_name,
                                strategy=strategy_name,
                                book=book_name,
                            ),
                        )
                    )
                strategy_pf = Portfolio(
                    id=hierarchy_node_id(
                        "strategy",
                        firm=portfolio.firm,
                        portfolio_id=portfolio.id,
                        desk=desk_name,
                        strategy=strategy_name,
                    ),
                    name=strategy_name,
                    positions=strategy_positions,
                    firm=portfolio.firm,
                    desk=desk_name,
                    strategy=strategy_name,
                )
                strategy_nodes.append(
                    self._node(
                        strategy_name,
                        "strategy",
                        strategy_path,
                        strategy_pf,
                        pricing,
                        root_market,
                        book_nodes,
                        node_id=hierarchy_node_id(
                            "strategy",
                            firm=portfolio.firm,
                            portfolio_id=portfolio.id,
                            desk=desk_name,
                            strategy=strategy_name,
                        ),
                    )
                )
            desk_pf = Portfolio(
                id=hierarchy_node_id(
                    "desk",
                    firm=portfolio.firm,
                    portfolio_id=portfolio.id,
                    desk=desk_name,
                ),
                name=desk_name,
                positions=desk_positions,
                firm=portfolio.firm,
                desk=desk_name,
                strategy=portfolio.strategy,
            )
            desk_nodes.append(
                self._node(
                    desk_name,
                    "desk",
                    desk_path,
                    desk_pf,
                    pricing,
                    root_market,
                    strategy_nodes,
                    node_id=hierarchy_node_id(
                        "desk",
                        firm=portfolio.firm,
                        portfolio_id=portfolio.id,
                        desk=desk_name,
                    ),
                )
            )

        portfolio_node = self._node(
            portfolio.name,
            "portfolio",
            portfolio_path,
            portfolio,
            pricing,
            root_market,
            desk_nodes,
            node_id=hierarchy_node_id(
                "portfolio",
                firm=portfolio.firm,
                portfolio_id=portfolio.id,
            ),
        )
        return self._node(
            portfolio.firm,
            "firm",
            firm_path,
            portfolio,
            pricing,
            root_market,
            [portfolio_node],
            node_id=hierarchy_node_id(
                "firm",
                firm=portfolio.firm,
                portfolio_id=portfolio.id,
            ),
        )


__all__ = [
    "HierarchyEngine",
    "filter_positions",
    "hierarchy_node_id",
    "portfolio_at",
    "resolve_desk",
    "resolve_strategy",
]
