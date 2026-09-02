"""Yield-curve scaffolding (M1.4).

RiskForge-owned curve types. Interpolation is linear in continuous zeros
(Actual/365-style year fractions). QuantLib is not required on the public
surface; adapters may consume ``to_dict()`` / ``df`` / ``zero`` later.

Conventions
-----------
- Zero rates: continuously compounded absolute decimal (0.04 = 4%).
- Shifts: basis points (25 = +0.0025 absolute).
- Key tenors: 1Y, 2Y, 5Y, 7Y, 10Y, 20Y, 30Y.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Mapping

CurveType = Literal["discount", "projection"]

KEY_TENORS: tuple[str, ...] = ("1Y", "2Y", "5Y", "7Y", "10Y", "20Y", "30Y")
TENOR_YEARS: dict[str, float] = {
    "1Y": 1.0,
    "2Y": 2.0,
    "5Y": 5.0,
    "7Y": 7.0,
    "10Y": 10.0,
    "20Y": 20.0,
    "30Y": 30.0,
}


@dataclass(frozen=True, slots=True)
class CurveNode:
    tenor: str
    years: float
    zero_rate: float


@dataclass(frozen=True, slots=True)
class YieldCurve:
    """Immutable yield curve with linear-in-zero interpolation."""

    currency: str
    curve_type: CurveType
    name: str
    nodes: tuple[CurveNode, ...]

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("curve requires at least one node")
        years = [n.years for n in self.nodes]
        if years != sorted(years) or len(set(years)) != len(years):
            raise ValueError("curve nodes must be strictly increasing in years")

    @classmethod
    def from_zero_dict(
        cls,
        currency: str,
        curve_type: CurveType,
        name: str,
        zeros: Mapping[str, float],
    ) -> YieldCurve:
        missing = [t for t in KEY_TENORS if t not in zeros]
        if missing:
            raise KeyError(f"missing key tenors: {missing}")
        nodes = tuple(
            CurveNode(tenor=t, years=TENOR_YEARS[t], zero_rate=float(zeros[t]))
            for t in KEY_TENORS
        )
        return cls(currency=currency, curve_type=curve_type, name=name, nodes=nodes)

    def zero(self, t: float) -> float:
        """Continuously compounded zero rate at year fraction ``t``."""
        if t < 0:
            raise ValueError(f"t must be >= 0, got {t}")
        nodes = self.nodes
        if t <= nodes[0].years:
            return float(nodes[0].zero_rate)
        if t >= nodes[-1].years:
            return float(nodes[-1].zero_rate)
        for left, right in zip(nodes, nodes[1:]):
            if left.years <= t <= right.years:
                w = (t - left.years) / (right.years - left.years)
                return float(left.zero_rate + w * (right.zero_rate - left.zero_rate))
        return float(nodes[-1].zero_rate)

    def df(self, t: float) -> float:
        """Discount factor ``exp(-z(t) * t)``; ``df(0) = 1``."""
        if t < 0:
            raise ValueError(f"t must be >= 0, got {t}")
        if t == 0.0:
            return 1.0
        return float(math.exp(-self.zero(t) * t))

    def parallel_shift_bps(self, bps: float) -> YieldCurve:
        """Add ``bps`` to every pillar (immutable)."""
        shift = bps / 10_000.0
        nodes = tuple(
            CurveNode(tenor=n.tenor, years=n.years, zero_rate=n.zero_rate + shift)
            for n in self.nodes
        )
        return YieldCurve(
            currency=self.currency,
            curve_type=self.curve_type,
            name=self.name,
            nodes=nodes,
        )

    def key_rate_shift_bps(self, tenor: str, bps: float) -> YieldCurve:
        """Bump a single key tenor; linear zero interpolation yields a tent bump."""
        if tenor not in TENOR_YEARS:
            raise KeyError(f"unknown key tenor: {tenor}")
        shift = bps / 10_000.0
        nodes = tuple(
            CurveNode(
                tenor=n.tenor,
                years=n.years,
                zero_rate=n.zero_rate + (shift if n.tenor == tenor else 0.0),
            )
            for n in self.nodes
        )
        return YieldCurve(
            currency=self.currency,
            curve_type=self.curve_type,
            name=self.name,
            nodes=nodes,
        )

    def to_dict(self) -> dict:
        """Plain JSON-serializable payload for ``MarketSnapshot.curves``."""
        return {
            "currency": self.currency,
            "curve_type": self.curve_type,
            "name": self.name,
            "zeros": {n.tenor: n.zero_rate for n in self.nodes},
        }


def build_flat_curve(
    currency: str,
    curve_type: CurveType,
    name: str,
    rate: float,
) -> YieldCurve:
    """Flat continuous-zero curve across all key tenors (EUR/GBP architecture hook)."""
    zeros = {t: rate for t in KEY_TENORS}
    return YieldCurve.from_zero_dict(currency, curve_type, name, zeros)


def build_usd_ois_discount(base_rate: float = 0.04) -> YieldCurve:
    return build_flat_curve("USD", "discount", "USD_OIS", base_rate)


def build_usd_sofr_projection(base_rate: float = 0.041) -> YieldCurve:
    return build_flat_curve("USD", "projection", "USD_SOFR", base_rate)


def attach_standard_usd_curves(
    snapshot,
    *,
    ois_rate: float = 0.04,
    sofr_rate: float = 0.041,
):
    """Attach USD OIS/SOFR curve payloads + USD key_rates onto a MarketSnapshot.

    Does not mutate ``snapshot``; returns a new frozen copy.
    """
    ois = build_usd_ois_discount(ois_rate)
    sofr = build_usd_sofr_projection(sofr_rate)
    from app.domain.models import _deep_unfreeze

    curves = _deep_unfreeze(snapshot.curves)
    curves[ois.name] = ois.to_dict()
    curves[sofr.name] = sofr.to_dict()
    key_rates = _deep_unfreeze(snapshot.key_rates)
    key_rates["USD"] = {n.tenor: n.zero_rate for n in ois.nodes}
    rates = dict(snapshot.rates)
    rates["USD"] = ois_rate
    projection = dict(snapshot.projection_rates)
    projection["USD"] = sofr_rate
    return snapshot.model_copy(
        update={
            "id": f"{snapshot.id}:usd_curves",
            "curves": curves,
            "key_rates": key_rates,
            "rates": rates,
            "projection_rates": projection,
        }
    )


__all__ = [
    "KEY_TENORS",
    "TENOR_YEARS",
    "CurveNode",
    "YieldCurve",
    "build_flat_curve",
    "build_usd_ois_discount",
    "build_usd_sofr_projection",
    "attach_standard_usd_curves",
]
