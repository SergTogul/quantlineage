"""R0.7.3 leftover: PortfolioService produces trade artifacts once for hierarchy.

``hierarchy()`` must value each position once and pass a complete artifact
map into ``HierarchyEngine.build``. It must not reprice once per hierarchy
node. Artifact-path VaR / ES stay omitted (zeros); do not invent them.

Conventions:
- Additive: parent == sum(children) within abs 1e-9 for MV and Greeks
- Sign: same as Valuation / HierarchyNode (currency PV and Greeks)
- Two-trade same-desk book has 7 nodes (firm…book + two trades)
"""

from __future__ import annotations

import math

from app.domain.models import EquityPosition, HierarchyNode, Portfolio
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.trade_artifacts import TradeCalculationArtifact
from app.sample import demo_market_snapshot
from app.services.portfolio_service import PortfolioService

_ADDITIVE_NODE = ("market_value", "delta", "gamma", "vega", "dv01", "fx_delta")


class _CountingPricing(BuiltinPricingEngine):
    def __init__(self) -> None:
        super().__init__()
        self.value_calls = 0

    def value(self, position, market):
        self.value_calls += 1
        return super().value(position, market)


def _two_trade_book() -> Portfolio:
    return Portfolio(
        id="two-trade",
        name="Two Trade Book",
        firm="Acme Capital",
        desk="Equity Desk",
        strategy="Momentum",
        positions=[
            EquityPosition(
                type="equity",
                id="eq-a",
                symbol="AAA",
                quantity=100,
                price=10.0,
                book="Cash",
                desk="Equity Desk",
                strategy="Momentum",
            ),
            EquityPosition(
                type="equity",
                id="eq-b",
                symbol="BBB",
                quantity=50,
                price=20.0,
                book="Cash",
                desk="Equity Desk",
                strategy="Momentum",
            ),
        ],
    )


def _count_nodes(node: HierarchyNode) -> int:
    return 1 + sum(_count_nodes(child) for child in node.children)


def _assert_additive_reconciles(node: HierarchyNode, tol: float = 1e-9) -> None:
    if not node.children:
        return
    for attr in _ADDITIVE_NODE:
        parent = getattr(node, attr)
        child_sum = sum(getattr(c, attr) for c in node.children)
        assert math.isclose(parent, child_sum, abs_tol=tol), (
            f"{node.level}:{node.name} {attr} {parent} != children {child_sum}"
        )
    for child in node.children:
        _assert_additive_reconciles(child, tol)


def test_hierarchy_values_each_position_once_not_once_per_node():
    pf = _two_trade_book()
    pricing = _CountingPricing()
    svc = PortfolioService(pricing, HistoricalRiskEngine(seed=1, observations=20))

    root = svc.hierarchy(pf)

    n_nodes = _count_nodes(root)
    n_positions = len(pf.positions)
    assert n_nodes == 7
    assert n_positions == 2
    assert pricing.value_calls == n_positions
    assert pricing.value_calls < n_nodes


def test_hierarchy_parent_additives_equal_sum_of_trade_valuations():
    pf = _two_trade_book()
    pricing = BuiltinPricingEngine()
    market = demo_market_snapshot(pf)
    expected = TradeCalculationArtifact.from_valuation(
        pricing.value(pf.positions[0], market)
    ).add(
        TradeCalculationArtifact.from_valuation(
            pricing.value(pf.positions[1], market)
        ),
        trade_id="node",
    )

    root = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
    ).hierarchy(pf)

    _assert_additive_reconciles(root)
    assert math.isclose(root.market_value, expected.pv, abs_tol=1e-9)
    assert math.isclose(root.delta, expected.delta, abs_tol=1e-9)
    assert math.isclose(root.gamma, expected.gamma, abs_tol=1e-9)
    assert math.isclose(root.vega, expected.vega, abs_tol=1e-9)
    assert math.isclose(root.dv01, expected.dv01, abs_tol=1e-9)
    assert math.isclose(root.fx_delta, expected.fx_delta, abs_tol=1e-9)


def test_hierarchy_artifact_path_does_not_invent_var_es():
    pf = _two_trade_book()
    root = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
    ).hierarchy(pf)

    assert root.var_95 == 0.0
    assert root.var_99 == 0.0
    assert root.expected_shortfall_99 == 0.0
    assert root.limits == []
