"""Helpers for Phase B tests: economics-only positions + explicit MarketSnapshot."""

from __future__ import annotations

from app.domain.models import MarketSnapshot
from app.market.snapshot import FixedMarketDataProvider as FixedMarketProvider


def equity_spot_market(
    symbol: str,
    spot: float,
    *,
    rate: float = 0.04,
    dividend_yield: float = 0.0,
    vol: float | None = None,
    market_id: str = "test",
) -> MarketSnapshot:
    equity_vols = {symbol: vol} if vol is not None else {}
    return MarketSnapshot(
        id=market_id,
        equity_spots={symbol: spot},
        equity_vols=equity_vols,
        rates={"USD": rate},
        dividend_yields={symbol: dividend_yield},
    )


def equity_spots_market(
    spots: dict[str, float],
    *,
    vols: dict[str, float] | None = None,
    rate: float = 0.04,
    dividend_yields: dict[str, float] | None = None,
    market_id: str = "test",
) -> MarketSnapshot:
    """Multi-symbol equity snapshot for ad-hoc test books."""
    divs = dividend_yields if dividend_yields is not None else {sym: 0.0 for sym in spots}
    return MarketSnapshot(
        id=market_id,
        equity_spots=dict(spots),
        equity_vols=dict(vols or {}),
        rates={"USD": rate},
        dividend_yields=divs,
    )


def fx_market(
    pair: str,
    spot: float,
    *,
    domestic_rate: float = 0.04,
    foreign_rate: float = 0.03,
    vol: float | None = None,
    market_id: str = "test",
) -> MarketSnapshot:
    fx_vols = {pair: vol} if vol is not None else {}
    return MarketSnapshot(
        id=market_id,
        fx_spots={pair: spot},
        fx_vols=fx_vols,
        rates={pair[-3:]: domestic_rate, pair[:3]: foreign_rate},
    )


def usd_rate_market(
    rate: float,
    *,
    projection: float | None = None,
    ir_vol: float | None = None,
    ir_future_quote: float | None = None,
    market_id: str = "test",
) -> MarketSnapshot:
    return MarketSnapshot(
        id=market_id,
        rates={"USD": rate},
        projection_rates={"USD": projection if projection is not None else rate},
        ir_vols={"USD": ir_vol} if ir_vol is not None else {},
        ir_future_quotes={"USD": ir_future_quote} if ir_future_quote is not None else {},
    )
