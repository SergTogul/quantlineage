"""R0.7.3: hierarchy consumes TradeCalculationArtifact for additive metrics.

When a complete artifact map is supplied, parent additive fields equal the
sum of trade artifacts and pricing is not invoked. Incomplete maps fail
closed (no silent mix of reprice + artifacts).

VaR / ES / limits are omitted on the artifact path (not invented from
vectors; node VaR from historical P&L is later). The default no-artifact
path still full-reprices (RF-008 stays open).

Conventions:
- Additive: parent == sum(children) within abs 1e-9 for MV, Greeks, stress P&L
- Sign: same as Valuation / HierarchyNode (currency PV and Greeks)
"""

from __future__ import annotations

import math

import pytest

from app.domain.models import (
    EquityPosition,
    HierarchyLevel,
    HierarchyNode,
    HierarchyRef,
    Portfolio,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.hierarchy import HierarchyEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.trade_artifacts import TradeCalculationArtifact
from app.sample import demo_market_snapshot

_ADDITIVE_NODE = ("market_value", "delta", "gamma", "vega", "dv01", "fx_delta")


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

    def value(self, position, market):
        self.value_calls += 1
        return super().value(position, market)


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


def _assert_additive_reconciles(node: HierarchyNode, tol: float = 1e-9) -> None:
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
        pf,
        _ForbiddenPricing(),
        market=demo_market_snapshot(pf),
        artifacts=artifacts,
    )

    _assert_additive_reconciles(root)
    assert math.isclose(root.market_value, expected.pv, abs_tol=1e-9)
    assert math.isclose(root.delta, expected.delta, abs_tol=1e-9)
    assert math.isclose(root.gamma, expected.gamma, abs_tol=1e-9)
    assert math.isclose(root.vega, expected.vega, abs_tol=1e-9)
    assert math.isclose(root.dv01, expected.dv01, abs_tol=1e-9)
    assert math.isclose(root.fx_delta, expected.fx_delta, abs_tol=1e-9)

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
    assert math.isclose(by_id["eq-a"].market_value, 100.0, abs_tol=1e-9)
    assert math.isclose(by_id["eq-b"].market_value, 40.0, abs_tol=1e-9)


def test_incomplete_artifact_set_fails_closed():
    pf = _two_trade_book()
    artifacts = {"eq-a": _complete_artifacts()["eq-a"]}
    with pytest.raises(ValueError, match="incomplete"):
        _engine().build(
            pf,
            _ForbiddenPricing(),
            market=demo_market_snapshot(pf),
            artifacts=artifacts,
        )


def test_artifact_key_mismatch_fails_closed():
    pf = _two_trade_book()
    swapped = _complete_artifacts()
    artifacts = {"eq-a": swapped["eq-b"], "eq-b": swapped["eq-a"]}
    with pytest.raises(ValueError, match="incomplete"):
        _engine().build(
            pf,
            _ForbiddenPricing(),
            market=demo_market_snapshot(pf),
            artifacts=artifacts,
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
        pf,
        _ForbiddenPricing(),
        ref,
        market=demo_market_snapshot(pf),
        artifacts=artifacts,
    )
    assert node.level == "book"
    assert math.isclose(node.market_value, expected.pv, abs_tol=1e-9)
    assert math.isclose(node.delta, expected.delta, abs_tol=1e-9)
    parent_stress = {s.scenario: s.pnl for s in node.stress}
    assert parent_stress["eq_crash"] == -15.0


def test_omitted_artifacts_still_reprices():
    pf = _two_trade_book()
    pricing = _CountingPricing()
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    assert pricing.value_calls > 0
    assert root.market_value != 0.0
