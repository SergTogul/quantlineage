"""P&L Explain v2 between two portfolio / market states (M4.3).

Decomposes actual P&L into Greek Taylor terms on the previous book plus trade-flow
(new / closed trades, including size changes). Pricing goes only through
``PricingEngine`` — no instrument formulas in this module.

Identity
--------
``actual = PV(curr, cm) − PV(prev, pm)``
``actual = market_effect + position_effect``
where ``market_effect = PV(prev, cm) − PV(prev, pm)`` and
``position_effect = PV(curr, cm) − PV(prev, cm)``.

Market effect is approximated with start-of-period Greeks:

- **delta** — cash delta × relative equity spot return
- **gamma** — ½ × dollar gamma × return²
- **vega** — vega (per 1 vol point) × absolute vol change in points
- **rates** — DV01 × parallel rate change in bp
- **FX** — FX cash delta × relative FX spot return
- **theta** — reprice with ``maturity_years`` aged by ``dt_years`` at previous marks

Position effect is attributed exactly to **new trades** / **closed trades**.

``explained + residual ≈ actual`` with ``residual`` carrying the Taylor remainder
(and any unattributed cross effects).

Units: currency P&L; positive = gain. Sign conventions match ``Valuation`` Greeks
(see ``sensitivities`` / Builtin adapter).
"""

from __future__ import annotations

from app.domain.models import (
    AttributionItem,
    AttributionReport,
    AttributionRequest,
    BondPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    Portfolio,
    Position,
    SwapPosition,
    Valuation,
)
from app.interfaces.pricing import PricingEngine
from app.sample import DemoAggregateMarketDataProvider

# Stable driver labels (API / UI). Residual stays on AttributionReport.residual.
DRIVER_DELTA = "Delta"
DRIVER_GAMMA = "Gamma"
DRIVER_VEGA = "Vega"
DRIVER_RATES = "Rates"
DRIVER_FX = "FX"
DRIVER_THETA = "Theta"
DRIVER_NEW = "New trades"
DRIVER_CLOSED = "Closed trades"

_DRIVER_ORDER = (
    DRIVER_DELTA,
    DRIVER_GAMMA,
    DRIVER_VEGA,
    DRIVER_RATES,
    DRIVER_FX,
    DRIVER_THETA,
    DRIVER_NEW,
    DRIVER_CLOSED,
)

_MIN_MATURITY = 1e-6


def _pv(portfolio: Portfolio, pricing: PricingEngine, market: MarketSnapshot | None) -> float:
    return sum(v.market_value for v in pricing.value_portfolio(portfolio, market))


def _spot_return(s0: float, s1: float) -> float:
    if s0 == 0.0:
        return 0.0
    return (s1 - s0) / s0


def _equity_symbol(position: Position) -> str | None:
    if isinstance(position, (EquityPosition, EquityFuturePosition, EuropeanOptionPosition)):
        return position.symbol
    return None


def _fx_pair(position: Position) -> str | None:
    if isinstance(position, (FXForwardPosition, FXOptionPosition)):
        return position.pair
    return None


def _rate_currency(position: Position) -> str | None:
    if isinstance(position, (BondPosition, SwapPosition, InterestRateFuturePosition)):
        return position.currency
    if isinstance(position, (EuropeanOptionPosition, EquityFuturePosition)):
        return "USD"
    if isinstance(position, (FXForwardPosition, FXOptionPosition)):
        return position.pair[-3:]
    return None


def _theta_for_position(
    position: Position,
    pricing: PricingEngine,
    market: MarketSnapshot,
    base_mv: float,
    dt_years: float,
) -> float:
    """Time decay via aged maturity reprice at fixed previous marks (no analytic θ)."""
    if dt_years <= 0.0 or not hasattr(position, "maturity_years"):
        return 0.0
    t0 = float(position.maturity_years)
    t1 = max(_MIN_MATURITY, t0 - dt_years)
    if abs(t1 - t0) < 1e-15:
        return 0.0
    aged = position.model_copy(update={"maturity_years": t1})
    return pricing.value(aged, market).market_value - base_mv


def _greek_buckets_for_position(
    position: Position,
    val: Valuation,
    previous: MarketSnapshot,
    current: MarketSnapshot,
    pricing: PricingEngine,
    dt_years: float,
) -> dict[str, float]:
    out = {
        DRIVER_DELTA: 0.0,
        DRIVER_GAMMA: 0.0,
        DRIVER_VEGA: 0.0,
        DRIVER_RATES: 0.0,
        DRIVER_FX: 0.0,
        DRIVER_THETA: 0.0,
    }

    sym = _equity_symbol(position)
    if sym is not None:
        s0 = float(previous.equity_spots.get(sym, getattr(position, "spot", getattr(position, "price", 0.0))))
        s1 = float(current.equity_spots.get(sym, s0))
        ret = _spot_return(s0, s1)
        out[DRIVER_DELTA] += val.delta * ret
        out[DRIVER_GAMMA] += 0.5 * val.gamma * ret * ret
        if isinstance(position, EuropeanOptionPosition):
            v0 = float(previous.equity_vols.get(sym, position.volatility))
            v1 = float(current.equity_vols.get(sym, v0))
            # Valuation.vega is P&L per 1 absolute vol point (0.01).
            out[DRIVER_VEGA] += val.vega * (v1 - v0) * 100.0

    pair = _fx_pair(position)
    if pair is not None:
        f0 = float(previous.fx_spots.get(pair, getattr(position, "spot", 0.0)))
        f1 = float(current.fx_spots.get(pair, f0))
        fx_ret = _spot_return(f0, f1)
        out[DRIVER_FX] += val.fx_delta * fx_ret
        out[DRIVER_GAMMA] += 0.5 * val.gamma * fx_ret * fx_ret
        if isinstance(position, FXOptionPosition):
            v0 = float(previous.fx_vols.get(pair, position.volatility))
            v1 = float(current.fx_vols.get(pair, v0))
            out[DRIVER_VEGA] += val.vega * (v1 - v0) * 100.0

    ccy = _rate_currency(position)
    if ccy is not None and val.dv01:
        r0 = float(previous.rates.get(ccy, 0.0))
        r1 = float(current.rates.get(ccy, r0))
        out[DRIVER_RATES] += val.dv01 * (r1 - r0) * 10000.0

    out[DRIVER_THETA] += _theta_for_position(position, pricing, previous, val.market_value, dt_years)
    return out


def _trade_flow_pnl(
    previous: Portfolio,
    current: Portfolio,
    pricing: PricingEngine,
    market: MarketSnapshot,
) -> tuple[float, float]:
    """Exact position_effect split into new / closed at ``market`` marks."""
    prev_map = {p.id: p for p in previous.positions}
    curr_map = {p.id: p for p in current.positions}
    new_pnl = 0.0
    closed_pnl = 0.0

    for pid, pos in curr_map.items():
        if pid not in prev_map:
            new_pnl += pricing.value(pos, market).market_value

    for pid, pos in prev_map.items():
        if pid not in curr_map:
            closed_pnl -= pricing.value(pos, market).market_value

    for pid in prev_map.keys() & curr_map.keys():
        d = (
            pricing.value(curr_map[pid], market).market_value
            - pricing.value(prev_map[pid], market).market_value
        )
        if d > 0.0:
            new_pnl += d
        elif d < 0.0:
            closed_pnl += d

    return new_pnl, closed_pnl


class AttributionEngine:
    def __init__(self, market_data=None):
        self.market_data = market_data or DemoAggregateMarketDataProvider()

    def explain(self, req: AttributionRequest, pricing: PricingEngine) -> AttributionReport:
        pm = req.previous_market or self.market_data.snapshot(req.previous_portfolio)
        cm = req.current_market or self.market_data.snapshot(req.current_portfolio)
        dt_years = float(req.dt_years or 0.0)

        base = _pv(req.previous_portfolio, pricing, pm)
        current = _pv(req.current_portfolio, pricing, cm)
        total = current - base

        buckets = {name: 0.0 for name in _DRIVER_ORDER}
        prev_vals = pricing.value_portfolio(req.previous_portfolio, pm)
        val_by_id = {v.position_id: v for v in prev_vals}
        for pos in req.previous_portfolio.positions:
            val = val_by_id[pos.id]
            part = _greek_buckets_for_position(pos, val, pm, cm, pricing, dt_years)
            for k, v in part.items():
                buckets[k] += v

        new_pnl, closed_pnl = _trade_flow_pnl(
            req.previous_portfolio, req.current_portfolio, pricing, cm
        )
        buckets[DRIVER_NEW] = new_pnl
        buckets[DRIVER_CLOSED] = closed_pnl

        items = [AttributionItem(driver=name, pnl=buckets[name]) for name in _DRIVER_ORDER]
        explained = sum(i.pnl for i in items)
        residual = total - explained
        return AttributionReport(
            base_market_value=base,
            current_market_value=current,
            total_change=total,
            explained_change=explained,
            residual=residual,
            items=items,
        )
