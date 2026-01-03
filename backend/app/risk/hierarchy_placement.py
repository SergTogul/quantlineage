"""Hierarchy placement helpers (desk/strategy/book/trade membership).

Pure portfolio slicing — no stress, VaR, or limit engines. Extracted so
``scenario_attribution`` / ``es`` can resolve desk/strategy without importing
``HierarchyEngine`` (which depends on ``StressEngine``).
"""

from __future__ import annotations

from app.domain.models import HierarchyLevel, HierarchyRef, Portfolio, Position


def resolve_desk(position: Position, portfolio: Portfolio) -> str:
    desk = getattr(position, "desk", None)
    return desk if desk is not None else portfolio.desk


def resolve_strategy(position: Position, portfolio: Portfolio) -> str:
    strategy = getattr(position, "strategy", None)
    return strategy if strategy is not None else portfolio.strategy


def _matches(position: Position, portfolio: Portfolio, ref: HierarchyRef) -> bool:
    level = ref.level
    if level is HierarchyLevel.FIRM:
        return True
    if level is HierarchyLevel.PORTFOLIO:
        return True
    if resolve_desk(position, portfolio) != ref.desk:
        return False
    if level is HierarchyLevel.DESK:
        return True
    if resolve_strategy(position, portfolio) != ref.strategy:
        return False
    if level is HierarchyLevel.STRATEGY:
        return True
    if position.book != ref.book:
        return False
    if level is HierarchyLevel.BOOK:
        return True
    return position.id == ref.trade_id


def filter_positions(portfolio: Portfolio, ref: HierarchyRef) -> list[Position]:
    """Return positions belonging to ``ref`` (validated against firm/portfolio)."""
    if ref.firm is not None and ref.firm != portfolio.firm:
        raise ValueError(f"firm mismatch: expected {portfolio.firm!r}, got {ref.firm!r}")
    if ref.portfolio_id is not None and ref.portfolio_id != portfolio.id:
        raise ValueError(
            f"portfolio mismatch: expected {portfolio.id!r}, got {ref.portfolio_id!r}"
        )
    if ref.level is HierarchyLevel.FIRM:
        return list(portfolio.positions)
    if ref.level is HierarchyLevel.PORTFOLIO:
        return list(portfolio.positions)
    if ref.desk is None:
        raise ValueError("desk is required for desk/strategy/book/trade refs")
    if ref.level in (HierarchyLevel.STRATEGY, HierarchyLevel.BOOK, HierarchyLevel.TRADE):
        if ref.strategy is None:
            raise ValueError("strategy is required for strategy/book/trade refs")
    if ref.level in (HierarchyLevel.BOOK, HierarchyLevel.TRADE):
        if ref.book is None:
            raise ValueError("book is required for book/trade refs")
    if ref.level is HierarchyLevel.TRADE and ref.trade_id is None:
        raise ValueError("trade_id is required for trade refs")
    return [p for p in portfolio.positions if _matches(p, portfolio, ref)]


def portfolio_at(portfolio: Portfolio, ref: HierarchyRef) -> Portfolio:
    """Build a sub-portfolio for risk calculation at a hierarchy node."""
    positions = filter_positions(portfolio, ref)
    if ref.desk is not None:
        desk = ref.desk
    else:
        desks = {resolve_desk(p, portfolio) for p in positions}
        desk = next(iter(desks)) if len(desks) == 1 else portfolio.desk
    if ref.strategy is not None:
        strategy = ref.strategy
    else:
        strategies = {resolve_strategy(p, portfolio) for p in positions}
        strategy = next(iter(strategies)) if len(strategies) == 1 else portfolio.strategy
    if ref.level is HierarchyLevel.FIRM:
        node_id, name = f"firm:{portfolio.firm}", portfolio.firm
    elif ref.level is HierarchyLevel.PORTFOLIO:
        node_id, name = portfolio.id, portfolio.name
    elif ref.level is HierarchyLevel.DESK:
        node_id, name = f"desk:{desk}", desk
    elif ref.level is HierarchyLevel.STRATEGY:
        node_id, name = f"strategy:{desk}/{strategy}", strategy
    elif ref.level is HierarchyLevel.BOOK:
        node_id, name = f"book:{desk}/{strategy}/{ref.book}", ref.book or "book"
    else:
        trade_id = ref.trade_id or (positions[0].id if positions else "trade")
        node_id, name = trade_id, trade_id
    return Portfolio(
        id=node_id,
        name=name,
        positions=positions,
        firm=portfolio.firm,
        desk=desk,
        strategy=strategy,
    )


__all__ = [
    "filter_positions",
    "portfolio_at",
    "resolve_desk",
    "resolve_strategy",
]
