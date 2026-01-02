from __future__ import annotations
from collections import defaultdict
from app.domain.models import HierarchyNode, Portfolio
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine


class HierarchyEngine:
    def __init__(self, risk: RiskEngine): self.risk=risk
    def _node(self,name,level,portfolio,pricing,children=None):
        r=self.risk.calculate(portfolio,pricing)
        return HierarchyNode(name=name,level=level,market_value=r["market_value"],var_99=r["var_99"],children=children or [])
    def build(self, portfolio: Portfolio, pricing: PricingEngine) -> HierarchyNode:
        books=defaultdict(list)
        for p in portfolio.positions: books[p.book].append(p)
        book_nodes=[]
        for book,positions in sorted(books.items()):
            trade_nodes=[]
            for p in positions:
                sub=Portfolio(id=p.id,name=p.id,positions=[p],desk=portfolio.desk,strategy=portfolio.strategy)
                trade_nodes.append(self._node(p.id,"trade",sub,pricing))
            sub=Portfolio(id=f"book:{book}",name=book,positions=positions,desk=portfolio.desk,strategy=portfolio.strategy)
            book_nodes.append(self._node(book,"book",sub,pricing,trade_nodes))
        strategy=self._node(portfolio.strategy,"strategy",portfolio,pricing,book_nodes)
        desk=self._node(portfolio.desk,"desk",portfolio,pricing,[strategy])
        return self._node(portfolio.name,"portfolio",portfolio,pricing,[desk])
