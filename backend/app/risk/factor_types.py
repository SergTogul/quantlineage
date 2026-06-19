"""Typed risk-factor taxonomy with stable string keys for API compatibility.

Risk vectors and market bumps should prefer these types internally. API / DTO
layers continue to expose ``factor: str`` via :attr:`RiskFactor.key`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

FactorType = Literal["equity", "vol", "rate", "fx"]


@dataclass(frozen=True, slots=True)
class EquitySpot:
    """Equity (or equity-index) spot risk factor."""

    symbol: str

    @property
    def key(self) -> str:
        return self.symbol

    @property
    def factor_type(self) -> FactorType:
        return "equity"

    @property
    def bucket(self) -> str:
        return self.symbol


@dataclass(frozen=True, slots=True)
class EquityVol:
    """Equity implied-vol risk factor.

    ``key`` stays ``{underlying}:VOL`` for API compatibility even when expiry /
    moneyness distinguish richer surface buckets later.
    """

    underlying: str
    expiry: str = "GENERIC"
    moneyness: str = "ATM"

    @property
    def key(self) -> str:
        return f"{self.underlying}:VOL"

    @property
    def factor_type(self) -> FactorType:
        return "vol"

    @property
    def bucket(self) -> str:
        return self.underlying


@dataclass(frozen=True, slots=True)
class RateZero:
    """Zero / discount-rate risk factor for a currency tenor.

    ``tenor`` of ``PARALLEL`` or ``ALL`` requests a parallel curve/scalar shock
    via :meth:`MarketSnapshot.bump`. Specific tenors (e.g. ``10Y``) bump only
    that pillar in ``key_rates`` / curve zeros — not scalar ``rates[ccy]``.
    """

    currency: str
    tenor: str

    @property
    def key(self) -> str:
        return f"{self.currency}:RATE"

    @property
    def factor_type(self) -> FactorType:
        return "rate"

    @property
    def bucket(self) -> str:
        return self.tenor


@dataclass(frozen=True, slots=True)
class FXSpot:
    """FX spot risk factor identified by a currency pair (e.g. EURUSD)."""

    pair: str

    @property
    def key(self) -> str:
        return self.pair

    @property
    def factor_type(self) -> FactorType:
        return "fx"

    @property
    def bucket(self) -> str:
        return self.pair


@dataclass(frozen=True, slots=True)
class FXVol:
    """FX implied-vol risk factor.

    ``key`` stays ``{pair}:VOL`` for API compatibility.
    """

    pair: str
    expiry: str = "GENERIC"
    moneyness: str = "ATM"

    @property
    def key(self) -> str:
        return f"{self.pair}:VOL"

    @property
    def factor_type(self) -> FactorType:
        return "vol"

    @property
    def bucket(self) -> str:
        return self.pair


RiskFactor = Union[EquitySpot, EquityVol, RateZero, FXSpot, FXVol]


def parse_risk_factor(
    factor: str,
    factor_type: FactorType,
    bucket: str,
    *,
    expiry: str = "GENERIC",
    moneyness: str = "ATM",
) -> RiskFactor:
    """Rebuild a typed factor from legacy string ``(factor, factor_type, bucket)``."""
    if factor_type == "equity":
        return EquitySpot(symbol=factor)
    if factor_type == "fx":
        return FXSpot(pair=factor)
    if factor_type == "rate":
        currency = factor.removesuffix(":RATE") if factor.endswith(":RATE") else factor
        return RateZero(currency=currency, tenor=bucket)
    if factor_type == "vol":
        if factor.endswith(":VOL"):
            name = factor[: -len(":VOL")]
        else:
            name = factor
        # Heuristic: FX pairs are typically 6-letter ISO codes without spaces.
        if len(name) == 6 and name.isalpha() and name.isupper():
            return FXVol(pair=name, expiry=expiry, moneyness=moneyness)
        return EquityVol(underlying=name or bucket, expiry=expiry, moneyness=moneyness)
    raise ValueError(f"unknown factor_type: {factor_type!r}")


def factor_sort_key(factor: RiskFactor) -> tuple[str, str, str]:
    """Stable sort key matching historical RiskFactorEngine ordering."""
    return (factor.key, factor.factor_type, factor.bucket)


def factor_column_id(factor: RiskFactor) -> str:
    """Stable CSV / panel column id (``EquitySpot:AAPL``, ``RateZero:USD:2Y``, …)."""
    if isinstance(factor, EquitySpot):
        return f"EquitySpot:{factor.symbol}"
    if isinstance(factor, EquityVol):
        return f"EquityVol:{factor.underlying}"
    if isinstance(factor, RateZero):
        return f"RateZero:{factor.currency}:{factor.tenor}"
    if isinstance(factor, FXSpot):
        return f"FXSpot:{factor.pair}"
    if isinstance(factor, FXVol):
        return f"FXVol:{factor.pair}"
    raise TypeError(f"unsupported risk factor type: {type(factor)!r}")


def parse_factor_column_id(column: str) -> RiskFactor:
    """Parse a ``factor_column_id`` header into a typed ``RiskFactor``."""
    raw = column.strip()
    parts = raw.split(":")
    if len(parts) < 2:
        raise ValueError(f"unrecognized factor column: {column!r}")
    kind, rest = parts[0], parts[1:]
    if kind == "EquitySpot" and len(rest) == 1 and rest[0]:
        return EquitySpot(rest[0])
    if kind == "EquityVol" and len(rest) == 1 and rest[0]:
        return EquityVol(underlying=rest[0])
    if kind == "RateZero" and len(rest) == 2 and rest[0] and rest[1]:
        return RateZero(rest[0], rest[1])
    if kind == "FXSpot" and len(rest) == 1 and rest[0]:
        return FXSpot(rest[0])
    if kind == "FXVol" and len(rest) == 1 and rest[0]:
        return FXVol(pair=rest[0])
    raise ValueError(f"unrecognized factor column: {column!r}")
