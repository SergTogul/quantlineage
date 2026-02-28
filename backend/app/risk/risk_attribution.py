"""Risk-change attribution (M4.4) — why did VaR / ES change?

Separate from P&L explain (:mod:`app.risk.attribution`). This module attributes
changes in a *risk metric* (default 99% VaR) across:

- closed trades, new trades, continuing position changes;
- equity / volatility / rates / FX market moves;
- correlation / residual (unexplained after the sequential waterfall).

Methodology
-----------
Bridging waterfall on :class:`~app.risk.historical.HistoricalRiskEngine`:

1. Start at previous portfolio + previous market.
2. Remove closed trades (ids only in previous).
3. Resize / replace continuing trades to current definitions.
4. Add new trades (ids only in current).
5. Replace market field groups one at a time on the current book
   (equity spots → equity vols → rates/key_rates/curves → FX spots/vols).
6. Residual = actual current risk − last bridge step (order effects +
   correlation / joint-factor effects not isolated by mark replacement).

Sign convention (loss risk, currency units — same as HistoricalRiskEngine):
- positive ``delta_risk`` ⇒ the driver *increased* the risk metric
- negative ``delta_risk`` ⇒ the driver reduced risk

Invariants
----------
- Identical portfolio + market ⇒ total_change ≈ 0 and all drivers ≈ 0
- ``sum(items.delta_risk) + residual == total_change`` (within tolerance)
"""

from __future__ import annotations

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    Position,
    RiskChangeAttributionReport,
    RiskChangeAttributionRequest,
    RiskChangeItem,
    VaRMethodology,
)
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import MarketDataProvider
from app.risk.historical import HistoricalRiskEngine
from app.sample import DemoPortfolioMarketDataProvider

# Market field groups applied sequentially after the position bridge.
_MARKET_STEPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Equity moves", ("equity_spots",)),
    ("Volatility moves", ("equity_vols", "vol_surfaces")),
    ("Rates moves", ("rates", "key_rates", "curves", "projection_rates", "rate_spreads")),
    ("FX moves", ("fx_spots", "fx_vols")),
)


def _clone_portfolio(template: Portfolio, positions: list[Position], *, suffix: str) -> Portfolio:
    return Portfolio(
        id=f"{template.id}:{suffix}",
        name=template.name,
        positions=list(positions),
        firm=template.firm,
        desk=template.desk,
        strategy=template.strategy,
    )


def _metric_value(risk: dict, metric: str) -> float:
    return float(risk[metric])


class RiskChangeAttributionEngine:
    """Attribute ΔVaR / ΔES between two portfolio–market states."""

    def __init__(
        self,
        risk_engine: HistoricalRiskEngine | None = None,
        market_data: MarketDataProvider | None = None,
    ):
        self.risk_engine = risk_engine or HistoricalRiskEngine()
        self.market_data = market_data or DemoPortfolioMarketDataProvider()

    def _var(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot,
        methodology: VaRMethodology,
        metric: str,
    ) -> float:
        raw = self.risk_engine.calculate(
            portfolio, pricing, methodology=methodology, market=market
        )
        return _metric_value(raw, metric)

    def explain(
        self,
        req: RiskChangeAttributionRequest,
        pricing: PricingEngine,
    ) -> RiskChangeAttributionReport:
        pm = req.previous_market or self.market_data.snapshot(req.previous_portfolio)
        cm = req.current_market or self.market_data.snapshot(req.current_portfolio)
        metric = req.metric
        meth = req.methodology

        prev_by_id = {p.id: p for p in req.previous_portfolio.positions}
        curr_by_id = {p.id: p for p in req.current_portfolio.positions}
        closed_ids = set(prev_by_id) - set(curr_by_id)
        common_ids = set(prev_by_id) & set(curr_by_id)

        items: list[RiskChangeItem] = []
        running_pf = req.previous_portfolio
        running_mkt = pm
        previous_risk = self._var(running_pf, pricing, running_mkt, meth, metric)
        running_risk = previous_risk

        # 1) Closed trades
        if closed_ids:
            positions = [p for p in running_pf.positions if p.id not in closed_ids]
            nxt = _clone_portfolio(req.previous_portfolio, positions, suffix="no-closed")
        else:
            nxt = running_pf
        risk_after = self._var(nxt, pricing, running_mkt, meth, metric)
        items.append(RiskChangeItem(driver="Closed trades", delta_risk=risk_after - running_risk))
        running_pf, running_risk = nxt, risk_after

        # 2) Continuing position definition / size changes
        resized = [curr_by_id[i] for i in sorted(common_ids)]
        nxt = _clone_portfolio(req.current_portfolio, resized, suffix="resized")
        risk_after = self._var(nxt, pricing, running_mkt, meth, metric)
        items.append(
            RiskChangeItem(driver="Position changes", delta_risk=risk_after - running_risk)
        )
        running_pf, running_risk = nxt, risk_after

        # 3) New trades — bridge to the full current book
        nxt = req.current_portfolio
        risk_after = self._var(nxt, pricing, running_mkt, meth, metric)
        items.append(RiskChangeItem(driver="New trades", delta_risk=risk_after - running_risk))
        running_pf, running_risk = nxt, risk_after

        # 4) Market field groups
        for label, fields in _MARKET_STEPS:
            update = {f: getattr(cm, f) for f in fields}
            nxt_mkt = running_mkt.model_copy(update={**update, "id": f"{running_mkt.id}:{label}"})
            risk_after = self._var(running_pf, pricing, nxt_mkt, meth, metric)
            items.append(RiskChangeItem(driver=label, delta_risk=risk_after - running_risk))
            running_mkt, running_risk = nxt_mkt, risk_after

        current_risk = self._var(req.current_portfolio, pricing, cm, meth, metric)
        total_change = current_risk - previous_risk
        corr_residual = current_risk - running_risk
        items.append(RiskChangeItem(driver="Correlation / residual", delta_risk=corr_residual))
        explained = sum(i.delta_risk for i in items)

        return RiskChangeAttributionReport(
            metric=metric,
            previous_risk=previous_risk,
            current_risk=current_risk,
            total_change=total_change,
            explained_change=explained,
            residual=total_change - explained,
            items=items,
        )
