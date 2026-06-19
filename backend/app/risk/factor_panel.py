"""Typed per-factor historical observation panel (R0.5.3 / RF-005 leftover).

Contract::

    date
    RiskFactor -> observation/change

This is the real panel type. One observation can hold per-name equity spots
and per-tenor rate zeros with independent numeric moves. It is **not** the
four-macro demo projection (``projection != "four_macro_demo"``) and
``is_per_name_per_tenor_panel`` is True.

Production API/worker wiring (``build_historical_risk_engine``) builds the
panel from the selected historical dataset via :func:`factor_panel_from_dataset`.
Bare ``HistoricalRiskEngine()`` / explicit ``factor_panel=None`` still uses the
labeled ``four_macro_demo`` dataset path. File four-macro CSVs still broadcast
onto typed factor families **only when** ``projection="four_macro_demo"``.
The production demo dataset is ``projection="per_factor"`` with a 1:1 column
map and ``is_per_name_per_tenor_panel is True``.

Units (match ``historical_data.py`` / ``FactorObservationSeries``):

- ``EquitySpot`` / ``FXSpot``: relative return (0.01 = +1%)
- ``EquityVol`` / ``FXVol``: relative change of vol level
- ``RateZero``: basis points (1.0 = +1bp)

Identity: a row is keyed by the full typed ``RiskFactor`` (via
``factor_sort_key``), not ``RiskFactor.key`` alone. ``RateZero.key`` is
currency-only (``USD:RATE``), so USD 2Y and USD 10Y are distinct columns.

Fail closed: empty panel / empty row, duplicate factor identity in one row,
mismatched date/row/column lengths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from app.risk.factor_types import (
    EquitySpot,
    EquityVol,
    FXSpot,
    FXVol,
    RateZero,
    RiskFactor,
    factor_sort_key,
    parse_factor_column_id,
)
from app.risk.historical_data import (
    FactorObservationSeries,
    PerFactorFileHistoricalDataset,
    SyntheticHistoricalDataset,
)

PER_FACTOR_PANEL_PROJECTION = "per_factor"

EQUITY_CHANGE_UNIT = "relative_return"
RATE_CHANGE_UNIT = "basis_points"
VOL_CHANGE_UNIT = "relative_vol"
FX_CHANGE_UNIT = "relative_return"

# Documented default universe for the production demo panel.
# Independent RNG streams per column — never a silent broadcast of one equity
# or one rate series onto every name/tenor. Includes SPY and USD 0Y so existing
# demo books (index / IR future) fail-closed-cover rather than missing a factor.
DEFAULT_PRODUCTION_PANEL_FACTORS: tuple[RiskFactor, ...] = (
    EquitySpot("AAPL"),
    EquitySpot("MSFT"),
    EquitySpot("NVDA"),
    EquitySpot("SPY"),
    EquityVol(underlying="AAPL"),
    EquityVol(underlying="MSFT"),
    EquityVol(underlying="NVDA"),
    EquityVol(underlying="SPY"),
    RateZero("USD", "0Y"),
    RateZero("USD", "2Y"),
    RateZero("USD", "5Y"),
    RateZero("USD", "10Y"),
    FXSpot("EURUSD"),
    FXVol(pair="EURUSD"),
)

# Match SyntheticHistoricalDataset distribution knobs (per factor family).
_EQUITY_MEAN = 0.0002
_EQUITY_STD = 0.013
_VOL_MEAN = 0.0
_VOL_STD = 0.07
_RATE_BPS_MEAN = 0.0
_RATE_BPS_STD = 7.0
_FX_MEAN = 0.0
_FX_STD = 0.006

_UNIT_BY_TYPE: dict[type, str] = {
    EquitySpot: EQUITY_CHANGE_UNIT,
    FXSpot: FX_CHANGE_UNIT,
    EquityVol: VOL_CHANGE_UNIT,
    FXVol: VOL_CHANGE_UNIT,
    RateZero: RATE_CHANGE_UNIT,
}

_DIST_BY_TYPE: dict[type, tuple[float, float]] = {
    EquitySpot: (_EQUITY_MEAN, _EQUITY_STD),
    EquityVol: (_VOL_MEAN, _VOL_STD),
    RateZero: (_RATE_BPS_MEAN, _RATE_BPS_STD),
    FXSpot: (_FX_MEAN, _FX_STD),
    FXVol: (_VOL_MEAN, _VOL_STD),
}


def change_unit(factor: RiskFactor) -> str:
    """Documented change unit for a typed factor (historical_data conventions)."""
    try:
        return _UNIT_BY_TYPE[type(factor)]
    except KeyError:
        raise TypeError(f"unsupported risk factor type: {type(factor)!r}") from None


def panel_factor_identity(factor: RiskFactor) -> tuple[str, str, str]:
    """Stable panel column identity.

    Equals ``factor_sort_key`` so two ``RateZero`` values that share
    ``key == "USD:RATE"`` remain distinct by tenor (``bucket``).
    """
    return factor_sort_key(factor)


def _pairs_to_changes(
    pairs: Sequence[tuple[RiskFactor, float]],
) -> dict[RiskFactor, float]:
    if not pairs:
        raise ValueError("empty factor observation: at least one factor change is required")
    seen: set[tuple[str, str, str]] = set()
    changes: dict[RiskFactor, float] = {}
    for factor, amount in pairs:
        identity = panel_factor_identity(factor)
        if identity in seen:
            raise ValueError(f"duplicate factor key in observation: {identity}")
        seen.add(identity)
        changes[factor] = float(amount)
    return changes


@dataclass(frozen=True, slots=True)
class FactorPanelObservation:
    """One date's typed factor changes.

    Units: equity/FX relative returns; rate moves in basis points; vol relative.
    """

    as_of: date
    changes: Mapping[RiskFactor, float]

    @classmethod
    def from_pairs(
        cls,
        as_of: date,
        pairs: Sequence[tuple[RiskFactor, float]],
    ) -> FactorPanelObservation:
        return cls(as_of=as_of, changes=MappingProxyType(_pairs_to_changes(pairs)))

    def change(self, factor: RiskFactor) -> float:
        try:
            return self.changes[factor]
        except KeyError:
            identity = panel_factor_identity(factor)
            for stored, amount in self.changes.items():
                if panel_factor_identity(stored) == identity:
                    return amount
            raise KeyError(f"factor not in observation: {identity}") from None

    @property
    def factors(self) -> tuple[RiskFactor, ...]:
        return tuple(self.changes.keys())


@dataclass(frozen=True, slots=True)
class HistoricalFactorPanel:
    """Aligned date × RiskFactor observation panel.

    ``projection`` is ``per_factor``, never ``four_macro_demo``.
    """

    dates: tuple[date, ...]
    factors: tuple[RiskFactor, ...]
    observations: tuple[FactorPanelObservation, ...]
    projection: str = PER_FACTOR_PANEL_PROJECTION

    def __post_init__(self) -> None:
        if not self.dates or not self.factors or not self.observations:
            raise ValueError("empty factor panel: dates, factors, and observations are required")
        if self.projection == "four_macro_demo":
            raise ValueError("HistoricalFactorPanel projection must not be four_macro_demo")
        n_dates = len(self.dates)
        n_factors = len(self.factors)
        if len(self.observations) != n_dates:
            raise ValueError(
                f"observations length {len(self.observations)} != dates length {n_dates}"
            )
        identities = [panel_factor_identity(f) for f in self.factors]
        if len(set(identities)) != n_factors:
            raise ValueError("duplicate factor key in panel columns")
        expected = set(identities)
        for as_of, obs in zip(self.dates, self.observations, strict=True):
            if obs.as_of != as_of:
                raise ValueError(f"observation date {obs.as_of} != panel date {as_of}")
            row_ids = {panel_factor_identity(f) for f in obs.factors}
            if len(obs.factors) != n_factors or row_ids != expected:
                raise ValueError(
                    f"observation on {as_of} length {len(obs.factors)} "
                    f"!= panel factor length {n_factors}"
                )

    @property
    def is_per_name_per_tenor_panel(self) -> bool:
        return True

    @property
    def n_observations(self) -> int:
        return len(self.dates)

    def observation_on(self, as_of: date) -> FactorPanelObservation:
        for obs in self.observations:
            if obs.as_of == as_of:
                return obs
        raise KeyError(f"no observation on {as_of}")

    def change(self, as_of: date, factor: RiskFactor) -> float:
        return self.observation_on(as_of).change(factor)

    @classmethod
    def from_pairs(
        cls,
        dates: Sequence[date],
        rows: Sequence[Sequence[tuple[RiskFactor, float]]],
    ) -> HistoricalFactorPanel:
        if len(dates) != len(rows):
            raise ValueError(
                f"dates length {len(dates)} != rows length {len(rows)}"
            )
        if not dates:
            raise ValueError("empty factor panel: at least one observation is required")
        observations = tuple(
            FactorPanelObservation.from_pairs(as_of, row)
            for as_of, row in zip(dates, rows, strict=True)
        )
        widths = {len(obs.factors) for obs in observations}
        if len(widths) != 1:
            raise ValueError(
                f"mismatched row lengths: {sorted(len(obs.factors) for obs in observations)}"
            )
        return cls(
            dates=tuple(dates),
            factors=observations[0].factors,
            observations=observations,
        )

    @classmethod
    def from_columns(
        cls,
        dates: Sequence[date],
        changes: Mapping[RiskFactor, Sequence[float]],
    ) -> HistoricalFactorPanel:
        if not dates or not changes:
            raise ValueError("empty factor panel: dates and factor columns are required")
        n = len(dates)
        factors = tuple(changes.keys())
        for factor, series in changes.items():
            if len(series) != n:
                raise ValueError(
                    f"{factor!r} length {len(series)} != dates length {n}"
                )
        rows = [
            [(factor, float(changes[factor][i])) for factor in factors]
            for i in range(n)
        ]
        return cls.from_pairs(dates, rows)


def _distribution_for(factor: RiskFactor) -> tuple[float, float]:
    try:
        return _DIST_BY_TYPE[type(factor)]
    except KeyError:
        raise TypeError(f"unsupported risk factor type: {type(factor)!r}") from None


def create_synthetic_factor_panel(
    *,
    seed: int = 7,
    observations: int = 750,
    factors: Sequence[RiskFactor] | None = None,
    start: date = date(2022, 1, 3),
) -> HistoricalFactorPanel:
    """Build a deterministic per-factor panel with independent column streams.

    Each factor gets its own RNG child of ``SeedSequence(seed)`` so two equities
    or two rate tenors are not copies of one series. Columns default to
    :data:`DEFAULT_PRODUCTION_PANEL_FACTORS` (AAPL/MSFT/NVDA/SPY, USD tenors, EURUSD).

    This is synthetic stand-in history — not a live market-data vendor feed.
    """
    if observations < 1:
        raise ValueError("observations must be >= 1")
    column_factors = tuple(factors) if factors is not None else DEFAULT_PRODUCTION_PANEL_FACTORS
    if not column_factors:
        raise ValueError("empty factor panel: at least one factor column is required")
    # Independent streams: spawn one child seed per column (not a shared draw).
    child_seeds = np.random.SeedSequence(seed).spawn(len(column_factors))
    changes: dict[RiskFactor, list[float]] = {}
    for factor, child in zip(column_factors, child_seeds, strict=True):
        mean, std = _distribution_for(factor)
        rng = np.random.default_rng(child)
        changes[factor] = rng.normal(mean, std, observations).tolist()
    dates = tuple(start + timedelta(days=i) for i in range(observations))
    return HistoricalFactorPanel.from_columns(dates, changes)


def truncate_factor_panel(
    panel: HistoricalFactorPanel,
    observations: int,
) -> HistoricalFactorPanel:
    """Keep the first ``observations`` dates of an existing panel."""
    if observations < 1:
        raise ValueError("observations must be >= 1")
    if observations > panel.n_observations:
        raise ValueError(
            f"observations {observations} exceeds panel length {panel.n_observations}"
        )
    if observations == panel.n_observations:
        return panel
    return HistoricalFactorPanel.from_pairs(
        dates=panel.dates[:observations],
        rows=[
            [(factor, obs.change(factor)) for factor in panel.factors]
            for obs in panel.observations[:observations]
        ],
    )


def _series_for_factor(factor: RiskFactor, series: FactorObservationSeries) -> np.ndarray:
    if isinstance(factor, EquitySpot):
        return series.equity_returns
    if isinstance(factor, (EquityVol, FXVol)):
        return series.vol_moves
    if isinstance(factor, RateZero):
        return series.rate_moves_bps
    if isinstance(factor, FXSpot):
        return series.fx_returns
    raise TypeError(f"unsupported risk factor type: {type(factor)!r}")


def _panel_from_per_factor_dataset(
    dataset: PerFactorFileHistoricalDataset,
    *,
    factors: Sequence[RiskFactor] | None,
    observations: int | None,
) -> HistoricalFactorPanel:
    """Map CSV columns onto typed factors 1:1. Dates come from the file."""
    parsed: dict[RiskFactor, Sequence[float]] = {}
    for name, series in dataset.columns.items():
        parsed[parse_factor_column_id(name)] = series
    if factors is None:
        column_factors = tuple(parsed.keys())
    else:
        column_factors = tuple(factors)
        available = {panel_factor_identity(f) for f in parsed}
        missing = [
            factor
            for factor in column_factors
            if panel_factor_identity(factor) not in available
        ]
        if missing:
            identities = ", ".join(str(panel_factor_identity(f)) for f in missing)
            raise ValueError(f"panel missing required factor(s): {identities}")
    if not column_factors:
        raise ValueError("empty factor panel: at least one factor column is required")
    source_len = dataset.n_observations
    if observations is None:
        n = source_len
    else:
        if observations < 1:
            raise ValueError("observations must be >= 1")
        if observations > source_len:
            raise ValueError(
                f"observations {observations} exceeds historical dataset length {source_len}"
            )
        n = observations
    by_id = {panel_factor_identity(f): (f, parsed[f]) for f in parsed}
    changes: dict[RiskFactor, Sequence[float]] = {}
    for factor in column_factors:
        stored, series = by_id[panel_factor_identity(factor)]
        changes[stored] = series[:n]
    return HistoricalFactorPanel.from_columns(dataset.dates[:n], changes)


def factor_panel_from_dataset(
    dataset: object,
    *,
    factors: Sequence[RiskFactor] | None = None,
    observations: int | None = None,
    seed: int | None = None,
) -> HistoricalFactorPanel:
    """Build a typed panel owned by ``dataset`` (per-factor 1:1 vs four-macro map).

    ``SyntheticHistoricalDataset`` keeps independent per-name / per-tenor RNG
    streams. File datasets with ``projection="per_factor"`` map CSV columns
    onto typed ``RiskFactor``s 1:1 using the file calendar. File / array
    four-macro sources broadcast each of the four CSV columns onto every typed
    factor of that family **only when** ``projection="four_macro_demo"``.
    ``observations`` smaller than the source truncates; larger than a file
    source raises (no invented rows).
    """
    if isinstance(dataset, PerFactorFileHistoricalDataset):
        return _panel_from_per_factor_dataset(
            dataset, factors=factors, observations=observations
        )
    column_factors = tuple(factors) if factors is not None else DEFAULT_PRODUCTION_PANEL_FACTORS
    if isinstance(dataset, SyntheticHistoricalDataset):
        obs = dataset.observations if observations is None else observations
        panel_seed = dataset.seed if seed is None else seed
        return create_synthetic_factor_panel(
            seed=panel_seed,
            observations=obs,
            factors=column_factors,
        )

    series = dataset.factor_observations()  # type: ignore[attr-defined]
    source_len = int(series.n_observations)
    if observations is None:
        n = source_len
    else:
        if observations < 1:
            raise ValueError("observations must be >= 1")
        if observations > source_len:
            raise ValueError(
                f"observations {observations} exceeds historical dataset length {source_len}"
            )
        n = observations
    if not column_factors:
        raise ValueError("empty factor panel: at least one factor column is required")
    start = date(2022, 1, 3)
    dates = tuple(start + timedelta(days=i) for i in range(n))
    changes: dict[RiskFactor, Sequence[float]] = {
        factor: _series_for_factor(factor, series)[:n] for factor in column_factors
    }
    return HistoricalFactorPanel.from_columns(dates, changes)


__all__ = [
    "DEFAULT_PRODUCTION_PANEL_FACTORS",
    "EQUITY_CHANGE_UNIT",
    "FX_CHANGE_UNIT",
    "PER_FACTOR_PANEL_PROJECTION",
    "RATE_CHANGE_UNIT",
    "VOL_CHANGE_UNIT",
    "FactorPanelObservation",
    "HistoricalFactorPanel",
    "change_unit",
    "create_synthetic_factor_panel",
    "factor_panel_from_dataset",
    "panel_factor_identity",
    "truncate_factor_panel",
]
