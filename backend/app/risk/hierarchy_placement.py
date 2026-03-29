"""Hierarchy placement helpers (desk/strategy/book/trade membership).

Pure portfolio slicing — no stress, VaR, or limit engines. Extracted so
``scenario_attribution`` / ``es`` can resolve desk/strategy without importing
``HierarchyEngine`` (which depends on ``StressEngine``).
"""

from __future__ import annotations

from app.domain.models import HierarchyLevel, HierarchyRef, Portfolio, Position


def _seg(value: str | None) -> str:
    """Encode one id segment so ``/`` in a label cannot join adjacent parts."""
    return (value or "").replace("%", "%25").replace("/", "%2F")


def hierarchy_node_id(
    level: HierarchyLevel | str,
    *,
    firm: str,
    portfolio_id: str,
    desk: str | None = None,
    strategy: str | None = None,
    book: str | None = None,
    trade_id: str | None = None,
) -> str:
    """Stable Firm → … → Trade id; same scheme as ``portfolio_at`` Portfolio.id.

    Every level is prefixed. Empty labels stay empty segments (not the
    literals ``trade`` / ``book``). ``/`` inside a label is ``%2F``.
    """
    resolved = HierarchyLevel(level) if not isinstance(level, HierarchyLevel) else level
    if resolved is HierarchyLevel.FIRM:
        return f"firm:{_seg(firm)}"
    if resolved is HierarchyLevel.PORTFOLIO:
        return f"portfolio:{_seg(portfolio_id)}"
    if resolved is HierarchyLevel.DESK:
        return f"desk:{_seg(desk)}"
    if resolved is HierarchyLevel.STRATEGY:
        return f"strategy:{_seg(desk)}/{_seg(strategy)}"
    if resolved is HierarchyLevel.BOOK:
        return f"book:{_seg(desk)}/{_seg(strategy)}/{_seg(book)}"
    return f"trade:{_seg(desk)}/{_seg(strategy)}/{_seg(book)}/{_seg(trade_id)}"


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
        name = portfolio.firm
        trade_id = None
    elif ref.level is HierarchyLevel.PORTFOLIO:
        name = portfolio.name
        trade_id = None
    elif ref.level is HierarchyLevel.DESK:
        name = desk
        trade_id = None
    elif ref.level is HierarchyLevel.STRATEGY:
        name = strategy
        trade_id = None
    elif ref.level is HierarchyLevel.BOOK:
        name = ref.book if ref.book else "book"
        trade_id = None
    else:
        trade_id = ref.trade_id if ref.trade_id is not None else (
            positions[0].id if positions else ""
        )
        name = trade_id if trade_id else "trade"
    node_id = hierarchy_node_id(
        ref.level,
        firm=portfolio.firm,
        portfolio_id=portfolio.id,
        desk=desk,
        strategy=strategy,
        book=ref.book,
        trade_id=trade_id,
    )
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
    "hierarchy_node_id",
    "portfolio_at",
    "resolve_desk",
    "resolve_strategy",
]
