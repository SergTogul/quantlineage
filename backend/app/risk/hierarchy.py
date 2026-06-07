"""First-class portfolio hierarchy (M4.1) with full risk aggregation (M4.2).

Tree: Firm → Portfolio → Desk → Strategy → Book → Trade.

Additive metrics (parent == sum children within abs 1e-9):
  market_value, delta, gamma, vega, dv01, fx_delta, stress scenario P&L.

Node-level metrics (from summed trade historical P&L, not summed VaR):
  var_95, var_99, expected_shortfall_99. Limits stay omitted on the
  artifact aggregation path (concentration / key-rate still need per-node
  pricing or an artifact-aware LimitEngine — R0.7.6 residual).

When ``artifacts`` is supplied to ``build`` / ``risk_at``, additive fields
are summed from ``TradeCalculationArtifact`` and pricing is not invoked.
When ``artifacts`` is omitted, trade artifacts are built **once**:
base ``pricing.value`` per position, shared ``historical_pnl_for_valuation``,
and default-scenario stress P&L via scenario-once / price-many (R0.7.5 /
R0.7.6 / RF-008 leftover). Node VaR / ES come from the summed
``historical_pnl`` vector (same loss = -P&L quantile convention as
``HistoricalRiskEngine.calculate`` / ``test_var_es_golden.py``).
An incomplete explicit map fails closed. Mixed present/absent historical
vectors fail closed via ``TradeCalculationArtifact.add``. All-omitted
vectors keep VaR / ES at zero.

Default-producer stress keys use scenario ``id`` (fallback ``name``), so
``StressResult.scenario`` on the artifact path is the scenario id. The
legacy reprice ``StressEngine.run`` labels rows with ``scenario.name`` —
intentional label difference; P&L math matches when the same scenarios
are applied.

Position-level ``desk`` / ``strategy`` override portfolio defaults when set.
Placement helpers live in ``hierarchy_placement`` (re-exported here for API stability).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

import numpy as np

from app.domain.models import (
    HierarchyLevel,
    HierarchyNode,
    HierarchyRef,
    LimitResult,
    MarketSnapshot,
    Portfolio,
    RiskSummary,
    StressResult,
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
from app.risk.historical import (
    HistoricalRiskEngine,
    historical_pnl_for_valuation,
    require_explicit_market,
)
from app.risk.limits import DEFAULT_LIMITS, LimitEngine
from app.risk.scenario_attribution import ScenarioLike
from app.risk.scenario_engine import apply_scenario
from app.risk.scenario_model import to_canonical_scenario
from app.risk.stress import DEFAULT_SCENARIOS, StressEngine
from app.risk.trade_artifacts import TradeCalculationArtifact


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


def _normalize_artifacts(
    artifacts: Mapping[str, TradeCalculationArtifact] | None,
) -> dict[str, TradeCalculationArtifact] | None:
    if artifacts is None:
        return None
    if isinstance(artifacts, str) or not isinstance(artifacts, Mapping):
        raise TypeError("artifacts must be a mapping of trade id to TradeCalculationArtifact")
    normalized: dict[str, TradeCalculationArtifact] = {}
    for key, art in artifacts.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("artifact keys must be non-empty trade ids")
        if not isinstance(art, TradeCalculationArtifact):
            raise TypeError(
                f"artifacts[{key!r}] must be TradeCalculationArtifact, got {type(art)!r}"
            )
        if art.trade_id != key:
            raise ValueError(
                f"incomplete artifact set: trade_id {art.trade_id!r} does not match key {key!r}"
            )
        normalized[key] = art
    return normalized


def _require_complete_artifacts(
    positions: Sequence,
    artifacts: Mapping[str, TradeCalculationArtifact],
) -> None:
    missing = sorted({p.id for p in positions} - set(artifacts))
    if missing:
        raise ValueError(f"incomplete artifact set; missing trade ids: {missing}")


def _sum_artifacts(
    positions: Sequence,
    artifacts: Mapping[str, TradeCalculationArtifact],
    node_id: str,
) -> TradeCalculationArtifact | None:
    _require_complete_artifacts(positions, artifacts)
    if not positions:
        return None
    total = artifacts[positions[0].id]
    for position in positions[1:]:
        total = total.add(artifacts[position.id], trade_id=node_id)
    return total


def _scenario_ids(
    positions: Sequence,
    artifacts: Mapping[str, TradeCalculationArtifact],
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for position in positions:
        for scenario in artifacts[position.id].stress_pnl:
            if scenario not in seen:
                seen.add(scenario)
                ordered.append(scenario)
    return tuple(ordered)


def _artifact_trade_id(position_id: str) -> str:
    """Stable non-empty artifact trade_id (empty position ids stay map keys)."""
    if isinstance(position_id, str) and position_id.strip():
        return position_id
    return "__empty__"


def _scenario_artifact_key(scenario: ScenarioLike) -> str:
    """Stable stress_pnl key: prefer scenario id, else non-empty name."""
    sid = getattr(scenario, "id", None)
    if isinstance(sid, str) and sid.strip():
        return sid
    name = getattr(scenario, "name", None)
    if isinstance(name, str) and name.strip():
        return name
    raise ValueError("stress scenario must have a non-empty id or name")


def _var_es_from_historical_pnl(
    pnl: Sequence[float] | None,
) -> tuple[float, float, float]:
    """VaR 95/99 and ES 99 from a historical P&L vector.

    Same convention as ``HistoricalRiskEngine.calculate`` and the historical
    method in ``VaRAnalytics.report`` (``var.py`` inlines this; there is no
    extracted helper). Goldens: ``test_var_es_golden.py``.

    - loss = -P&L
    - ``numpy.quantile`` default linear interpolation
    - VaR and ES floored at zero
    - ES is the mean of losses greater than or equal to 99% VaR
    """
    if pnl is None:
        return 0.0, 0.0, 0.0
    series = np.asarray(pnl, dtype=float)
    if series.size == 0:
        return 0.0, 0.0, 0.0
    losses = -series
    var_95 = float(max(0.0, np.quantile(losses, 0.95)))
    var_99 = float(max(0.0, np.quantile(losses, 0.99)))
    tail = losses[losses >= var_99]
    es_99 = float(max(0.0, tail.mean() if len(tail) else var_99))
    return var_95, var_99, es_99


def _stress_from_artifacts(
    summed: TradeCalculationArtifact | None,
    positions: Sequence,
    artifacts: Mapping[str, TradeCalculationArtifact],
    scenario_ids: Sequence[str],
) -> list[StressResult]:
    pnl_by = {} if summed is None else dict(summed.stress_pnl)
    return [
        StressResult(
            scenario=scenario,
            pnl=float(pnl_by.get(scenario, 0.0)),
            by_position={
                p.id: float(artifacts[p.id].stress_pnl.get(scenario, 0.0))
                for p in positions
            },
        )
        for scenario in scenario_ids
    ]


class HierarchyEngine:
    """Build full-metric risk trees and compute risk at an arbitrary hierarchy node."""

    def __init__(
        self,
        risk: RiskEngine,
        *,
        stress_engine: StressEngine | None = None,
        limit_engine: LimitEngine | None = None,
        stress_scenarios: Sequence[ScenarioLike] | None = None,
    ):
        self.risk = risk
        self.stress_engine = stress_engine or StressEngine()
        self.limit_engine = limit_engine or LimitEngine()
        self.stress_scenarios = list(
            stress_scenarios if stress_scenarios is not None else DEFAULT_SCENARIOS
        )

    def _metrics(
        self, portfolio: Portfolio, pricing: PricingEngine, market: MarketSnapshot
    ) -> RiskSummary:
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
        risk: RiskSummary,
        market: MarketSnapshot,
        stress: Sequence[StressResult] | None = None,
    ) -> list[LimitResult]:
        extra: dict[str, float] = {}
        if stress is not None:
            extra["stress_loss"] = max(
                0.0, max((-float(s.pnl) for s in stress), default=0.0)
            )
        return self.limit_engine.evaluate(
            portfolio,
            pricing,
            risk,
            DEFAULT_LIMITS,
            market=market,
            extra=extra or None,
        )

    def _trade_artifacts(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot,
    ) -> dict[str, TradeCalculationArtifact]:
        """Value each trade once; attach historical + default stress P&L.

        Base PV / Greeks: one ``pricing.value`` per position on ``market``.
        Historical vector: ``historical_pnl_for_valuation`` (no extra value).
        Stress: each entry in ``self.stress_scenarios`` (default
        ``DEFAULT_SCENARIOS``) is applied once via ``apply_scenario``, then
        every position is valued on that shocked snapshot (RF-006 / R0.4.5
        scenario-once, price-many). No per-node full stress run.
        """
        valuations = {
            position.id: pricing.value(position, market)
            for position in portfolio.positions
        }
        stress_by_trade: dict[str, dict[str, float]] = {
            position_id: {} for position_id in valuations
        }
        if valuations:
            for scenario in self.stress_scenarios:
                key = _scenario_artifact_key(scenario)
                formal = to_canonical_scenario(scenario, market)
                shocked = apply_scenario(market, formal)
                for position in portfolio.positions:
                    shocked_mv = pricing.value(position, shocked).market_value
                    stress_by_trade[position.id][key] = (
                        shocked_mv - valuations[position.id].market_value
                    )
        artifacts: dict[str, TradeCalculationArtifact] = {}
        for position in portfolio.positions:
            valuation = valuations[position.id]
            artifacts[position.id] = TradeCalculationArtifact.from_valuation(
                valuation,
                trade_id=_artifact_trade_id(position.id),
                historical_pnl=historical_pnl_for_valuation(self.risk, valuation),
                stress_pnl=stress_by_trade[position.id],
            )
        return artifacts

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
        artifacts: Mapping[str, TradeCalculationArtifact] | None = None,
        scenario_ids: Sequence[str] = (),
    ) -> HierarchyNode:
        if artifacts is not None:
            return self._node_from_artifacts(
                name,
                level,
                path,
                portfolio,
                children,
                node_id=node_id,
                artifacts=artifacts,
                scenario_ids=scenario_ids,
            )
        r = self._metrics(portfolio, pricing, market)
        stress = self._stress(portfolio, pricing, market)
        return HierarchyNode(
            id=node_id,
            name=name,
            level=level,  # type: ignore[arg-type]
            path=path,
            market_value=float(r.market_value),
            delta=float(r.delta),
            gamma=float(r.gamma),
            vega=float(r.vega),
            dv01=float(r.dv01),
            fx_delta=float(r.fx_delta),
            var_95=float(r.var_95),
            var_99=float(r.var_99),
            expected_shortfall_99=float(r.expected_shortfall_99),
            stress=stress,
            limits=self._limits(portfolio, pricing, r, market, stress),
            children=list(children or []),
        )

    def _node_from_artifacts(
        self,
        name: str,
        level: str,
        path: str,
        portfolio: Portfolio,
        children: Sequence[HierarchyNode] | None,
        *,
        node_id: str,
        artifacts: Mapping[str, TradeCalculationArtifact],
        scenario_ids: Sequence[str],
    ) -> HierarchyNode:
        summed = _sum_artifacts(portfolio.positions, artifacts, node_id)
        var_95, var_99, es_99 = _var_es_from_historical_pnl(
            None if summed is None else summed.historical_pnl
        )
        return HierarchyNode(
            id=node_id,
            name=name,
            level=level,  # type: ignore[arg-type]
            path=path,
            market_value=0.0 if summed is None else float(summed.pv),
            delta=0.0 if summed is None else float(summed.delta),
            gamma=0.0 if summed is None else float(summed.gamma),
            vega=0.0 if summed is None else float(summed.vega),
            dv01=0.0 if summed is None else float(summed.dv01),
            fx_delta=0.0 if summed is None else float(summed.fx_delta),
            var_95=var_95,
            var_99=var_99,
            expected_shortfall_99=es_99,
            stress=_stress_from_artifacts(
                summed, portfolio.positions, artifacts, scenario_ids
            ),
            limits=[],
            children=list(children or []),
        )

    def risk_at(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        ref: HierarchyRef,
        market: MarketSnapshot | None = None,
        artifacts: Mapping[str, TradeCalculationArtifact] | None = None,
    ) -> HierarchyNode:
        """Full metrics for one hierarchy node (no children)."""
        root_market = require_explicit_market(market)
        artifact_map = _normalize_artifacts(artifacts)
        sub = portfolio_at(portfolio, ref)
        if artifact_map is None:
            artifact_map = self._trade_artifacts(sub, pricing, root_market)
        else:
            _require_complete_artifacts(sub.positions, artifact_map)
        scenario_ids = _scenario_ids(sub.positions, artifact_map)
        return self._node(
            sub.name,
            ref.level.value,
            _ref_path(portfolio, ref),
            sub,
            pricing,
            root_market,
            node_id=sub.id,
            artifacts=artifact_map,
            scenario_ids=scenario_ids,
        )

    def build(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot | None = None,
        artifacts: Mapping[str, TradeCalculationArtifact] | None = None,
    ) -> HierarchyNode:
        """Full Firm → … → Trade tree with NAV/Greeks/VaR/ES/stress/limits per node."""
        root_market = require_explicit_market(market)
        artifact_map = _normalize_artifacts(artifacts)
        if artifact_map is None:
            artifact_map = self._trade_artifacts(portfolio, pricing, root_market)
        else:
            _require_complete_artifacts(portfolio.positions, artifact_map)
        scenario_ids = _scenario_ids(portfolio.positions, artifact_map)
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
                                artifacts=artifact_map,
                                scenario_ids=scenario_ids,
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
                            artifacts=artifact_map,
                            scenario_ids=scenario_ids,
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
                        artifacts=artifact_map,
                        scenario_ids=scenario_ids,
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
                    artifacts=artifact_map,
                    scenario_ids=scenario_ids,
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
            artifacts=artifact_map,
            scenario_ids=scenario_ids,
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
            artifacts=artifact_map,
            scenario_ids=scenario_ids,
        )


__all__ = [
    "HierarchyEngine",
    "filter_positions",
    "hierarchy_node_id",
    "portfolio_at",
    "resolve_desk",
    "resolve_strategy",
]
