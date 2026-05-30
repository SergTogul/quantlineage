"""Canonical typed sub-market views over ``MarketSnapshot`` (R0.4.1-B).

Flat dict fields on ``MarketSnapshot`` remain the storage/API shape. Risk and
pricing consumers that need grouped market semantics should use
``snapshot.equity``, ``.rates_market``, ``.vol``, and ``.fx``, which return the
frozen dataclasses below wrapping the already-frozen nested mappings
(``MappingProxyType``). Named ``VolMarket.surfaces`` and ``RateMarket.curves``
are reconstructed as ``VolSurface`` / ``YieldCurve`` (fail closed on present
invalid payloads). This module does not replace snapshot storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.market.curves import KEY_TENORS, CurveNode, CurveType, YieldCurve, tenor_to_years
from app.market.vol_surfaces import VolSurface, vol_surface_from_dict


def typed_vol_surfaces(payloads: Mapping[str, Mapping]) -> Mapping[str, VolSurface]:
    """Rebuild named ``VolSurface`` objects from snapshot ``vol_surfaces`` dicts.

    Empty ``payloads`` stays an empty mapping. A present invalid payload fails
    closed (``ValueError`` / ``KeyError`` / ``TypeError``), never skipped.
    """
    if not payloads:
        return MappingProxyType({})
    out: dict[str, VolSurface] = {}
    for name, payload in payloads.items():
        if not isinstance(payload, Mapping):
            raise TypeError(f"vol surface {name!r} must be a mapping")
        out[str(name)] = vol_surface_from_dict(payload, default_name=str(name))
    return MappingProxyType(out)


def yield_curve_from_snapshot_payload(name: str, payload: Mapping) -> YieldCurve:
    """Rebuild one ``YieldCurve`` from a snapshot ``curves`` payload.

    Uses ``YieldCurve.from_zero_dict`` when all key tenors are present;
    otherwise an equivalent node reconstruction. Present invalid payloads fail
    closed — empty/missing zeros and unknown tenors are not skipped.
    """
    if not isinstance(payload, Mapping):
        raise TypeError(f"curve {name!r} must be a mapping")
    zeros = payload.get("zeros")
    if not isinstance(zeros, Mapping):
        raise TypeError(f"curve {name!r} zeros must be a mapping")
    if not zeros:
        raise ValueError(f"curve {name!r} requires zeros")
    currency = str(payload.get("currency") or "")
    if not currency:
        raise ValueError(f"curve {name!r} requires currency")
    raw_type = payload.get("curve_type", "discount")
    if raw_type not in ("discount", "projection"):
        raise ValueError(f"curve {name!r} invalid curve_type: {raw_type!r}")
    curve_type: CurveType = raw_type
    curve_name = str(payload.get("name") or name)
    if all(t in zeros for t in KEY_TENORS):
        return YieldCurve.from_zero_dict(currency, curve_type, curve_name, zeros)
    nodes = tuple(
        sorted(
            (
                CurveNode(
                    tenor=str(tenor),
                    years=tenor_to_years(str(tenor)),
                    zero_rate=float(rate),
                )
                for tenor, rate in zeros.items()
            ),
            key=lambda node: node.years,
        )
    )
    return YieldCurve(
        currency=currency,
        curve_type=curve_type,
        name=curve_name,
        nodes=nodes,
    )


def typed_yield_curves(payloads: Mapping[str, Mapping]) -> Mapping[str, YieldCurve]:
    """Rebuild named ``YieldCurve`` objects from snapshot ``curves`` dicts.

    Empty ``payloads`` stays an empty mapping. A present invalid payload fails
    closed (``ValueError`` / ``KeyError`` / ``TypeError``), never skipped.
    """
    if not payloads:
        return MappingProxyType({})
    out: dict[str, YieldCurve] = {}
    for name, payload in payloads.items():
        out[str(name)] = yield_curve_from_snapshot_payload(str(name), payload)
    return MappingProxyType(out)


def _require_fx_spot_keys(spots: Mapping[str, float]) -> None:
    """Reject non-6-letter ISO FX pair keys. Empty ``spots`` is valid."""
    from app.domain.models import _require_fx_pair

    for pair in spots:
        try:
            _require_fx_pair(str(pair))
        except Exception as exc:
            raise ValueError(f"invalid FX pair key: {pair!r}") from exc


@dataclass(frozen=True, slots=True)
class EquityMarket:
    """Equity spots and dividend yields from a snapshot."""

    spots: Mapping[str, float]
    dividend_yields: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class RateMarket:
    """Scalar discount/projection/spreads, key-rate pillars, and named curves."""

    discount: Mapping[str, float]
    projection: Mapping[str, float]
    spreads: Mapping[str, float]
    key_rates: Mapping[str, Mapping[str, float]]
    curves: Mapping[str, YieldCurve]


@dataclass(frozen=True, slots=True)
class VolMarket:
    """Scalar ATM vols plus named typed surfaces (M1.5)."""

    equity: Mapping[str, float]
    fx: Mapping[str, float]
    surfaces: Mapping[str, VolSurface]


@dataclass(frozen=True, slots=True)
class FxMarket:
    """FX spot marks from a snapshot."""

    spots: Mapping[str, float]

    def __post_init__(self) -> None:
        _require_fx_spot_keys(self.spots)
