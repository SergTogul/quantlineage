"""Trade-grain calculation artifact for reusable risk-run results (R0.7.2 / RF-008).

A risk run should be able to produce and reuse, per stable trade id:

- trade PV;
- additive sensitivities already treated as parent == sum(children) by
  ``HierarchyEngine`` (delta, gamma, vega, dv01, fx_delta);
- tenor-bucket key-rate DV01 contributions;
- stress P&L keyed by scenario id;
- an optional historical P&L vector.

This module is the **type + aggregation helpers only**. Hierarchy consumes
these artifacts on both the explicit ``artifacts=`` path and the default
no-artifact path (R0.7.5 builds the map once per run). Do not import
``hierarchy``.

Units / signs match ``Valuation`` / ``HierarchyNode``:

- ``pv`` — currency market value;
- ``delta`` / ``fx_delta`` — cash delta;
- ``gamma`` — dollar gamma;
- ``vega`` — P&L per 1 absolute vol point;
- ``dv01`` — P&L for a +1bp parallel rate move;
- ``key_rate_dv01`` — mapping of stable currency/tenor bucket id to P&L for a +1bp tenor move;
- ``stress_pnl`` / ``historical_pnl`` — currency P&L.

All stored numbers must be finite. ``historical_pnl`` is omitted as ``None``;
an empty sequence is rejected (not stored as empty).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from app.domain.models import Valuation

_ADDITIVE_GREEKS: tuple[str, ...] = ("delta", "gamma", "vega", "dv01", "fx_delta")


def _require_finite(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return number


def _require_trade_id(trade_id: str) -> str:
    if not isinstance(trade_id, str) or not trade_id.strip():
        raise ValueError("trade_id must be a non-empty string")
    return trade_id


def _freeze_numeric_mapping(
    name: str,
    values: Mapping[str, float] | None,
) -> Mapping[str, float]:
    if values is None:
        return MappingProxyType({})
    if isinstance(values, str) or not isinstance(values, Mapping):
        raise ValueError(f"{name} must be a mapping of non-empty string keys to finite values")
    frozen: dict[str, float] = {}
    for raw_key, raw_value in values.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError(f"{name} keys must be non-empty strings")
        frozen[raw_key] = _require_finite(f"{name}[{raw_key!r}]", raw_value)
    return MappingProxyType(frozen)


def _freeze_stress_pnl(stress_pnl: Mapping[str, float] | None) -> Mapping[str, float]:
    return _freeze_numeric_mapping("stress_pnl", stress_pnl)


def _freeze_key_rate_dv01(
    key_rate_dv01: Mapping[str, float] | None,
) -> Mapping[str, float]:
    return _freeze_numeric_mapping("key_rate_dv01", key_rate_dv01)


def _freeze_historical_pnl(
    historical_pnl: Sequence[float] | None,
) -> tuple[float, ...] | None:
    if historical_pnl is None:
        return None
    if isinstance(historical_pnl, (str, bytes)) or not isinstance(historical_pnl, Sequence):
        raise ValueError("historical_pnl must be a real sequence of finite floats, or omitted")
    if len(historical_pnl) == 0:
        raise ValueError("historical_pnl may be empty only if omitted (None)")
    return tuple(
        _require_finite(f"historical_pnl[{i}]", value)
        for i, value in enumerate(historical_pnl)
    )


def _merge_numeric_mapping(
    left: Mapping[str, float],
    right: Mapping[str, float],
) -> dict[str, float]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = merged.get(key, 0.0) + value
    return merged


def _merge_stress(
    left: Mapping[str, float],
    right: Mapping[str, float],
) -> dict[str, float]:
    return _merge_numeric_mapping(left, right)


def _add_historical(
    left: Sequence[float] | None,
    right: Sequence[float] | None,
) -> tuple[float, ...] | None:
    if left is None and right is None:
        return None
    if left is None or right is None:
        raise ValueError(
            "historical_pnl is present on only one artifact; omit both or use equal lengths"
        )
    if len(left) != len(right):
        raise ValueError(
            f"historical_pnl length mismatch: {len(left)} != {len(right)}"
        )
    return tuple(a + b for a, b in zip(left, right, strict=True))


@dataclass(frozen=True, slots=True)
class TradeCalculationArtifact:
    """Frozen per-trade PV, Greeks, key-rate buckets, stress, and historical P&L."""

    trade_id: str
    pv: float
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    dv01: float = 0.0
    fx_delta: float = 0.0
    key_rate_dv01: Mapping[str, float] = field(default_factory=dict)
    stress_pnl: Mapping[str, float] = field(default_factory=dict)
    historical_pnl: Sequence[float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _require_trade_id(self.trade_id))
        object.__setattr__(self, "pv", _require_finite("pv", self.pv))
        for name in _ADDITIVE_GREEKS:
            object.__setattr__(self, name, _require_finite(name, getattr(self, name)))
        object.__setattr__(self, "key_rate_dv01", _freeze_key_rate_dv01(self.key_rate_dv01))
        object.__setattr__(self, "stress_pnl", _freeze_stress_pnl(self.stress_pnl))
        object.__setattr__(self, "historical_pnl", _freeze_historical_pnl(self.historical_pnl))

    @classmethod
    def from_parts(
        cls,
        trade_id: str,
        *,
        pv: float,
        delta: float = 0.0,
        gamma: float = 0.0,
        vega: float = 0.0,
        dv01: float = 0.0,
        fx_delta: float = 0.0,
        key_rate_dv01: Mapping[str, float] | None = None,
        stress_pnl: Mapping[str, float] | None = None,
        historical_pnl: Sequence[float] | None = None,
    ) -> TradeCalculationArtifact:
        """Build an artifact from explicit fields (preferred construction path)."""
        return cls(
            trade_id=trade_id,
            pv=pv,
            delta=delta,
            gamma=gamma,
            vega=vega,
            dv01=dv01,
            fx_delta=fx_delta,
            key_rate_dv01=key_rate_dv01 or {},
            stress_pnl=stress_pnl or {},
            historical_pnl=historical_pnl,
        )

    @classmethod
    def from_valuation(
        cls,
        valuation: Valuation,
        *,
        key_rate_dv01: Mapping[str, float] | None = None,
        stress_pnl: Mapping[str, float] | None = None,
        historical_pnl: Sequence[float] | None = None,
        trade_id: str | None = None,
    ) -> TradeCalculationArtifact:
        """Map a stable ``Valuation`` onto this artifact (no hierarchy import)."""
        return cls.from_parts(
            trade_id if trade_id is not None else valuation.position_id,
            pv=valuation.market_value,
            delta=valuation.delta,
            gamma=valuation.gamma,
            vega=valuation.vega,
            dv01=valuation.dv01,
            fx_delta=valuation.fx_delta,
            key_rate_dv01=key_rate_dv01,
            stress_pnl=stress_pnl,
            historical_pnl=historical_pnl,
        )

    def add(
        self,
        other: TradeCalculationArtifact,
        *,
        trade_id: str | None = None,
    ) -> TradeCalculationArtifact:
        """Sum additive measures and merge bucket/scenario vectors by key."""
        if not isinstance(other, TradeCalculationArtifact):
            raise TypeError(f"can only add TradeCalculationArtifact, got {type(other)!r}")
        result_id = self.trade_id if trade_id is None else trade_id
        return TradeCalculationArtifact.from_parts(
            result_id,
            pv=self.pv + other.pv,
            delta=self.delta + other.delta,
            gamma=self.gamma + other.gamma,
            vega=self.vega + other.vega,
            dv01=self.dv01 + other.dv01,
            fx_delta=self.fx_delta + other.fx_delta,
            key_rate_dv01=_merge_numeric_mapping(self.key_rate_dv01, other.key_rate_dv01),
            stress_pnl=_merge_stress(self.stress_pnl, other.stress_pnl),
            historical_pnl=_add_historical(self.historical_pnl, other.historical_pnl),
        )

    def __add__(self, other: Any) -> TradeCalculationArtifact:
        if not isinstance(other, TradeCalculationArtifact):
            return NotImplemented
        return self.add(other)
