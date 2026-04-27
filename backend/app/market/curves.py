"""Yield-curve scaffolding (M1.4).

RiskForge-owned curve types. Interpolation is linear in continuous zeros
(Actual/365-style year fractions). QuantLib is not required on the public
surface; adapters may consume ``to_dict()`` / ``df`` / ``zero`` later.

Conventions
-----------
- Zero rates: continuously compounded absolute decimal (0.04 = 4%).
- Shifts: basis points (25 = +0.0025 absolute), converted via
  ``app.risk.shock_units.bps_to_decimal_rate`` (no inline bp-to-decimal scale).
- Key tenors: 1Y, 2Y, 5Y, 7Y, 10Y, 20Y, 30Y.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Mapping

from app.risk.shock_units import bps_to_decimal_rate

CurveType = Literal["discount", "projection"]
BootstrapInstrumentKind = Literal["deposit", "simple", "zero"]

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


def tenor_to_years(tenor: str) -> float:
    """Parse simple tenor strings into Actual/365-style year fractions."""
    key = tenor.strip().upper()
    if key in TENOR_YEARS:
        return TENOR_YEARS[key]
    if len(key) < 2:
        raise ValueError(f"unsupported tenor: {tenor!r}")
    try:
        amount = float(key[:-1])
    except ValueError as exc:
        raise ValueError(f"unsupported tenor: {tenor!r}") from exc
    unit = key[-1]
    if unit == "D":
        years = amount / 365.0
    elif unit == "W":
        years = amount * 7.0 / 365.0
    elif unit == "M":
        years = amount / 12.0
    elif unit == "Y":
        years = amount
    else:
        raise ValueError(f"unsupported tenor: {tenor!r}")
    if years <= 0.0:
        raise ValueError(f"tenor must be positive: {tenor!r}")
    return years


@dataclass(frozen=True, slots=True)
class CurveNode:
    tenor: str
    years: float
    zero_rate: float


@dataclass(frozen=True, slots=True)
class CurveBootstrapInstrument:
    """Minimal deterministic market instrument for curve bootstrapping.

    ``deposit`` / ``simple`` rates are annualized simple rates converted to
    continuous zero rates via ``df = 1 / (1 + rT)``. ``zero`` rates are already
    continuous zeros.
    """

    kind: BootstrapInstrumentKind
    tenor: str
    rate: float

    def __post_init__(self) -> None:
        if self.kind not in {"deposit", "simple", "zero"}:
            raise ValueError(f"unsupported bootstrap instrument kind: {self.kind!r}")
        object.__setattr__(self, "tenor", self.tenor.strip().upper())
        tenor_to_years(self.tenor)
        object.__setattr__(self, "rate", float(self.rate))

    @property
    def years(self) -> float:
        return tenor_to_years(self.tenor)

    def zero_rate(self) -> float:
        if self.kind == "zero":
            return float(self.rate)
        denominator = 1.0 + float(self.rate) * self.years
        if denominator <= 0.0:
            raise ValueError(
                f"simple-rate bootstrap instrument {self.tenor} implies non-positive discount factor"
            )
        return math.log(denominator) / self.years

    def to_dict(self) -> dict:
        return {"kind": self.kind, "tenor": self.tenor, "rate": self.rate}


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
        shift = bps_to_decimal_rate(bps)
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
        shift = bps_to_decimal_rate(bps)
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


def bootstrap_yield_curve(
    currency: str,
    curve_type: CurveType,
    name: str,
    instruments: tuple[CurveBootstrapInstrument, ...] | list[CurveBootstrapInstrument],
) -> YieldCurve:
    """Build a deterministic zero curve from explicit market instruments.

    This is intentionally a scoped single-curve bootstrap: no calendars,
    futures convexity, swaps, stubs, turn-of-year effects, or multi-curve
    calibration. Instruments are sorted by maturity so equal inputs produce
    byte-stable curve payloads independent of caller order.
    """
    if not instruments:
        raise ValueError("bootstrap requires at least one instrument")

    ordered = tuple(sorted(instruments, key=lambda inst: (inst.years, inst.tenor, inst.kind)))
    seen: set[str] = set()
    nodes: list[CurveNode] = []
    for instrument in ordered:
        if instrument.tenor in seen:
            raise ValueError(f"duplicate bootstrap tenor: {instrument.tenor}")
        seen.add(instrument.tenor)
        nodes.append(
            CurveNode(
                tenor=instrument.tenor,
                years=instrument.years,
                zero_rate=instrument.zero_rate(),
            )
        )
    return YieldCurve(currency=currency.upper(), curve_type=curve_type, name=name, nodes=tuple(nodes))


def attach_bootstrapped_curve(
    snapshot,
    *,
    currency: str,
    curve_type: CurveType,
    name: str,
    instruments: tuple[CurveBootstrapInstrument, ...] | list[CurveBootstrapInstrument],
):
    """Attach a bootstrapped curve payload and scalar/key-rate views to a snapshot."""
    curve = bootstrap_yield_curve(currency, curve_type, name, instruments)
    ordered_instruments = tuple(sorted(instruments, key=lambda inst: (inst.years, inst.tenor, inst.kind)))
    from app.domain.models import _deep_unfreeze

    payload = curve.to_dict()
    payload["bootstrap"] = {
        "method": "simple_deposit_zero",
        "instruments": [inst.to_dict() for inst in ordered_instruments],
        "limitations": "single-curve deterministic bootstrap; no live data or production multi-curve calibration",
    }

    ccy = curve.currency
    curves = _deep_unfreeze(snapshot.curves)
    curves[curve.name] = payload
    key_rates = _deep_unfreeze(snapshot.key_rates)
    if curve.curve_type == "discount":
        key_rates[ccy] = {node.tenor: node.zero_rate for node in curve.nodes}

    rates = dict(snapshot.rates)
    projection = dict(snapshot.projection_rates)
    first_zero = float(curve.nodes[0].zero_rate)
    if curve.curve_type == "projection":
        projection[ccy] = first_zero
    else:
        rates[ccy] = first_zero

    return snapshot.model_copy(
        update={
            "id": f"{snapshot.id}:bootstrapped:{curve.name}",
            "curves": curves,
            "key_rates": key_rates,
            "rates": rates,
            "projection_rates": projection,
        }
    )


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
    "BootstrapInstrumentKind",
    "KEY_TENORS",
    "TENOR_YEARS",
    "CurveBootstrapInstrument",
    "CurveNode",
    "YieldCurve",
    "attach_bootstrapped_curve",
    "bootstrap_yield_curve",
    "build_flat_curve",
    "build_usd_ois_discount",
    "build_usd_sofr_projection",
    "attach_standard_usd_curves",
    "tenor_to_years",
]
