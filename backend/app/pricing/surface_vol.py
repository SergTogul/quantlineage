"""Resolve option implied vol from ``MarketSnapshot.vol_surfaces`` when present.

Rebuilds RiskForge ``VolSurface`` from the snapshot payload grid
(``expiry|moneyness`` → vol). QuantLib types stay out of this module.
"""

from __future__ import annotations

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
