"""Fail-closed validation of normalized historical series. No interpolation."""

from __future__ import annotations

import math
from datetime import date

from app.market.ingestion.models import HistoricalSeries
from app.market.ingestion.normalize import is_stale
from app.market.quality.errors import (
    DuplicateDatesError,
    InsufficientObservationsError,
    NonFiniteValueError,
    NonPositivePriceError,
    UnknownUnitError,
    UnsortedDatesError,
)
from app.market.quality.hash import content_hash
from app.market.quality.models import ALLOWED_UNITS, MIN_OBSERVATIONS, SeriesLineage


def validate_series(
    series: HistoricalSeries,
    *,
    requested_end: date,
    min_observations: int = MIN_OBSERVATIONS,
) -> SeriesLineage:
    """Reject invalid series; return lineage including hash and 7-day stale flag."""
    dates = [point.observation_date for point in series.points]
    if dates != sorted(dates):
        raise UnsortedDatesError("observation dates are not sorted")
    if len(dates) != len(set(dates)):
        raise DuplicateDatesError("duplicate observation dates")
    for point in series.points:
        if not math.isfinite(point.value):
            raise NonFiniteValueError("non-finite observation value")
    unit = series.metadata.unit
    if unit not in ALLOWED_UNITS:
        raise UnknownUnitError(f"unknown unit {unit!r}; allowed {sorted(ALLOWED_UNITS)}")
    if unit == "price":
        for point in series.points:
            if point.value <= 0:
                raise NonPositivePriceError("price observations must be positive")
    if len(series.points) < min_observations:
        raise InsufficientObservationsError(
            f"observation_count {len(series.points)} is below minimum {min_observations}"
        )
    first = series.points[0].observation_date if series.points else None
    last = series.points[-1].observation_date if series.points else None
    frequency = series.metadata.frequency
    frequency_value = frequency.value if hasattr(frequency, "value") else str(frequency)
    return SeriesLineage(
        source=series.metadata.source,
        source_symbol=series.metadata.source_symbol,
        instrument_id=series.instrument.instrument_id,
        unit=unit,
        frequency=frequency_value,
        currency=series.metadata.currency,
        adjustment=series.metadata.adjustment,
        first_observation=first,
        last_observation=last,
        observation_count=len(series.points),
        retrieved_at=series.metadata.retrieved_at,
        missing_count=series.quality.missing_count,
        duplicate_count=series.quality.duplicate_count,
        stale=is_stale(
            last_observation=last,
            requested_end=requested_end,
            retrieved_at=series.metadata.retrieved_at,
        ),
        content_hash=content_hash(series),
        normalization_version=series.metadata.normalization_version,
    )
