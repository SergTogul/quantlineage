"""Parse finite observation values; treat documented missing tokens as gaps."""

from __future__ import annotations

import math
from collections.abc import Collection
from datetime import date, datetime
from typing import Any

from app.market.ingestion.errors import MalformedResponseError
from app.market.ingestion.models import HistoricalPoint

STALE_AFTER_DAYS = 7
"""Wave A stale rule: last observation more than 7 calendar days before the horizon."""


def parse_observation_value(
    raw: Any,
    *,
    missing_tokens: Collection[str] = (),
) -> float | None:
    """Return a finite float, None if missing, or raise malformed_response."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise MalformedResponseError("non-numeric observation")
    if isinstance(raw, (int, float)):
        value = float(raw)
        if not math.isfinite(value):
            raise MalformedResponseError("non-finite observation")
        return value
    if isinstance(raw, str):
        token = raw.strip()
        if token == "" or token in missing_tokens:
            return None
        try:
            value = float(token)
        except ValueError:
            raise MalformedResponseError("non-numeric observation") from None
        if not math.isfinite(value):
            raise MalformedResponseError("non-finite observation")
        return value
    raise MalformedResponseError("non-numeric observation")


def collect_points(
    rows: list[tuple[date, float | None]],
) -> tuple[list[HistoricalPoint], int, int]:
    """Keep first finite value per date. Returns points, missing_count, duplicate_count."""
    points: list[HistoricalPoint] = []
    seen: set[date] = set()
    missing = 0
    duplicates = 0
    for observation_date, value in rows:
        if value is None:
            missing += 1
            continue
        if observation_date in seen:
            duplicates += 1
            continue
        seen.add(observation_date)
        points.append(HistoricalPoint(observation_date=observation_date, value=value))
    points.sort(key=lambda point: point.observation_date)
    return points, missing, duplicates


def is_stale(*, last_observation: date | None, requested_end: date, retrieved_at: datetime) -> bool:
    """True when last observation is more than STALE_AFTER_DAYS before requested_end/retrieved_at."""
    if last_observation is None:
        return True
    horizon = requested_end if requested_end <= retrieved_at.date() else retrieved_at.date()
    return (horizon - last_observation).days > STALE_AFTER_DAYS
