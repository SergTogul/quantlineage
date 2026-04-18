"""R0.7.3 leftover: PortfolioService produces trade artifacts once for hierarchy.

``hierarchy()`` must value each position once and pass a complete artifact
map into ``HierarchyEngine.build``. It must not reprice once per hierarchy
node. Per-trade historical P&L is attached once (``approximate_pnl_series``
on already-valued Greeks); node VaR / ES are VaR / ES of the summed vector.

Conventions:
- Additive: parent == sum(children) within abs 1e-9 for MV and Greeks
- VaR / ES: loss = -P&L; numpy.quantile default linear; floor at 0;
  ES = mean of losses >= VaR (same as ``test_var_es_golden.py``)
- Sign: same as Valuation / HierarchyNode (currency PV and Greeks)
- Two-trade same-desk book has 7 nodes (firm…book + two trades)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.domain.models import EquityPosition, HierarchyNode, Portfolio
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine, approximate_pnl_series
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


def _var_es_from_pnl(pnl: np.ndarray) -> tuple[float, float, float]:
    """Independent golden-convention VaR 95/99 and ES 99."""
    losses = -np.asarray(pnl, dtype=float)
    var_95 = float(max(0.0, np.quantile(losses, 0.95)))
    var_99 = float(max(0.0, np.quantile(losses, 0.99)))
    tail = losses[losses >= var_99]
    es_99 = float(max(0.0, tail.mean() if len(tail) else var_99))
    return var_95, var_99, es_99


def test_hierarchy_artifact_path_var_es_equals_summed_trade_vectors():
    """Node VaR/ES = golden VaR/ES of the summed per-trade historical vectors.

    Independent reconstruction: one ``approximate_pnl_series`` per already-
    valued trade (same seed/observations/methodology as the service). Does
    not invent numbers. Limits stay omitted.
    """
    pf = _two_trade_book()
    pricing = _CountingPricing()
    engine = HistoricalRiskEngine(seed=1, observations=20)
    svc = PortfolioService(pricing, engine)
    market = svc.market_snapshot(pf)
    obs = engine.dataset.factor_observations()
    series = []
    for position in pf.positions:
        valuation = BuiltinPricingEngine().value(position, market)
        series.append(
            approximate_pnl_series(
                delta=valuation.delta,
                gamma=valuation.gamma,
                vega=valuation.vega,
                dv01=valuation.dv01,
                fx_delta=valuation.fx_delta,
                equity_ret=obs.equity_returns,
                vol_pct=obs.vol_moves,
                rates_bps=obs.rate_moves_bps,
                fx_ret=obs.fx_returns,
                methodology=engine.methodology,
            )
        )
    expected_95, expected_99, expected_es = _var_es_from_pnl(series[0] + series[1])

    root = svc.hierarchy(pf)

    assert pricing.value_calls == len(pf.positions)
    assert root.var_95 == pytest.approx(expected_95, rel=0, abs=1e-12)
    assert root.var_99 == pytest.approx(expected_99, rel=0, abs=1e-12)
    assert root.expected_shortfall_99 == pytest.approx(expected_es, rel=0, abs=1e-12)
    assert root.var_99 != 0.0
    assert root.limits == []
