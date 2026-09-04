"""R0.7.1 / RF-008 slice: stable HierarchyNode identifiers.

IDs align with ``portfolio_at`` sub-portfolio ids so later limits/drilldown
can address the same node. ``path`` remains the slash-separated display
breadcrumb (firm / portfolio / desk / strategy / book / trade labels).

This slice does not change VaR/ES numbers or stop per-node recomputation.
"""

from __future__ import annotations

import math

from app.domain.models import (
    EquityPosition,
    HierarchyLevel,
    HierarchyNode,
    HierarchyRef,
    Portfolio,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.hierarchy import HierarchyEngine
from app.risk.hierarchy_placement import hierarchy_node_id, portfolio_at
from app.risk.historical import HistoricalRiskEngine
from app.sample import demo_market_snapshot

_ADDITIVE = ("market_value", "delta", "gamma", "vega", "dv01", "fx_delta")


def _engine(seed: int = 1, observations: int = 40) -> HierarchyEngine:
    return HierarchyEngine(HistoricalRiskEngine(seed=seed, observations=observations))


def _multi_book_portfolio() -> Portfolio:
    """Two desks, two books under one desk, inherited placement on one trade."""
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
            ),
            EquityPosition(
                type="equity",
                id="eq-d",
                symbol="DDD",
                quantity=10,
                price=50.0,
                book="Cash C",
                desk="Equity Desk",
                strategy="Momentum",
            ),
        ],
    )


def _walk(node: HierarchyNode):
    yield node
    for child in node.children:
        yield from _walk(child)


def _nodes_by_level(root: HierarchyNode) -> dict[str, list[HierarchyNode]]:
    grouped: dict[str, list[HierarchyNode]] = {}
    for node in _walk(root):
        grouped.setdefault(node.level, []).append(node)
    return grouped


def test_hierarchy_node_id_matches_portfolio_at_scheme():
    """Shared helper matches the ids ``portfolio_at`` already invents."""
    pf = _multi_book_portfolio()
    cases = [
        (
            HierarchyRef(level=HierarchyLevel.FIRM, firm="Acme Capital"),
            "firm:Acme Capital",
        ),
        (
            HierarchyRef(
                level=HierarchyLevel.PORTFOLIO,
                firm="Acme Capital",
                portfolio_id="multi-desk",
            ),
            "portfolio:multi-desk",
        ),
        (
            HierarchyRef(
                level=HierarchyLevel.DESK,
                firm="Acme Capital",
                portfolio_id="multi-desk",
                desk="Rates Desk",
            ),
            "desk:Rates Desk",
        ),
        (
            HierarchyRef(
                level=HierarchyLevel.STRATEGY,
                firm="Acme Capital",
                portfolio_id="multi-desk",
                desk="Rates Desk",
                strategy="Carry",
            ),
            "strategy:Rates Desk/Carry",
        ),
        (
            HierarchyRef(
                level=HierarchyLevel.BOOK,
                firm="Acme Capital",
                portfolio_id="multi-desk",
                desk="Equity Desk",
                strategy="Momentum",
                book="Cash C",
            ),
            "book:Equity Desk/Momentum/Cash C",
        ),
        (
            HierarchyRef(
                level=HierarchyLevel.TRADE,
                firm="Acme Capital",
                portfolio_id="multi-desk",
                desk="Rates Desk",
                strategy="Carry",
                book="Cash A",
                trade_id="eq-a",
            ),
            "trade:Rates Desk/Carry/Cash A/eq-a",
        ),
    ]
    for ref, expected in cases:
        assert hierarchy_node_id(
            ref.level,
            firm=pf.firm,
            portfolio_id=pf.id,
            desk=ref.desk,
            strategy=ref.strategy,
            book=ref.book,
            trade_id=ref.trade_id,
        ) == expected
        assert portfolio_at(pf, ref).id == expected


def test_all_six_levels_have_nonempty_ids():
    pricing = BuiltinPricingEngine()
    pf = _multi_book_portfolio()
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    by_level = _nodes_by_level(root)
    assert set(by_level) == {"firm", "portfolio", "desk", "strategy", "book", "trade"}
    for level, nodes in by_level.items():
        assert nodes, f"missing nodes at {level}"
        for node in nodes:
            assert node.id, f"{level}:{node.name} has empty id"
            assert node.path, f"{level}:{node.name} has empty path"


def test_ids_unique_in_multi_desk_multi_book_tree():
    pricing = BuiltinPricingEngine()
    pf = _multi_book_portfolio()
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    ids = [node.id for node in _walk(root)]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_rebuild_identical_id_and_path():
    pricing = BuiltinPricingEngine()
    pf = _multi_book_portfolio()
    market = demo_market_snapshot(pf)
    engine = _engine()
    first = [(n.id, n.path, n.level, n.name) for n in _walk(engine.build(pf, pricing, market=market))]
    second = [(n.id, n.path, n.level, n.name) for n in _walk(engine.build(pf, pricing, market=market))]
    assert first == second


def test_trades_under_different_books_do_not_collide():
    pricing = BuiltinPricingEngine()
    pf = _multi_book_portfolio()
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    trades = {n.name: n for n in _walk(root) if n.level == "trade"}
    assert set(trades) == {"eq-a", "eq-b", "eq-c", "eq-d"}
    books = {n.name: n for n in _walk(root) if n.level == "book"}
    assert "Cash B" in books and "Cash C" in books
    assert trades["eq-b"].id != trades["eq-d"].id
    assert trades["eq-b"].path != trades["eq-d"].path
    assert trades["eq-b"].id == "trade:Equity Desk/Momentum/Cash B/eq-b"
    assert trades["eq-d"].id == "trade:Equity Desk/Momentum/Cash C/eq-d"
    assert books["Cash B"].id != books["Cash C"].id


def test_tree_ids_align_with_portfolio_at_and_risk_at():
    pricing = BuiltinPricingEngine()
    pf = _multi_book_portfolio()
    market = demo_market_snapshot(pf)
    engine = _engine()
    root = engine.build(pf, pricing, market=market)
    by_level = _nodes_by_level(root)

    firm = by_level["firm"][0]
    assert firm.id == "firm:Acme Capital"
    assert firm.path == "Acme Capital"
    assert firm.id != firm.path

    portfolio = by_level["portfolio"][0]
    assert portfolio.id == "portfolio:multi-desk"
    assert portfolio.path == "Acme Capital/multi-desk"

    rates = next(n for n in by_level["desk"] if n.name == "Rates Desk")
    assert rates.id == "desk:Rates Desk"
    assert rates.path == "Acme Capital/multi-desk/Rates Desk"

    carry = next(n for n in by_level["strategy"] if n.name == "Carry")
    assert carry.id == "strategy:Rates Desk/Carry"

    cash_c = next(n for n in by_level["book"] if n.name == "Cash C")
    assert cash_c.id == "book:Equity Desk/Momentum/Cash C"

    refs = [
        HierarchyRef(level=HierarchyLevel.FIRM, firm="Acme Capital"),
        HierarchyRef(
            level=HierarchyLevel.PORTFOLIO,
            firm="Acme Capital",
            portfolio_id="multi-desk",
        ),
        HierarchyRef(
            level=HierarchyLevel.DESK,
            firm="Acme Capital",
            portfolio_id="multi-desk",
            desk="Rates Desk",
        ),
        HierarchyRef(
            level=HierarchyLevel.STRATEGY,
            firm="Acme Capital",
            portfolio_id="multi-desk",
            desk="Rates Desk",
            strategy="Carry",
        ),
        HierarchyRef(
            level=HierarchyLevel.BOOK,
            firm="Acme Capital",
            portfolio_id="multi-desk",
            desk="Equity Desk",
            strategy="Momentum",
            book="Cash C",
        ),
        HierarchyRef(
            level=HierarchyLevel.TRADE,
            firm="Acme Capital",
            portfolio_id="multi-desk",
            desk="Rates Desk",
            strategy="Carry",
            book="Cash A",
            trade_id="eq-a",
        ),
    ]
    tree_by_id = {n.id: n for n in _walk(root)}
    for ref in refs:
        expected_id = portfolio_at(pf, ref).id
        at_node = engine.risk_at(pf, pricing, ref, market=market)
        assert at_node.id == expected_id
        assert at_node.id in tree_by_id
        assert tree_by_id[expected_id].path == at_node.path
        assert tree_by_id[expected_id].level == at_node.level


def test_node_ids_do_not_change_var_es_or_additive_reconciliation():
    pricing = BuiltinPricingEngine()
    risk = HistoricalRiskEngine(seed=1, observations=40)
    pf = _multi_book_portfolio()
    market = demo_market_snapshot(pf)
    root = HierarchyEngine(risk).build(pf, pricing, market=market)

    def _reconcile(node: HierarchyNode) -> None:
        if not node.children:
            return
        for attr in _ADDITIVE:
            parent = getattr(node, attr)
            child_sum = sum(getattr(c, attr) for c in node.children)
            assert math.isclose(parent, child_sum, abs_tol=1e-9)
        parent_stress = {s.scenario: s.pnl for s in node.stress}
        for scenario, parent_pnl in parent_stress.items():
            child_sum = sum(
                next(s.pnl for s in c.stress if s.scenario == scenario) for c in node.children
            )
            assert math.isclose(parent_pnl, child_sum, abs_tol=1e-9)
        for child in node.children:
            _reconcile(child)

    _reconcile(root)
    expected = risk.calculate(pf, pricing, market=market)
    assert math.isclose(root.var_95, expected["var_95"], abs_tol=1e-9)
    assert math.isclose(root.var_99, expected["var_99"], abs_tol=1e-9)
    assert math.isclose(root.expected_shortfall_99, expected["expected_shortfall_99"], abs_tol=1e-9)
    assert math.isclose(root.market_value, 3500.0, abs_tol=1e-9)


def _assert_unique_nonempty_ids(root: HierarchyNode) -> list[str]:
    ids = [node.id for node in _walk(root)]
    assert all(ids), f"empty id in {ids}"
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    return ids


def test_portfolio_id_equal_to_trade_id_does_not_collide():
    pricing = BuiltinPricingEngine()
    pf = Portfolio(
        id="eq-a",
        name="Named Like A Trade",
        firm="Acme",
        positions=[
            EquityPosition(type="equity", id="eq-a", symbol="AAA", quantity=1, price=10.0),
            EquityPosition(type="equity", id="eq-b", symbol="BBB", quantity=1, price=10.0),
        ],
    )
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    ids = _assert_unique_nonempty_ids(root)
    assert "portfolio:eq-a" in ids
    assert any(i.endswith("/eq-a") and i.startswith("trade:") for i in ids)


def test_empty_and_literal_trade_ids_under_different_books_do_not_collide():
    pricing = BuiltinPricingEngine()
    pf = Portfolio(
        id="books",
        name="Empty vs literal trade",
        firm="Acme",
        desk="D",
        strategy="S",
        positions=[
            EquityPosition(
                type="equity", id="", symbol="AAA", quantity=1, price=10.0, book="Cash A"
            ),
            EquityPosition(
                type="equity", id="trade", symbol="BBB", quantity=1, price=10.0, book="Cash B"
            ),
        ],
    )
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    ids = _assert_unique_nonempty_ids(root)
    assert "trade:D/S/Cash A/" in ids
    assert "trade:D/S/Cash B/trade" in ids


def test_trade_id_matching_desk_prefix_does_not_collide():
    pricing = BuiltinPricingEngine()
    pf = Portfolio(
        id="desk-collision",
        name="Trade named like a desk",
        firm="Acme",
        desk="Rates Desk",
        strategy="Carry",
        positions=[
            EquityPosition(
                type="equity",
                id="desk:Rates Desk",
                symbol="AAA",
                quantity=1,
                price=10.0,
                book="Cash A",
            ),
        ],
    )
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    ids = _assert_unique_nonempty_ids(root)
    assert "desk:Rates Desk" in ids
    assert "trade:Rates Desk/Carry/Cash A/desk:Rates Desk" in ids


def test_empty_and_literal_book_labels_do_not_collide():
    pricing = BuiltinPricingEngine()
    pf = Portfolio(
        id="book-labels",
        name="Empty vs literal book",
        firm="Acme",
        desk="D",
        strategy="S",
        positions=[
            EquityPosition(type="equity", id="eq-empty-book", symbol="AAA", quantity=1, price=10.0, book=""),
            EquityPosition(type="equity", id="eq-book", symbol="BBB", quantity=1, price=10.0, book="book"),
        ],
    )
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    ids = _assert_unique_nonempty_ids(root)
    assert "book:D/S/" in ids
    assert "book:D/S/book" in ids


def test_empty_portfolio_id_is_namespaced_and_nonempty():
    pricing = BuiltinPricingEngine()
    pf = Portfolio(
        id="",
        name="Empty book id",
        firm="Acme",
        positions=[
            EquityPosition(type="equity", id="eq-z", symbol="AAA", quantity=1, price=10.0),
        ],
    )
    root = _engine().build(pf, pricing, market=demo_market_snapshot(pf))
    ids = _assert_unique_nonempty_ids(root)
    assert "portfolio:" in ids


def test_slash_in_desk_and_strategy_labels_do_not_collide():
    assert hierarchy_node_id(
        "strategy",
        firm="Acme",
        portfolio_id="p",
        desk="Rates/Extra",
        strategy="Carry",
    ) != hierarchy_node_id(
        "strategy",
        firm="Acme",
        portfolio_id="p",
        desk="Rates",
        strategy="Extra/Carry",
    )
