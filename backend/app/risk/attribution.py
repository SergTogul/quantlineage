from __future__ import annotations
from app.domain.models import AttributionItem, AttributionReport, AttributionRequest, MarketSnapshot, Portfolio
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import PositionMarketDataProvider


def _pv(portfolio: Portfolio, pricing: PricingEngine, market: MarketSnapshot | None):
    return sum(v.market_value for v in pricing.value_portfolio(portfolio, market))


class AttributionEngine:
    def __init__(self, market_data=None): self.market_data=market_data or PositionMarketDataProvider()
    def explain(self, req: AttributionRequest, pricing: PricingEngine) -> AttributionReport:
        pm=req.previous_market or self.market_data.snapshot(req.previous_portfolio)
        cm=req.current_market or self.market_data.snapshot(req.current_portfolio)
        base=_pv(req.previous_portfolio,pricing,pm)
        after_positions=_pv(req.current_portfolio,pricing,pm)
        items=[AttributionItem(driver="Position changes",pnl=after_positions-base)]
        running=pm; running_pv=after_positions
        fields=[("Equity moves","equity_spots"),("Volatility moves","equity_vols"),("Rates moves","rates"),("FX moves","fx_spots"),("FX volatility moves","fx_vols")]
        for label,field in fields:
            nxt=running.model_copy(update={field:getattr(cm,field)})
            pv=_pv(req.current_portfolio,pricing,nxt)
            items.append(AttributionItem(driver=label,pnl=pv-running_pv)); running=nxt; running_pv=pv
        current=_pv(req.current_portfolio,pricing,cm); explained=sum(i.pnl for i in items); total=current-base
        return AttributionReport(base_market_value=base,current_market_value=current,total_change=total,explained_change=explained,residual=total-explained,items=items)
