"""Resolve discount / projection rates from ``MarketSnapshot`` curves and key rates.

Pricing adapters prefer:
1. typed curve payloads in ``market.curves`` (discount vs projection);
2. ``market.key_rates[ccy]`` rebuilt as a sparse :class:`YieldCurve`;
3. scalar ``market.rates`` / ``projection_rates`` / trade marks.

Zero rates are continuously compounded (same convention as ``app.market.curves``).
QuantLib types stay out of this module.
"""

from __future__ import annotations

from typing import Mapping

from app.domain.models import MarketSnapshot
from app.market.curves import CurveNode, CurveType, YieldCurve, tenor_to_years


def curve_from_payload(name: str, payload: Mapping) -> YieldCurve | None:
    """Build a :class:`YieldCurve` from a snapshot curve / zeros dict payload."""
    zeros = payload.get("zeros")
    if not isinstance(zeros, Mapping) or not zeros:
        return None
    currency = str(payload.get("currency", "") or "")
    raw_type = payload.get("curve_type", "discount")
    curve_type: CurveType = "projection" if raw_type == "projection" else "discount"
    nodes: list[CurveNode] = []
    for tenor, rate in zeros.items():
        try:
            years = tenor_to_years(str(tenor))
        except ValueError:
            continue
        nodes.append(CurveNode(tenor=str(tenor), years=years, zero_rate=float(rate)))
    if not nodes:
        return None
    ordered = tuple(sorted(nodes, key=lambda n: n.years))
    return YieldCurve(
        currency=currency,
        curve_type=curve_type,
        name=str(payload.get("name") or name),
        nodes=ordered,
    )


def _select_yield_curve_uncached(
    market: MarketSnapshot,
    currency: str,
    *,
    prefer_projection: bool = False,
) -> YieldCurve | None:
    """Pick the best RiskForge curve for ``currency``, or synthesize from key rates."""
    ccy = currency.upper()
    candidates: list[YieldCurve] = []
    for name, payload in market.curves.items():
        if not isinstance(payload, Mapping):
            continue
        if str(payload.get("currency", "")).upper() != ccy:
            continue
        curve = curve_from_payload(str(name), payload)
        if curve is not None:
            candidates.append(curve)

    if prefer_projection:
        for curve in candidates:
            if curve.curve_type == "projection":
                return curve
    for curve in candidates:
        if curve.curve_type == "discount":
            return curve
    if candidates:
        return candidates[0]

    nested = market.key_rates.get(currency) or market.key_rates.get(ccy)
    if nested:
        return curve_from_payload(
            f"{ccy}_KEY",
            {
                "currency": ccy,
                "curve_type": "discount",
                "name": f"{ccy}_KEY",
                "zeros": nested,
            },
        )
    return None


def select_yield_curve(
    market: MarketSnapshot,
    currency: str,
    *,
    prefer_projection: bool = False,
) -> YieldCurve | None:
    """Pick the best RiskForge curve for ``currency``, or synthesize from key rates.

    When ``RISKFORGE_CURVE_CACHE`` is enabled (default), constructed ``YieldCurve``
    instances are memoized by currency-relevant market fingerprint.
    """
    from app.pricing.curve_cache import (
        curve_cache_enabled,
        curve_cache_key,
        get_curve_construction_cache,
    )

    if not curve_cache_enabled():
        return _select_yield_curve_uncached(
            market, currency, prefer_projection=prefer_projection
        )

    key = curve_cache_key(market, currency, prefer_projection=prefer_projection)
    cache = get_curve_construction_cache()
    hit = cache.get(key)
    if hit is not None:
        return hit

    built = _select_yield_curve_uncached(
        market, currency, prefer_projection=prefer_projection
    )
    if built is None:
        return None
    return cache.put(key, built)


def has_curve_or_key_rates(market: MarketSnapshot | None, currency: str) -> bool:
    if market is None:
        return False
    return select_yield_curve(market, currency) is not None


def continuous_zero(
    market: MarketSnapshot | None,
    currency: str,
    maturity_years: float,
    *,
    fallback: float,
    prefer_projection: bool = False,
) -> float:
    """Continuous zero at ``maturity_years``; scalar market / trade mark as fallback."""
    if market is not None:
        curve = select_yield_curve(market, currency, prefer_projection=prefer_projection)
        if curve is not None:
            return float(curve.zero(maturity_years))
        if prefer_projection and currency in market.projection_rates:
            return float(market.projection_rates[currency])
        if currency in market.rates:
            return float(market.rates[currency])
    return float(fallback)


def discount_factor(
    market: MarketSnapshot | None,
    currency: str,
    maturity_years: float,
    *,
    fallback_yield: float,
) -> float | None:
    """Continuous DF from curves/key_rates, or ``None`` to keep annual scalar compounding."""
    if market is None or not has_curve_or_key_rates(market, currency):
        return None
    curve = select_yield_curve(market, currency, prefer_projection=False)
    assert curve is not None
    return float(curve.df(maturity_years))
