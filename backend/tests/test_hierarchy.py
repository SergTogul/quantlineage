"""M4.1 First-class hierarchy + M4.2 hierarchical risk aggregation.

Conventions:
- Additive: parent == sum(children) within abs 1e-9 for MV, Greeks, stress P&L
- VaR / ES / limits: computed on the node sub-portfolio (not summed)
- Position desk/strategy None → inherit Portfolio defaults
- Empty book → zero MV / zero risk metrics at every level
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
from app.risk.es import ESContributionAnalytics
from app.risk.hierarchy import (
    HierarchyEngine,
    filter_positions,
    portfolio_at,
    resolve_desk,
    resolve_strategy,
)
from app.risk.historical import HistoricalRiskEngine
from app.risk.limits import DEFAULT_LIMITS
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService

_ADDITIVE = ("market_value", "delta", "gamma", "vega", "dv01", "fx_delta")


def _assert_mv_reconciles(node: HierarchyNode, tol: float = 1e-9) -> None:
    if not node.children:
        return
    child_sum = sum(c.market_value for c in node.children)
    assert math.isclose(node.market_value, child_sum, abs_tol=tol), (
        f"{node.level}:{node.name} MV {node.market_value} != children {child_sum}"
    )
    for child in node.children:
        _assert_mv_reconciles(child, tol)


def _assert_additive_reconciles(node: HierarchyNode, tol: float = 1e-9) -> None:
    if not node.children:
        return
    for attr in _ADDITIVE:
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


def _engine(seed: int = 1, observations: int = 40) -> HierarchyEngine:
    return HierarchyEngine(HistoricalRiskEngine(seed=seed, observations=observations))


def _multi_desk_portfolio() -> Portfolio:
    return Portfolio(
        id="multi-desk",
        name="Multi Desk Book",
        firm="Acme Capital",
        desk="Default Desk",
        strategy="Default Strat",
        positions=[
            EquityPosition(
                type="equity",
                id="eq-a",
                symbol="AAA",
                quantity=100,
                price=10.0,
                book="Cash A",
                desk="Rates Desk",
                strategy="Carry",
            ),
            EquityPosition(
                type="equity",
                id="eq-b",
                symbol="BBB",
                quantity=50,
                price=20.0,
                book="Cash B",
                desk="Equity Desk",
                strategy="Momentum",
            ),
            EquityPosition(
                type="equity",
                id="eq-c",
                symbol="CCC",
                quantity=25,
                price=40.0,
                book="Cash B",
                # desk/strategy omitted → inherit portfolio defaults
            ),
        ],
    )


def test_hierarchy_levels_order():
    assert list(HierarchyLevel) == [
        HierarchyLevel.FIRM,
        HierarchyLevel.PORTFOLIO,
        HierarchyLevel.DESK,
        HierarchyLevel.STRATEGY,
        HierarchyLevel.BOOK,
        HierarchyLevel.TRADE,
    ]


def test_resolve_desk_strategy_defaults():
    pf = Portfolio(
        id="p",
        name="P",
        desk="Macro",
        strategy="Multi",
        positions=[
            EquityPosition(
                type="equity", id="x", symbol="X", quantity=1, price=1.0, desk="FX Desk"
            ),
            EquityPosition(type="equity", id="y", symbol="Y", quantity=1, price=1.0),
        ],
    )
    assert resolve_desk(pf.positions[0], pf) == "FX Desk"
    assert resolve_strategy(pf.positions[0], pf) == "Multi"
    assert resolve_desk(pf.positions[1], pf) == "Macro"
    assert resolve_strategy(pf.positions[1], pf) == "Multi"


def test_build_firm_to_trade_tree():
    pricing = BuiltinPricingEngine()
    root = _engine().build(_multi_desk_portfolio(), pricing)

    assert root.level == "firm"
    assert root.name == "Acme Capital"
    assert root.path == "Acme Capital"
    assert len(root.children) == 1

    portfolio_node = root.children[0]
    assert portfolio_node.level == "portfolio"
    assert portfolio_node.name == "Multi Desk Book"
    assert portfolio_node.path == "Acme Capital/multi-desk"

    desks = {d.name: d for d in portfolio_node.children}
    assert desks.keys() == {"Rates Desk", "Equity Desk", "Default Desk"}
    assert all(d.level == "desk" for d in desks.values())

    rates = desks["Rates Desk"]
    assert len(rates.children) == 1
    assert rates.children[0].level == "strategy"
    assert rates.children[0].name == "Carry"
    assert rates.children[0].children[0].level == "book"
    assert rates.children[0].children[0].children[0].level == "trade"
    assert rates.children[0].children[0].children[0].name == "eq-a"

    inherited = desks["Default Desk"]
    assert inherited.children[0].name == "Default Strat"
    assert inherited.children[0].children[0].children[0].name == "eq-c"


def test_market_value_reconciles_at_every_level():
    pricing = BuiltinPricingEngine()
    root = _engine().build(_multi_desk_portfolio(), pricing)
    _assert_mv_reconciles(root)
    # Spot check: three equities 1000 + 1000 + 1000
    assert math.isclose(root.market_value, 3000.0, abs_tol=1e-9)


def test_sample_portfolio_hierarchy_still_drills_to_trade():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    root = svc.hierarchy(SAMPLE_PORTFOLIO)
    assert root.level == "firm"
    portfolio = root.children[0]
    assert portfolio.level == "portfolio"
    desk = portfolio.children[0]
    strategy = desk.children[0]
    assert desk.level == "desk" and strategy.level == "strategy"
    assert any(t.level == "trade" for b in strategy.children for t in b.children)


def test_empty_portfolio_zero_risk_tree():
    pricing = BuiltinPricingEngine()
    empty = Portfolio(id="empty", name="Empty", firm="F", positions=[])
    root = _engine(observations=20).build(empty, pricing)
    assert root.level == "firm"
    assert root.market_value == 0.0
    assert root.var_99 == 0.0
    assert root.expected_shortfall_99 == 0.0
    assert root.delta == 0.0
    assert root.stress  # default scenarios still attached
    assert all(s.pnl == 0.0 for s in root.stress)
    assert root.limits
    assert all(not lim.breached for lim in root.limits)
    assert root.children[0].market_value == 0.0
    assert root.children[0].var_99 == 0.0
    assert root.children[0].children == []


def test_portfolio_at_filters_by_desk_and_book():
    pf = _multi_desk_portfolio()
    desk_ref = HierarchyRef(
        level=HierarchyLevel.DESK,
        firm="Acme Capital",
        portfolio_id="multi-desk",
        desk="Equity Desk",
    )
    desk_pf = portfolio_at(pf, desk_ref)
    assert [p.id for p in desk_pf.positions] == ["eq-b"]
    assert desk_pf.desk == "Equity Desk"
    assert desk_pf.strategy == "Momentum"

    book_ref = HierarchyRef(
        level=HierarchyLevel.BOOK,
        firm="Acme Capital",
        portfolio_id="multi-desk",
        desk="Equity Desk",
        strategy="Momentum",
        book="Cash B",
    )
    book_pf = portfolio_at(pf, book_ref)
    assert [p.id for p in book_pf.positions] == ["eq-b"]

    trade_ref = HierarchyRef(
        level=HierarchyLevel.TRADE,
        firm="Acme Capital",
        portfolio_id="multi-desk",
        desk="Rates Desk",
        strategy="Carry",
        book="Cash A",
        trade_id="eq-a",
    )
    assert [p.id for p in filter_positions(pf, trade_ref)] == ["eq-a"]


def test_portfolio_at_rejects_wrong_firm_or_portfolio():
    pf = _multi_desk_portfolio()
    with pytest.raises(ValueError, match="firm"):
        portfolio_at(
            pf,
            HierarchyRef(level=HierarchyLevel.FIRM, firm="Other"),
        )
    with pytest.raises(ValueError, match="portfolio"):
        portfolio_at(
            pf,
            HierarchyRef(
                level=HierarchyLevel.PORTFOLIO,
                firm="Acme Capital",
                portfolio_id="nope",
            ),
        )


def test_es_contributions_split_by_position_desk_strategy():
    pricing = BuiltinPricingEngine()
    pf = _multi_desk_portfolio()
    report = ESContributionAnalytics(seed=1, observations=60).report(
        pf, pricing, confidence=0.9, market=demo_market_snapshot(pf)
    )
    desks = {c.key for c in report.by_desk}
    strategies = {c.key for c in report.by_strategy}
    assert desks == {"Rates Desk", "Equity Desk", "Default Desk"}
    assert strategies == {"Carry", "Momentum", "Default Strat"}
    assert report.reconciliation_error_desk < 1e-6
    assert report.reconciliation_error_strategy < 1e-6


def test_risk_at_matches_subset_var():
    pricing = BuiltinPricingEngine()
    risk = HistoricalRiskEngine(seed=1, observations=40)
    engine = HierarchyEngine(risk)
    pf = _multi_desk_portfolio()
    ref = HierarchyRef(
        level=HierarchyLevel.DESK,
        firm="Acme Capital",
        portfolio_id="multi-desk",
        desk="Rates Desk",
    )
    market = demo_market_snapshot(pf)
    node = engine.risk_at(pf, pricing, ref, market=market)
    assert node.level == "desk"
    assert node.name == "Rates Desk"
    subset = portfolio_at(pf, ref)
    expected = risk.calculate(subset, pricing, market=market)
    assert math.isclose(node.market_value, expected["market_value"], abs_tol=1e-9)
    assert math.isclose(node.var_99, expected["var_99"], abs_tol=1e-9)
    assert math.isclose(node.expected_shortfall_99, expected["expected_shortfall_99"], abs_tol=1e-9)
    assert math.isclose(node.delta, expected["delta"], abs_tol=1e-9)


def test_greeks_var_es_stress_limits_on_nodes():
    """M4.2: full metric set present; additives reconcile; VaR/ES match subset."""
    pricing = BuiltinPricingEngine()
    risk = HistoricalRiskEngine(seed=1, observations=40)
    engine = HierarchyEngine(risk)
    pf = _multi_desk_portfolio()
    market = demo_market_snapshot(pf)
    root = engine.build(pf, pricing, market=market)

    _assert_additive_reconciles(root)

    assert root.limits
    assert {lim.metric for lim in root.limits} == {lim.metric for lim in DEFAULT_LIMITS}
    assert root.stress
    assert all(hasattr(s, "pnl") and hasattr(s, "scenario") for s in root.stress)

    desk_ref = HierarchyRef(
        level=HierarchyLevel.DESK,
        firm="Acme Capital",
        portfolio_id="multi-desk",
        desk="Equity Desk",
    )
    desk_node = next(d for d in root.children[0].children if d.name == "Equity Desk")
    expected = risk.calculate(portfolio_at(pf, desk_ref), pricing, market=market)
    assert math.isclose(desk_node.var_95, expected["var_95"], abs_tol=1e-9)
    assert math.isclose(desk_node.var_99, expected["var_99"], abs_tol=1e-9)
    assert math.isclose(desk_node.expected_shortfall_99, expected["expected_shortfall_99"], abs_tol=1e-9)
    assert math.isclose(desk_node.vega, expected["vega"], abs_tol=1e-9)
    assert math.isclose(desk_node.dv01, expected["dv01"], abs_tol=1e-9)
    assert math.isclose(desk_node.fx_delta, expected["fx_delta"], abs_tol=1e-9)


def test_risk_at_includes_stress_and_limits():
    pricing = BuiltinPricingEngine()
    engine = _engine()
    pf = _multi_desk_portfolio()
    ref = HierarchyRef(
        level=HierarchyLevel.STRATEGY,
        firm="Acme Capital",
        portfolio_id="multi-desk",
        desk="Rates Desk",
        strategy="Carry",
    )
    node = engine.risk_at(pf, pricing, ref)
    assert node.level == "strategy"
    assert node.stress
    assert node.limits
    assert len(node.limits) == len(DEFAULT_LIMITS)
