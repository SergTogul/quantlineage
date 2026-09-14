"""Resolve option implied vol from ``MarketSnapshot.vol_surfaces`` when present.

Rebuilds QuantLineage ``VolSurface`` from the snapshot payload grid
(``expiry|moneyness`` → vol). QuantLib types stay out of this module.
"""

from __future__ import annotations

from app.market.demo_snapshot import MissingMarketDataError
from app.market.vol_surfaces import vol_surface_from_dict


def option_vol_from_snapshot(
    market,
    *,
    name: str,
    maturity_years: float,
    strike: float,
    spot: float,
    fallback: float,
) -> float:
    """Surface vol at ``(maturity_years, strike/spot)``; else ``fallback`` scalar."""
    surfaces = getattr(market, "vol_surfaces", None) or {}
    raw = surfaces.get(name)
    if raw is None or spot <= 0:
        return fallback
    return vol_surface_from_dict(raw, default_name=name).vol(maturity_years, strike / spot)


def required_equity_option_vol(
    market,
    *,
    name: str,
    maturity_years: float,
    strike: float,
    spot: float,
) -> float:
    """Surface vol if usable; else ``equity_vols[name]``; else ``MissingMarketDataError``.

    Does not fall back to a trade-local mark. Callers keep ``position.volatility``
    only when ``market is None``.
    """
    surfaces = getattr(market, "vol_surfaces", None) or {}
    raw = surfaces.get(name)
    if raw is not None and spot > 0:
        return option_vol_from_snapshot(
            market,
            name=name,
            maturity_years=maturity_years,
            strike=strike,
            spot=spot,
            fallback=0.0,
        )
    try:
        return market.equity_vols[name]
    except KeyError:
        raise MissingMarketDataError(f"equity_vols[{name}]") from None


def required_fx_option_vol(
    market,
    *,
    name: str,
    maturity_years: float,
    strike: float,
    spot: float,
) -> float:
    """Surface vol if usable; else ``fx_vols[name]``; else ``MissingMarketDataError``.

    Does not fall back to a trade-local mark. Callers keep ``position.volatility``
    only when ``market is None``.
    """
    surfaces = getattr(market, "vol_surfaces", None) or {}
    raw = surfaces.get(name)
    if raw is not None and spot > 0:
        return option_vol_from_snapshot(
            market,
            name=name,
            maturity_years=maturity_years,
            strike=strike,
            spot=spot,
            fallback=0.0,
        )
    try:
        return market.fx_vols[name]
    except KeyError:
        raise MissingMarketDataError(f"fx_vols[{name}]") from None


def required_ir_option_vol(
    market,
    *,
    name: str,
    maturity_years: float,
    strike: float,
    forward: float,
) -> float:
    """Surface vol if usable; else ``ir_vols[name]``; else ``MissingMarketDataError``.

    Does not fall back to a trade-local mark. Callers keep ``position.volatility``
    only when ``market is None``.
    """
    surfaces = getattr(market, "vol_surfaces", None) or {}
    raw = surfaces.get(name)
    if raw is not None and forward > 0:
        return option_vol_from_snapshot(
            market,
            name=name,
            maturity_years=maturity_years,
            strike=strike,
            spot=forward,
            fallback=0.0,
        )
    try:
        return market.ir_vols[name]
    except KeyError:
        raise MissingMarketDataError(f"ir_vols[{name}]") from None
