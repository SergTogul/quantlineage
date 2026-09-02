"""Historical market dataset abstraction (M2.1).

Separates **historical factor observations** from scenario generation
(``app.risk.scenarios``, M2.2) and portfolio valuation / VaR aggregation
(`HistoricalRiskEngine`, `VaRAnalytics`, including M2.3 full revaluation).

Units (MVP aggregate factors — not tenor-specific key rates):
- equity / FX returns: relative (0.01 = +1%)
- vol moves: relative change of vol level (0.07 ≈ +7% of current vol)
- rate moves: parallel shifts in basis points (1.0 = +1bp)

This module does **not** depend on ``MarketSnapshot.key_rates`` or key-rate DV01
semantics (those remain open Critical M1 items).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

type FloatArray = NDArray[np.floating]


@dataclass(frozen=True, slots=True)
class FactorObservationSeries:
    """Aligned historical factor moves (one row per observation date).

    All arrays must share the same length. Columns are aggregate risk factors
    matching the MVP delta-gamma VaR approximation — not per-tenor key rates.
    """

    equity_returns: FloatArray
    vol_moves: FloatArray
    rate_moves_bps: FloatArray
    fx_returns: FloatArray

    def __post_init__(self) -> None:
        n = len(self.equity_returns)
        for name in ("vol_moves", "rate_moves_bps", "fx_returns"):
            arr = getattr(self, name)
            if len(arr) != n:
                raise ValueError(f"{name} length {len(arr)} != equity_returns length {n}")
        if n == 0:
            raise ValueError("FactorObservationSeries requires at least one observation")

    @property
    def n_observations(self) -> int:
        return int(len(self.equity_returns))


@runtime_checkable
class HistoricalMarketDataset(Protocol):
    """Source of historical factor observations for risk engines."""

    def factor_observations(self) -> FactorObservationSeries:
        """Return aligned factor move series (deterministic for a given source)."""


@dataclass(frozen=True, slots=True)
class ArrayHistoricalDataset:
    """Explicit observation arrays (tests, fixtures, future file loaders)."""

    series: FactorObservationSeries

    def factor_observations(self) -> FactorObservationSeries:
        return self.series


@dataclass(frozen=True, slots=True)
class SyntheticHistoricalDataset:
    """Deterministic synthetic factor history (MVP stand-in for a market dataset).

    Distributions match the legacy inline RNG in ``HistoricalRiskEngine`` /
    ``VaRAnalytics`` so existing seeded risk results remain numerically stable.
    """

    seed: int = 7
    observations: int = 750
    equity_mean: float = 0.0002
    equity_std: float = 0.013
    vol_mean: float = 0.0
    vol_std: float = 0.07
    rate_bps_mean: float = 0.0
    rate_bps_std: float = 7.0
    fx_mean: float = 0.0
    fx_std: float = 0.006

    def factor_observations(self) -> FactorObservationSeries:
        if self.observations < 1:
            raise ValueError("observations must be >= 1")
        rng = np.random.default_rng(self.seed)
        return FactorObservationSeries(
            equity_returns=rng.normal(self.equity_mean, self.equity_std, self.observations),
            vol_moves=rng.normal(self.vol_mean, self.vol_std, self.observations),
            rate_moves_bps=rng.normal(self.rate_bps_mean, self.rate_bps_std, self.observations),
            fx_returns=rng.normal(self.fx_mean, self.fx_std, self.observations),
        )


__all__ = [
    "ArrayHistoricalDataset",
    "FactorObservationSeries",
    "HistoricalMarketDataset",
    "SyntheticHistoricalDataset",
]
