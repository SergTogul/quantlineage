"""Resolve option implied vol from ``MarketSnapshot.vol_surfaces`` when present.

Rebuilds RiskForge ``VolSurface`` from the snapshot payload grid
(``expiry|moneyness`` → vol). QuantLib types stay out of this module.
"""

from __future__ import annotations

from typing import Mapping

from app.market.vol_surfaces import VolSurface


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
    return _surface_from_payload(raw, default_name=name).vol(maturity_years, strike / spot)


def _surface_from_payload(payload: Mapping, *, default_name: str) -> VolSurface:
    raw_grid = payload.get("grid") or {}
    grid: dict[tuple[str, float], float] = {}
    for key, vol in raw_grid.items():
        expiry_s, m_s = str(key).split("|", 1)
        grid[(expiry_s, float(m_s))] = float(vol)
    return VolSurface.from_grid(
        str(payload.get("name") or default_name),
        payload["asset_class"],
        grid,
    )
