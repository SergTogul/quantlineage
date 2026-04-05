"""Historical market dataset abstraction (M2.1) + demo file replay (M10.2).

Separates **historical factor observations** from scenario generation
(``app.risk.scenarios``, M2.2) and portfolio valuation / VaR aggregation
(`HistoricalRiskEngine`, `VaRAnalytics`, including M2.3 full revaluation).

Units (MVP aggregate factors — not tenor-specific key rates):
- equity / FX returns: relative (0.01 = +1%)
- vol moves: relative change of vol level (0.07 ≈ +7% of current vol)
- rate moves: parallel shifts in basis points (1.0 = +1bp)

M10.2 ships a **demo** CSV under ``data/demo_historical_factors.csv`` (synthetic
replay of ``SyntheticHistoricalDataset(seed=7, observations=750)`` — **no live
vendor feeds**). Load via ``load_demo_historical_dataset()`` or
``create_historical_dataset("demo")`` / env ``RISKFORGE_HISTORICAL_DATASET``.

R0.5.4: the shipped four-column demo/synthetic series is a **demo projection /
fixture** (``projection="four_macro_demo"``), not a per-name or per-tenor
historical factor panel. RF-005 stays open until that panel exists (R0.5.3).

This module does **not** depend on ``MarketSnapshot.key_rates`` or key-rate DV01
semantics (those remain open Critical M1 items).
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

type FloatArray = NDArray[np.floating]

DEMO_HISTORICAL_DATASET_ID = "demo-historical-factors"
DEMO_HISTORICAL_CSV_NAME = "demo_historical_factors.csv"
HISTORICAL_DATASET_ENV = "RISKFORGE_HISTORICAL_DATASET"

# MVP aggregate factor names matching FactorObservationSeries columns.
# Not per-name spots and not per-tenor key rates (R0.5.3 / RF-005).
MVP_AGGREGATE_FACTORS: tuple[str, ...] = ("equity", "vol", "rate", "fx")

_REQUIRED_CSV_COLUMNS = (
    "equity_return",
    "vol_move",
    "rate_move_bps",
    "fx_return",
)


class HistoricalDatasetProjection(StrEnum):
    """How a historical dataset maps onto the risk-factor space.

    ``four_macro_demo`` is the shipped MVP: four aggregate series
    (equity / vol / rate / fx). It is a demo projection / fixture, not a
    per-name or per-tenor historical factor panel (R0.5.3 / RF-005).
    """

    FOUR_MACRO_DEMO = "four_macro_demo"


FOUR_MACRO_DEMO_PROJECTION = HistoricalDatasetProjection.FOUR_MACRO_DEMO


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

    @property
    def aggregate_factors(self) -> tuple[str, ...]:
        """MVP aggregate factor names for the four series columns."""
        return MVP_AGGREGATE_FACTORS


class _FourMacroDemoLabels:
    """R0.5.4 label contract shared by shipped four-column datasets."""

    projection: HistoricalDatasetProjection

    @property
    def is_per_name_per_tenor_panel(self) -> bool:
        """False for ``four_macro_demo`` — R0.5.3 panel is not implemented."""
        return self.projection != HistoricalDatasetProjection.FOUR_MACRO_DEMO

    @property
    def aggregate_factors(self) -> tuple[str, ...]:
        return MVP_AGGREGATE_FACTORS


@runtime_checkable
class HistoricalMarketDataset(Protocol):
    """Source of historical factor observations for risk engines."""

    projection: HistoricalDatasetProjection

    def factor_observations(self) -> FactorObservationSeries:
        """Return aligned factor move series (deterministic for a given source)."""


@dataclass(frozen=True, slots=True)
class ArrayHistoricalDataset(_FourMacroDemoLabels):
    """Explicit observation arrays (tests, fixtures, future file loaders)."""

    series: FactorObservationSeries
    projection: HistoricalDatasetProjection = FOUR_MACRO_DEMO_PROJECTION

    def factor_observations(self) -> FactorObservationSeries:
        return self.series


@dataclass(frozen=True, slots=True)
class FileHistoricalDataset(_FourMacroDemoLabels):
    """Factor observations loaded from a CSV (demo / replay / fixtures)."""

    series: FactorObservationSeries
    dataset_id: str = "file"
    source_path: str | None = None
    projection: HistoricalDatasetProjection = FOUR_MACRO_DEMO_PROJECTION

    def factor_observations(self) -> FactorObservationSeries:
        return self.series


@dataclass(frozen=True, slots=True)
class SyntheticHistoricalDataset(_FourMacroDemoLabels):
    """Deterministic synthetic factor history (MVP stand-in for a market dataset).

    Distributions match the legacy inline RNG in ``HistoricalRiskEngine`` /
    ``VaRAnalytics`` so existing seeded risk results remain numerically stable.

    Labeled ``projection="four_macro_demo"``: four aggregate series, not a
    per-name / per-tenor panel.
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
    projection: HistoricalDatasetProjection = FOUR_MACRO_DEMO_PROJECTION

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


def _repo_root() -> Path:
    # backend/app/risk/historical_data.py → parents[3] = repo root
    return Path(__file__).resolve().parents[3]


def demo_historical_dataset_path() -> Path:
    """Path to the packaged M10.2 demo factor-return CSV (repo ``data/``)."""
    return _repo_root() / "data" / DEMO_HISTORICAL_CSV_NAME


def load_factor_observations_csv(path: str | Path) -> FactorObservationSeries:
    """Load aligned aggregate factor moves from a CSV.

    Required columns: ``equity_return``, ``vol_move``, ``rate_move_bps``,
    ``fx_return``. Optional ``date`` is ignored by the risk engines (kept for
    human replay / documentation).
    """
    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {csv_path}")
        fields = {name.strip() for name in reader.fieldnames}
        missing = [c for c in _REQUIRED_CSV_COLUMNS if c not in fields]
        if missing:
            raise ValueError(
                f"missing required column(s) {missing} in {csv_path}; "
                f"need {_REQUIRED_CSV_COLUMNS}"
            )
        equity: list[float] = []
        vol: list[float] = []
        rates: list[float] = []
        fx: list[float] = []
        for row in reader:
            equity.append(float(row["equity_return"]))
            vol.append(float(row["vol_move"]))
            rates.append(float(row["rate_move_bps"]))
            fx.append(float(row["fx_return"]))
    if not equity:
        raise ValueError(f"CSV has no data rows: {csv_path}")
    return FactorObservationSeries(
        equity_returns=np.asarray(equity, dtype=float),
        vol_moves=np.asarray(vol, dtype=float),
        rate_moves_bps=np.asarray(rates, dtype=float),
        fx_returns=np.asarray(fx, dtype=float),
    )


def load_csv_historical_dataset(
    path: str | Path,
    *,
    dataset_id: str = "file",
    projection: HistoricalDatasetProjection = FOUR_MACRO_DEMO_PROJECTION,
) -> FileHistoricalDataset:
    """Wrap ``load_factor_observations_csv`` as a ``HistoricalMarketDataset``.

    Four-column CSVs are the ``four_macro_demo`` projection unless a future
    loader supplies a different label (R0.5.3 panel is not implemented here).
    """
    csv_path = Path(path).resolve()
    return FileHistoricalDataset(
        series=load_factor_observations_csv(csv_path),
        dataset_id=dataset_id,
        source_path=str(csv_path),
        projection=projection,
    )


def load_demo_historical_dataset() -> FileHistoricalDataset:
    """Load the packaged demo historical factor dataset (M10.2).

    Returns a ``FileHistoricalDataset`` labeled
    ``projection="four_macro_demo"`` — a fixture, not a per-name / per-tenor
    panel.

    Usage::

        from app.risk.historical_data import load_demo_historical_dataset
        from app.risk.historical import HistoricalRiskEngine

        engine = HistoricalRiskEngine(dataset=load_demo_historical_dataset())
    """
    path = demo_historical_dataset_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"demo historical dataset not found at {path}; "
            "expected repo data/demo_historical_factors.csv"
        )
    return load_csv_historical_dataset(
        path,
        dataset_id=DEMO_HISTORICAL_DATASET_ID,
        projection=FOUR_MACRO_DEMO_PROJECTION,
    )


def create_historical_dataset(
    source: str | None = None,
    *,
    seed: int = 7,
    observations: int = 750,
) -> HistoricalMarketDataset:
    """Resolve a historical factor source for risk engines / API DI.

    ``source`` (or env ``RISKFORGE_HISTORICAL_DATASET``) may be:

    - ``demo`` (factory default) — packaged ``data/demo_historical_factors.csv``
    - ``synthetic`` — seeded RNG (``SyntheticHistoricalDataset``)
    - path to a ``.csv`` file with the required factor columns

    ``HistoricalRiskEngine()`` with ``dataset=None`` still defaults to
    ``SyntheticHistoricalDataset`` for backward-compatible ctor behavior.

    Demo and synthetic sources are labeled ``projection="four_macro_demo"``.
    """
    raw = source if source is not None else os.getenv(HISTORICAL_DATASET_ENV, "demo")
    resolved = (raw or "demo").strip()
    key = resolved.lower()
    if key in {"demo", "demo-historical", DEMO_HISTORICAL_DATASET_ID}:
        return load_demo_historical_dataset()
    if key in {"synthetic", "rng", "random"}:
        return SyntheticHistoricalDataset(seed=seed, observations=observations)
    path = Path(resolved).expanduser()
    if path.suffix.lower() == ".csv" or path.is_file():
        return load_csv_historical_dataset(path)
    raise ValueError(
        f"Unknown historical dataset source: {resolved!r}; "
        f"use 'demo', 'synthetic', or a path to a factor CSV"
    )


__all__ = [
    "DEMO_HISTORICAL_CSV_NAME",
    "DEMO_HISTORICAL_DATASET_ID",
    "FOUR_MACRO_DEMO_PROJECTION",
    "HISTORICAL_DATASET_ENV",
    "MVP_AGGREGATE_FACTORS",
    "ArrayHistoricalDataset",
    "FactorObservationSeries",
    "FileHistoricalDataset",
    "HistoricalDatasetProjection",
    "HistoricalMarketDataset",
    "SyntheticHistoricalDataset",
    "create_historical_dataset",
    "demo_historical_dataset_path",
    "load_csv_historical_dataset",
    "load_demo_historical_dataset",
    "load_factor_observations_csv",
]
