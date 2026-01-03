"""Sub-market views over a MarketSnapshot (immutable mappings)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class EquityMarket:
    spots: Mapping[str, float]
    dividend_yields: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class RateMarket:
    """Scalar discount marks today; projection/spreads/key_rates scaffold for M1.4."""

    discount: Mapping[str, float]
    projection: Mapping[str, float]
    spreads: Mapping[str, float]
    key_rates: Mapping[str, Mapping[str, float]]


@dataclass(frozen=True, slots=True)
class VolMarket:
    """Scalar ATM vols plus optional named surface payloads (M1.5)."""

    equity: Mapping[str, float]
    fx: Mapping[str, float]
    surfaces: Mapping[str, Mapping]


@dataclass(frozen=True, slots=True)
class FxMarket:
    spots: Mapping[str, float]
