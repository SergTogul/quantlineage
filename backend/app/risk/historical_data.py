"""Historical market dataset abstraction (M2.1) + demo file replay (M10.2 / 10.1).

Separates **historical factor observations** from scenario generation
(``app.risk.scenarios``, M2.2) and portfolio valuation / VaR aggregation
(`HistoricalRiskEngine`, `VaRAnalytics`, including M2.3 full revaluation).

Units:
- EquitySpot / FXSpot: relative return (0.01 = +1%)
- EquityVol / FXVol: relative change of vol level
- RateZero: basis points (1.0 = +1bp)

Production demo default is the per-factor synthetic replay
``data/demo_multi_factor_history.csv`` (``projection="per_factor"``,
id ``demo-multi-factor-history`` / ``v1``). **No live vendor feeds.**

The four-column CSV ``data/demo_historical_factors.csv`` remains a labeled
``four_macro_demo`` fixture (``create_historical_dataset("demo")`` /
``load_demo_historical_dataset()`` / ``factor_panel=None``). It is not the
production factory default.

This module does **not** depend on ``MarketSnapshot.key_rates`` or key-rate DV01
semantics (those remain open Critical M1 items).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

type FloatArray = NDArray[np.floating]

DEMO_HISTORICAL_DATASET_ID = "demo-historical-factors"
DEMO_HISTORICAL_CSV_NAME = "demo_historical_factors.csv"
DEMO_MULTI_FACTOR_DATASET_ID = "demo-multi-factor-history"
DEMO_MULTI_FACTOR_CSV_NAME = "demo_multi_factor_history.csv"
DEMO_MULTI_FACTOR_DATASET_VERSION = "v1"
HISTORICAL_DATASET_ENV = "RISKFORGE_HISTORICAL_DATASET"
DEFAULT_HISTORICAL_DATASET_SOURCE = DEMO_MULTI_FACTOR_DATASET_ID

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

    ``four_macro_demo`` is the labeled four-column fixture (equity / vol / rate / fx).
    ``per_factor`` is the production demo panel: one independent series per typed
    ``RiskFactor`` (no family-wide broadcast).
    """

    FOUR_MACRO_DEMO = "four_macro_demo"
    PER_FACTOR = "per_factor"


FOUR_MACRO_DEMO_PROJECTION = HistoricalDatasetProjection.FOUR_MACRO_DEMO
PER_FACTOR_PROJECTION = HistoricalDatasetProjection.PER_FACTOR

_PER_FACTOR_COLUMN_PREFIXES = (
    "EquitySpot:",
    "EquityVol:",
    "RateZero:",
    "FXSpot:",
    "FXVol:",
)


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
        """False for ``four_macro_demo`` — aggregate projection, not a per-factor panel."""
        return self.projection != HistoricalDatasetProjection.FOUR_MACRO_DEMO

    @property
    def aggregate_factors(self) -> tuple[str, ...]:
        return MVP_AGGREGATE_FACTORS


@runtime_checkable
class HistoricalMarketDataset(Protocol):
    """Source of historical factor observations for risk engines."""

    @property
    def projection(self) -> HistoricalDatasetProjection: ...

    def factor_observations(self) -> FactorObservationSeries:
        """Return aligned factor move series (deterministic for a given source)."""


@dataclass(frozen=True, slots=True)
class ArrayHistoricalDataset(_FourMacroDemoLabels):
    """Explicit observation arrays (tests, fixtures, future file loaders)."""

    series: FactorObservationSeries
    projection: HistoricalDatasetProjection = FOUR_MACRO_DEMO_PROJECTION

    def factor_observations(self) -> FactorObservationSeries:
        return self.series


def file_csv_dataset_id(path: str | Path) -> str:
    """Canonical identity for a CSV-backed historical dataset.

    Demo / synthetic aliases stay as named constants; arbitrary CSVs use
    ``file:`` + resolved absolute path so distinct paths never collapse to
    the same id (R0.8.4).
    """
    return f"file:{Path(path).expanduser().resolve()}"


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
class PerFactorFileHistoricalDataset:
    """Checked-in per-factor history: one independent series per typed column.

    ``projection="per_factor"``. Dates come from the file. This is synthetic
    demo replay, not observed market data. Four-macro ``factor_observations()``
    is unavailable (fail closed) — use ``factor_panel_from_dataset``.
    """

    dates: tuple[date, ...]
    columns: Mapping[str, FloatArray]
    dataset_id: str
    source_path: str | None = None
    dataset_version: str = DEMO_MULTI_FACTOR_DATASET_VERSION
    projection: HistoricalDatasetProjection = PER_FACTOR_PROJECTION

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", MappingProxyType(dict(self.columns)))
        if not self.dates or not self.columns:
            raise ValueError("per-factor dataset requires dates and at least one factor column")
        n = len(self.dates)
        for name, series in self.columns.items():
            if len(series) != n:
                raise ValueError(f"{name} length {len(series)} != dates length {n}")
        if self.projection != PER_FACTOR_PROJECTION:
            raise ValueError("PerFactorFileHistoricalDataset projection must be per_factor")

    @property
    def is_per_name_per_tenor_panel(self) -> bool:
        return True

    @property
    def n_observations(self) -> int:
        return len(self.dates)

    def factor_observations(self) -> FactorObservationSeries:
        raise ValueError(
            "per-factor dataset has no four-macro factor_observations(); "
            "use factor_panel_from_dataset"
        )


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
    """Path to the packaged four-macro demo factor-return CSV (repo ``data/``)."""
    return _repo_root() / "data" / DEMO_HISTORICAL_CSV_NAME


def demo_multi_factor_dataset_path() -> Path:
    """Path to the packaged per-factor demo history CSV (repo ``data/``)."""
    return _repo_root() / "data" / DEMO_MULTI_FACTOR_CSV_NAME


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


def load_per_factor_observations_csv(
    path: str | Path,
) -> tuple[tuple[date, ...], dict[str, FloatArray]]:
    """Load a wide per-factor CSV: ``date`` plus typed ``EquitySpot:AAPL`` columns.

    Dates come from the file. Column ids must parse as typed risk factors.
    Synthetic demo replay only — not observed market data.
    """
    from app.risk.factor_types import parse_factor_column_id

    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {csv_path}")
        fields = [name.strip() for name in reader.fieldnames if name and name.strip()]
        if "date" not in fields:
            raise ValueError(f"per-factor CSV missing date column in {csv_path}")
        factor_names = [name for name in fields if name != "date"]
        if not factor_names:
            raise ValueError(f"per-factor CSV has no factor columns in {csv_path}")
        for name in factor_names:
            parse_factor_column_id(name)
        dates: list[date] = []
        series: dict[str, list[float]] = {name: [] for name in factor_names}
        for row in reader:
            dates.append(date.fromisoformat(str(row["date"]).strip()))
            for name in factor_names:
                series[name].append(float(row[name]))
    if not dates:
        raise ValueError(f"CSV has no data rows: {csv_path}")
    return tuple(dates), {name: np.asarray(values, dtype=float) for name, values in series.items()}


def load_per_factor_csv_dataset(
    path: str | Path,
    *,
    dataset_id: str | None = None,
    dataset_version: str = DEMO_MULTI_FACTOR_DATASET_VERSION,
) -> PerFactorFileHistoricalDataset:
    """Load a wide per-factor CSV as ``projection="per_factor"``."""
    from app.market.history.artifact import sidecar_identity

    csv_path = Path(path).expanduser().resolve()
    if not csv_path.is_file():
        raise ValueError(f"historical dataset CSV not found: {csv_path}")
    dates, columns = load_per_factor_observations_csv(csv_path)
    sidecar_id, sidecar_version = sidecar_identity(csv_path)
    if dataset_id is None or dataset_id == "file":
        resolved_id = sidecar_id or file_csv_dataset_id(csv_path)
    else:
        resolved_id = dataset_id
    resolved_version = sidecar_version or dataset_version
    return PerFactorFileHistoricalDataset(
        dates=dates,
        columns=columns,
        dataset_id=resolved_id,
        source_path=str(csv_path),
        dataset_version=resolved_version,
        projection=PER_FACTOR_PROJECTION,
    )


def _csv_header_fields(csv_path: Path) -> list[str]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {csv_path}")
        return [name.strip() for name in reader.fieldnames if name and name.strip()]


def _header_is_four_macro(fields: list[str]) -> bool:
    present = set(fields)
    return all(col in present for col in _REQUIRED_CSV_COLUMNS)


def _header_is_per_factor(fields: list[str]) -> bool:
    return any(
        any(name.startswith(prefix) for prefix in _PER_FACTOR_COLUMN_PREFIXES) for name in fields
    )


def load_csv_historical_dataset(
    path: str | Path,
    *,
    dataset_id: str | None = None,
    projection: HistoricalDatasetProjection | None = None,
) -> FileHistoricalDataset | PerFactorFileHistoricalDataset:
    """Load a factor CSV as four-macro or per-factor depending on headers / label.

    Four-column CSVs stay ``four_macro_demo`` (family broadcast when mapped to a
    panel). Wide typed-column CSVs are ``per_factor`` (1:1 mapping, no broadcast).
    """
    csv_path = Path(path).expanduser().resolve()
    if not csv_path.is_file():
        raise ValueError(f"historical dataset CSV not found: {csv_path}")
    fields = _csv_header_fields(csv_path)
    if projection is None:
        if _header_is_four_macro(fields):
            projection = FOUR_MACRO_DEMO_PROJECTION
        elif _header_is_per_factor(fields):
            projection = PER_FACTOR_PROJECTION
        else:
            raise ValueError(
                f"unrecognized historical CSV columns in {csv_path}; "
                f"need four-macro {_REQUIRED_CSV_COLUMNS} or typed factor columns"
            )
    if projection == PER_FACTOR_PROJECTION:
        return load_per_factor_csv_dataset(csv_path, dataset_id=dataset_id)
    if dataset_id is None or dataset_id == "file":
        resolved_id = file_csv_dataset_id(csv_path)
    else:
        resolved_id = dataset_id
    return FileHistoricalDataset(
        series=load_factor_observations_csv(csv_path),
        dataset_id=resolved_id,
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
    dataset = load_csv_historical_dataset(
        path,
        dataset_id=DEMO_HISTORICAL_DATASET_ID,
        projection=FOUR_MACRO_DEMO_PROJECTION,
    )
    if not isinstance(dataset, FileHistoricalDataset):
        raise TypeError(
            f"demo four-macro CSV must load as FileHistoricalDataset, got {type(dataset).__name__}"
        )
    return dataset


def load_demo_multi_factor_dataset() -> PerFactorFileHistoricalDataset:
    """Load the packaged per-factor demo history (Stage 10.1).

    Synthetic SeedSequence replay frozen in git — **not** observed market data.
    """
    path = demo_multi_factor_dataset_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"demo multi-factor dataset not found at {path}; "
            "expected repo data/demo_multi_factor_history.csv"
        )
    return load_per_factor_csv_dataset(
        path,
        dataset_id=DEMO_MULTI_FACTOR_DATASET_ID,
        dataset_version=DEMO_MULTI_FACTOR_DATASET_VERSION,
    )


def create_historical_dataset(
    source: str | None = None,
    *,
    seed: int = 7,
    observations: int = 750,
) -> HistoricalMarketDataset:
    """Resolve a historical factor source for risk engines / API DI.

    ``source`` (or env ``RISKFORGE_HISTORICAL_DATASET``) may be:

    - unset / ``demo-multi-factor-history`` — packaged per-factor demo panel
    - ``demo`` / ``demo-historical-factors`` — labeled four-macro fixture CSV
    - ``synthetic`` — seeded four-macro RNG (``SyntheticHistoricalDataset``)
    - ``real:public:wave-a`` — frozen public CSV (env ``QUANTLINEAGE_PUBLIC_HISTORY_CSV``)
    - path to a ``.csv`` file (four-macro or per-factor headers)

    When ``source`` and ``RISKFORGE_HISTORICAL_DATASET`` are unset,
    ``QUANTLINEAGE_DATA_MODE=public`` selects ``real:public:wave-a`` (fails closed
    if the CSV is missing). Unset / ``synthetic`` keeps the demo panel.

    ``HistoricalRiskEngine()`` with ``dataset=None`` still defaults to
    ``SyntheticHistoricalDataset`` for backward-compatible ctor behavior.
    Default ``create_historical_dataset()`` stays the demo panel; public history
    is opt-in by id or ``QUANTLINEAGE_DATA_MODE=public`` and never fetches HTTP.
    """
    from app.market.history.data_mode import apply_quantlineage_data_mode

    default = DEFAULT_HISTORICAL_DATASET_SOURCE
    selected = apply_quantlineage_data_mode(source)
    resolved = (selected or default).strip()
    key = resolved.lower()
    if key in {
        DEMO_MULTI_FACTOR_DATASET_ID,
        "demo-multi-factor",
        "per_factor",
        "per-factor",
    }:
        return load_demo_multi_factor_dataset()
    if key in {"demo", "demo-historical", DEMO_HISTORICAL_DATASET_ID}:
        return load_demo_historical_dataset()
    if key in {"synthetic", "rng", "random"}:
        return SyntheticHistoricalDataset(seed=seed, observations=observations)
    from app.market.history.artifact import resolve_public_history_csv
    from app.market.history.spec import WAVE_A_DATASET_ID

    if resolved == WAVE_A_DATASET_ID or key == WAVE_A_DATASET_ID:
        csv_path = resolve_public_history_csv()
        return load_per_factor_csv_dataset(csv_path, dataset_id=WAVE_A_DATASET_ID)
    path = Path(resolved).expanduser()
    if resolved.startswith("file:"):
        path = Path(resolved[len("file:") :]).expanduser()
    if path.suffix.lower() == ".csv" or path.is_file():
        if not path.is_file():
            raise ValueError(f"historical dataset CSV not found: {path}")
        return load_csv_historical_dataset(path)
    raise ValueError(
        f"Unknown historical dataset source: {resolved!r}; "
        f"use {DEMO_MULTI_FACTOR_DATASET_ID!r}, 'demo', 'synthetic', "
        f"{WAVE_A_DATASET_ID!r}, or a path to a factor CSV"
    )


__all__ = [
    "DEFAULT_HISTORICAL_DATASET_SOURCE",
    "DEMO_HISTORICAL_CSV_NAME",
    "DEMO_HISTORICAL_DATASET_ID",
    "DEMO_MULTI_FACTOR_CSV_NAME",
    "DEMO_MULTI_FACTOR_DATASET_ID",
    "DEMO_MULTI_FACTOR_DATASET_VERSION",
    "FOUR_MACRO_DEMO_PROJECTION",
    "HISTORICAL_DATASET_ENV",
    "MVP_AGGREGATE_FACTORS",
    "PER_FACTOR_PROJECTION",
    "ArrayHistoricalDataset",
    "FactorObservationSeries",
    "FileHistoricalDataset",
    "HistoricalDatasetProjection",
    "HistoricalMarketDataset",
    "PerFactorFileHistoricalDataset",
    "SyntheticHistoricalDataset",
    "create_historical_dataset",
    "demo_historical_dataset_path",
    "demo_multi_factor_dataset_path",
    "file_csv_dataset_id",
    "load_csv_historical_dataset",
    "load_demo_historical_dataset",
    "load_demo_multi_factor_dataset",
    "load_factor_observations_csv",
    "load_per_factor_csv_dataset",
    "load_per_factor_observations_csv",
]
