"""R0.7.3 / R0.7.5 / R0.7.6: hierarchy consumes TradeCalculationArtifact.

When a complete artifact map is supplied, parent additive fields equal the
sum of trade artifacts and pricing is not invoked. Incomplete maps fail
closed (no silent mix of reprice + artifacts).

When ``artifacts`` is omitted, ``HierarchyEngine`` builds the trade-grain
map once (base ``pricing.value`` + default-scenario stress via
scenario-once / price-many) then aggregates — it must not reprice once
per hierarchy node (R0.7.5 / R0.7.6 / RF-008 leftover).

Conventions:
- Additive: parent == sum(children) within abs 1e-9 for MV, Greeks, stress P&L
- Sign: same as Valuation / HierarchyNode (currency PV and Greeks)
- Value budget on default path: N_positions × (1 + N_scenarios)
- apply_scenario count ≈ N_scenarios (not × nodes)
"""
from __future__ import annotations

import math

import pytest
from tests.market_fixtures import equity_spots_market

import app.risk.hierarchy as hierarchy_mod
from app.domain.models import (
    EquityPosition,
    HierarchyLevel,
    HierarchyNode,
    HierarchyRef,
    MarketSnapshot,
    Portfolio,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.hierarchy import HierarchyEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.stress import DEFAULT_SCENARIOS, StressEngine
from app.risk.trade_artifacts import TradeCalculationArtifact

_ADDITIVE_NODE = ("market_value", "delta", "gamma", "vega", "dv01", "fx_delta")
_N_DEFAULT_SCENARIOS = len(DEFAULT_SCENARIOS)


class _ForbiddenPricing:
    """Fails if any pricing entry point is used."""

    def value(self, position, market=None):
        raise AssertionError("pricing.value must not be called when artifacts are supplied")

    def value_portfolio(self, portfolio, market=None):
        raise AssertionError(
            "pricing.value_portfolio must not be called when artifacts are supplied"
        )

    def shocked_value(self, position, scenario, market=None):
        raise AssertionError(
            "pricing.shocked_value must not be called when artifacts are supplied"
        )


class _CountingPricing(BuiltinPricingEngine):

    def __init__(self) -> None:
        super().__init__()
        self.value_calls = 0
        self.value_portfolio_calls = 0
        self.shocked_value_calls = 0

    def value(self, position, market):
        self.value_calls += 1
        return super().value(position, market)

    def value_portfolio(self, portfolio, market=None):
        self.value_portfolio_calls += 1
        return super().value_portfolio(portfolio, market)

    def shocked_value(self, position, scenario, market=None):
        self.shocked_value_calls += 1
        return super().shocked_value(position, scenario, market)


class _FirstPassThenForbidden(BuiltinPricingEngine):
    """Allows exactly ``budget`` ``value`` calls, then forbids further pricing."""

    def __init__(self, budget: int) -> None:
        super().__init__()
        self.budget = budget
        self.value_calls = 0

    def value(self, position, market):
        self.value_calls += 1
        if self.value_calls > self.budget:
            raise AssertionError(
                f"pricing.value called {self.value_calls} times; budget was {self.budget}"
            )
        return super().value(position, market)

    def value_portfolio(self, portfolio, market=None):
        raise AssertionError("pricing.value_portfolio must not be used after trade artifacts")

    def shocked_value(self, position, scenario, market=None):
        raise AssertionError("pricing.shocked_value must not be used on default artifact path")


def _artifact(
    trade_id: str,
    *,
    pv: float,
    delta: float,
    gamma: float = 0.0,
    vega: float = 0.0,
    dv01: float = 0.0,
    fx_delta: float = 0.0,
    stress_pnl: dict[str, float] | None = None,
) -> TradeCalculationArtifact:
    return TradeCalculationArtifact.from_parts(
        trade_id,
        pv=pv,
        delta=delta,
        gamma=gamma,
        vega=vega,
        dv01=dv01,
        fx_delta=fx_delta,
        stress_pnl=stress_pnl,
    )


def _two_trade_market() -> MarketSnapshot:
    return equity_spots_market({"AAA": 100.0, "BBB": 80.0})


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
                book="Cash",
                desk="Equity Desk",
                strategy="Momentum",
            ),
            EquityPosition(
                type="equity",
                id="eq-b",
                symbol="BBB",
                quantity=50,
                book="Cash",
                desk="Equity Desk",
                strategy="Momentum",
            ),
        ],
    )


def _complete_artifacts() -> dict[str, TradeCalculationArtifact]:
    return {
        "eq-a": _artifact(
            "eq-a",
            pv=100.0,
            delta=10.0,
            gamma=0.5,
            vega=2.0,
            dv01=0.1,
            fx_delta=3.0,
            stress_pnl={"eq_crash": -10.0, "rate_up": -2.0},
        ),
        "eq-b": _artifact(
            "eq-b",
            pv=40.0,
            delta=-4.0,
            gamma=0.25,
            vega=1.5,
            dv01=-0.02,
            fx_delta=1.0,
            stress_pnl={"eq_crash": -5.0, "fx_shock": 1.5},
        ),
    }


def _engine() -> HierarchyEngine:
    return HierarchyEngine(HistoricalRiskEngine(seed=1, observations=20))


def _count_nodes(node: HierarchyNode) -> int:
    return 1 + sum(_count_nodes(child) for child in node.children)


def _default_value_budget(n_positions: int) -> int:
    return n_positions * (1 + _N_DEFAULT_SCENARIOS)


def _assert_additive_reconciles(node: HierarchyNode, tol: float = 1e-09) -> None:
    if not node.children:
        return
    for attr in _ADDITIVE_NODE:
        parent = getattr(node, attr)
        child_sum = sum(getattr(c, attr) for c in node.children)
        assert math.isclose(parent, child_sum, abs_tol=tol), (
            f"{node.level}:{node.name} {attr} {parent} != children {child_sum}"
        )
    parent_stress = {s.scenario: s.pnl for s in node.stress}
    for scenario, parent_pnl in parent_stress.items():
        child_sum = sum(
            next(s.pnl for s in c.stress if s.scenario == scenario) for c in node.children
        )
        assert math.isclose(parent_pnl, child_sum, abs_tol=tol), (
            f"{node.level}:{node.name} stress[{scenario}] {parent_pnl} != {child_sum}"
        )
    for child in node.children:
        _assert_additive_reconciles(child, tol)


def test_parent_additive_metrics_equal_sum_of_artifacts_without_pricing():
    pf = _two_trade_book()
    artifacts = _complete_artifacts()
    expected = artifacts["eq-a"].add(artifacts["eq-b"], trade_id="node")
    root = _engine().build(
        pf, _ForbiddenPricing(), market=_two_trade_market(), artifacts=artifacts
    )
    _assert_additive_reconciles(root)
    assert math.isclose(root.market_value, expected.pv, abs_tol=1e-09)
    assert math.isclose(root.delta, expected.delta, abs_tol=1e-09)
    assert math.isclose(root.gamma, expected.gamma, abs_tol=1e-09)
    assert math.isclose(root.vega, expected.vega, abs_tol=1e-09)
    assert math.isclose(root.dv01, expected.dv01, abs_tol=1e-09)
    assert math.isclose(root.fx_delta, expected.fx_delta, abs_tol=1e-09)
    parent_stress = {s.scenario: s.pnl for s in root.stress}
    assert parent_stress == dict(expected.stress_pnl)
    assert parent_stress["eq_crash"] == -15.0
    assert parent_stress["rate_up"] == -2.0
    assert parent_stress["fx_shock"] == 1.5
    trades = [
        n
        for n in root.children[0].children[0].children[0].children[0].children
        if n.level == "trade"
    ]
    by_id = {t.name: t for t in trades}
    assert math.isclose(by_id["eq-a"].market_value, 100.0, abs_tol=1e-09)
    assert math.isclose(by_id["eq-b"].market_value, 40.0, abs_tol=1e-09)


def test_incomplete_artifact_set_fails_closed():
    pf = _two_trade_book()
    artifacts = {"eq-a": _complete_artifacts()["eq-a"]}
    with pytest.raises(ValueError, match="incomplete"):
        _engine().build(
            pf, _ForbiddenPricing(), market=_two_trade_market(), artifacts=artifacts
        )


def test_artifact_key_mismatch_fails_closed():
    pf = _two_trade_book()
    swapped = _complete_artifacts()
    artifacts = {"eq-a": swapped["eq-b"], "eq-b": swapped["eq-a"]}
    with pytest.raises(ValueError, match="incomplete"):
        _engine().build(
            pf, _ForbiddenPricing(), market=_two_trade_market(), artifacts=artifacts
        )


def test_risk_at_sums_artifacts_without_pricing():
    pf = _two_trade_book()
    artifacts = _complete_artifacts()
    expected = artifacts["eq-a"].add(artifacts["eq-b"], trade_id="node")
    ref = HierarchyRef(
        level=HierarchyLevel.BOOK,
        firm="Acme Capital",
        portfolio_id="two-trade",
        desk="Equity Desk",
        strategy="Momentum",
        book="Cash",
    )
    node = _engine().risk_at(
        pf, _ForbiddenPricing(), ref, market=_two_trade_market(), artifacts=artifacts
    )
    assert node.level == "book"
    assert math.isclose(node.market_value, expected.pv, abs_tol=1e-09)
    assert math.isclose(node.delta, expected.delta, abs_tol=1e-09)
    parent_stress = {s.scenario: s.pnl for s in node.stress}
    assert parent_stress["eq_crash"] == -15.0


def test_omitted_artifacts_values_each_trade_once_not_once_per_node():
    """R0.7.5/R0.7.6: default build prices base once + S shocked passes, not per node."""
    pf = _two_trade_book()
    pricing = _CountingPricing()
    root = _engine().build(pf, pricing, market=_two_trade_market())
    n_nodes = _count_nodes(root)
    n_positions = len(pf.positions)
    assert n_nodes == 7
    assert n_positions == 2
    assert pricing.value_calls == _default_value_budget(n_positions)
    assert pricing.value_calls < n_nodes * (1 + _N_DEFAULT_SCENARIOS)
    assert pricing.value_portfolio_calls == 0
    assert pricing.shocked_value_calls == 0
    assert root.market_value != 0.0
    assert root.limits == []
    assert {s.scenario for s in root.stress} == {s.id for s in DEFAULT_SCENARIOS}


def test_omitted_artifacts_forbid_pricing_after_first_pass():
    """After the trade-grain pass (base + stress), aggregation must not call pricing again."""
    pf = _two_trade_book()
    budget = _default_value_budget(len(pf.positions))
    pricing = _FirstPassThenForbidden(budget=budget)
    root = _engine().build(pf, pricing, market=_two_trade_market())
    assert pricing.value_calls == budget
    assert math.isclose(root.market_value, 100.0 * 100 + 80.0 * 50, abs_tol=1e-09)


def test_risk_at_omitted_artifacts_values_subset_once():
    pf = _two_trade_book()
    pricing = _CountingPricing()
    ref = HierarchyRef(
        level=HierarchyLevel.BOOK,
        firm="Acme Capital",
        portfolio_id="two-trade",
        desk="Equity Desk",
        strategy="Momentum",
        book="Cash",
    )
    node = _engine().risk_at(pf, pricing, ref, market=_two_trade_market())
    assert pricing.value_calls == _default_value_budget(2)
    assert pricing.shocked_value_calls == 0
    assert node.limits == []
    assert math.isclose(node.market_value, 14000.0, abs_tol=1e-09)
    assert {s.scenario for s in node.stress} == {s.id for s in DEFAULT_SCENARIOS}


def test_default_producer_stress_sums_to_parent_and_matches_stress_engine():
    """R0.7.6: node stress P&L is sum of trade artifacts; matches StressEngine.run."""
    pf = _two_trade_book()
    market = _two_trade_market()
    pricing = BuiltinPricingEngine()
    root = _engine().build(pf, pricing, market=market)
    _assert_additive_reconciles(root)
    expected = {
        r.scenario: r.pnl
        for r in StressEngine().run(
            pf, BuiltinPricingEngine(), DEFAULT_SCENARIOS, market=market
        )
    }
    # StressEngine labels by name; artifact path by id — compare via id→name map.
    id_to_name = {s.id: s.name for s in DEFAULT_SCENARIOS}
    by_id = {s.scenario: s.pnl for s in root.stress}
    assert set(by_id) == set(id_to_name)
    for sid, pnl in by_id.items():
        assert math.isclose(pnl, expected[id_to_name[sid]], abs_tol=1e-09)


def test_default_producer_apply_scenario_once_per_scenario_not_per_node(monkeypatch):
    """R0.7.6: apply_scenario ≈ S, not S × nodes."""
    pf = _two_trade_book()
    pricing = _CountingPricing()
    real_apply = hierarchy_mod.apply_scenario
    calls: list[object] = []

    def counting_apply(base, scen, **kwargs):
        calls.append(scen)
        return real_apply(base, scen, **kwargs)

    monkeypatch.setattr(hierarchy_mod, "apply_scenario", counting_apply)
    root = _engine().build(pf, pricing, market=_two_trade_market())
    n_nodes = _count_nodes(root)
    assert len(calls) == _N_DEFAULT_SCENARIOS
    assert len(calls) < _N_DEFAULT_SCENARIOS * n_nodes
    assert pricing.value_calls == _default_value_budget(len(pf.positions))
    assert root.stress
