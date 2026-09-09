"""Canonical typed sub-market views over ``MarketSnapshot`` (R0.4.1-A).

Flat dict fields on ``MarketSnapshot`` remain the storage/API shape. Risk and
pricing consumers that need grouped market semantics should use
``snapshot.equity``, ``.rates_market``, ``.vol``, and ``.fx``, which return the
frozen dataclasses below wrapping the already-frozen nested mappings
(``MappingProxyType``). This module does not replace snapshot storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class EquityMarket:
    """Equity spots and dividend yields from a snapshot."""

    spots: Mapping[str, float]
    dividend_yields: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class RateMarket:
    """Scalar discount/projection/spreads plus key-rate pillars (M1.4)."""

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
    """FX spot marks from a snapshot."""

    spots: Mapping[str, float]
