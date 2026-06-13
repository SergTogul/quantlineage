"""Shared snapshot-mark overlay for Builtin and QuantLib working views.

Family selection is a frozen ``terms.type`` map after ``get_capability``.
Unknown families fail closed. This is not a plugin framework and does not
import pricing engines.
"""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

from app.domain.instrument_terms import InstrumentTerms
from app.domain.models import MarketSnapshot, Position
from app.market.demo_snapshot import MissingMarketDataError
from app.pricing.curve_rates import required_continuous_zero, required_ir_future_quote
from app.pricing.instrument_capabilities import get_capability
from app.pricing.surface_vol import (
    required_equity_option_vol,
    required_fx_option_vol,
    required_ir_option_vol,
)


def required_equity_spot(market: MarketSnapshot, symbol: str) -> float:
    try:
        return market.equity_spots[symbol]
    except KeyError:
        raise MissingMarketDataError(f"equity_spots[{symbol}]") from None


def required_settlement_rate(market: MarketSnapshot, currency: str) -> float:
    try:
        return market.rates[currency]
    except KeyError:
        raise MissingMarketDataError(f"rates[{currency}]") from None


def required_dividend_yield(market: MarketSnapshot, symbol: str) -> float:
    try:
        return market.dividend_yields[symbol]
    except KeyError:
        raise MissingMarketDataError(f"dividend_yields[{symbol}]") from None


def required_fx_spot(market: MarketSnapshot, pair: str) -> float:
    try:
        return market.fx_spots[pair]
    except KeyError:
        raise MissingMarketDataError(f"fx_spots[{pair}]") from None


def _equity_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    return {"price": required_equity_spot(market, terms.symbol)}


def _equity_future_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    return {
        "spot": required_equity_spot(market, terms.symbol),
        "risk_free_rate": required_settlement_rate(market, terms.currency),
        "dividend_yield": required_dividend_yield(market, terms.symbol),
    }


def _european_option_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    spot = required_equity_spot(market, terms.symbol)
    return {
        "spot": spot,
        "volatility": required_equity_option_vol(
            market,
            name=terms.symbol,
            maturity_years=terms.maturity_years,
            strike=terms.strike,
            spot=spot,
        ),
        "risk_free_rate": required_settlement_rate(market, terms.currency),
        "dividend_yield": required_dividend_yield(market, terms.symbol),
    }


def _bond_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    return {
        "yield_rate": required_continuous_zero(
            market,
            terms.currency,
            terms.maturity_years,
        )
    }


def _swap_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    return {
        "market_swap_rate": required_continuous_zero(
            market,
            terms.currency,
            terms.maturity_years,
        )
    }


def _ir_future_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    return {
        "forward_rate": required_continuous_zero(
            market,
            terms.currency,
            terms.maturity_years,
            prefer_projection=True,
        ),
        "quoted_rate": required_ir_future_quote(market, terms.currency),
    }


def _cap_floor_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    forward = required_continuous_zero(
        market,
        terms.currency,
        terms.maturity_years,
        prefer_projection=True,
    )
    return {
        "forward_rate": forward,
        "discount_rate": required_continuous_zero(
            market,
            terms.currency,
            terms.maturity_years,
        ),
        "volatility": required_ir_option_vol(
            market,
            name=terms.currency,
            maturity_years=terms.maturity_years,
            strike=terms.strike,
            forward=forward,
        ),
    }


def _swaption_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    forward = required_continuous_zero(
        market,
        terms.currency,
        terms.option_maturity_years,
        prefer_projection=True,
    )
    return {
        "forward_swap_rate": forward,
        "discount_rate": required_continuous_zero(
            market,
            terms.currency,
            terms.option_maturity_years + terms.swap_tenor_years,
        ),
        "volatility": required_ir_option_vol(
            market,
            name=terms.currency,
            maturity_years=terms.option_maturity_years,
            strike=terms.strike,
            forward=forward,
        ),
    }


def _fx_forward_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    return {
        "spot": required_fx_spot(market, terms.pair),
        "domestic_rate": required_settlement_rate(market, terms.pair[-3:]),
        "foreign_rate": required_settlement_rate(market, terms.pair[:3]),
    }


def _fx_option_marks(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    spot = required_fx_spot(market, terms.pair)
    return {
        "spot": spot,
        "volatility": required_fx_option_vol(
            market,
            name=terms.pair,
            maturity_years=terms.maturity_years,
            strike=terms.strike,
            spot=spot,
        ),
        "domestic_rate": required_settlement_rate(market, terms.pair[-3:]),
        "foreign_rate": required_settlement_rate(market, terms.pair[:3]),
    }


_OVERLAY_HANDLERS = MappingProxyType(
    {
        "equity": _equity_marks,
        "equity_future": _equity_future_marks,
        "european_option": _european_option_marks,
        "bond": _bond_marks,
        "swap": _swap_marks,
        "fx_forward": _fx_forward_marks,
        "fx_option": _fx_option_marks,
        "ir_future": _ir_future_marks,
        "cap_floor": _cap_floor_marks,
        "swaption": _swaption_marks,
    }
)


def snapshot_marks_from_terms(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    """Resolve live marks from the explicit snapshot using terms keys only."""
    family = getattr(terms, "type", None)
    get_capability(family)
    try:
        handler = _OVERLAY_HANDLERS[family]
    except KeyError:
        raise TypeError(f"unknown instrument family: {family!r}") from None
    return handler(terms, market)


def pricing_view(
    position: Position, terms: InstrumentTerms, market: MarketSnapshot
) -> SimpleNamespace:
    """Terms + snapshot marks (+ Position duration when present). Never reads DTO marks."""
    attrs = dict(terms.model_dump())
    attrs.update(snapshot_marks_from_terms(terms, market))
    duration = getattr(position, "duration", None)
    if duration is not None:
        attrs["duration"] = duration
    return SimpleNamespace(**attrs)
