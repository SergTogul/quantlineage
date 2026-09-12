"""Date-intersection alignment. No silent forward-fill."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from app.market.ingestion.models import HistoricalPoint, HistoricalSeries
from app.market.quality.errors import InsufficientAlignedHistoryError
from app.market.quality.models import MIN_OBSERVATIONS, AlignmentResult


def align_series(
    series_by_id: Mapping[str, HistoricalSeries],
    *,
    min_aligned: int = MIN_OBSERVATIONS,
) -> AlignmentResult:
    """Intersect observation dates; report per-series drops; order by instrument_id."""
    if not series_by_id:
        raise InsufficientAlignedHistoryError("no series to align")

    dated: dict[str, dict[date, HistoricalPoint]] = {}
    instrument_ids: dict[str, str] = {}
    for key, series in series_by_id.items():
        instrument_id = series.instrument.instrument_id
        instrument_ids[key] = instrument_id
        dated[key] = {point.observation_date: point for point in series.points}

    date_sets = [set(points) for points in dated.values()]
    intersection = set.intersection(*date_sets) if date_sets else set()
    aligned_dates = tuple(sorted(intersection))
    if len(aligned_dates) < min_aligned:
        raise InsufficientAlignedHistoryError(
            f"aligned length {len(aligned_dates)} is below minimum {min_aligned}"
        )

    ordered_keys = tuple(sorted(series_by_id, key=lambda key: instrument_ids[key]))
    series_ids = tuple(instrument_ids[key] for key in ordered_keys)
    aligned: dict[str, tuple[HistoricalPoint, ...]] = {}
    dropped_dates: dict[str, tuple[date, ...]] = {}
    for key in ordered_keys:
        instrument_id = instrument_ids[key]
        points = dated[key]
        aligned[instrument_id] = tuple(points[day] for day in aligned_dates)
        dropped_dates[instrument_id] = tuple(sorted(set(points) - intersection))

    return AlignmentResult(
        dates=aligned_dates,
        series_ids=series_ids,
        aligned=aligned,
        dropped_dates=dropped_dates,
    )
