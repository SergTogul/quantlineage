"""Deterministic SHA-256 of normalized series content. Excludes retrieved_at."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from app.market.ingestion.models import Frequency, HistoricalSeries


def content_hash(series: HistoricalSeries, *, transform_config: Mapping[str, Any] | None = None) -> str:
    frequency = series.metadata.frequency
    frequency_value = frequency.value if isinstance(frequency, Frequency) else str(frequency)
    payload: dict[str, Any] = {
        "instrument_id": series.instrument.instrument_id,
        "source": series.metadata.source,
        "source_symbol": series.metadata.source_symbol,
        "unit": series.metadata.unit,
        "frequency": frequency_value,
        "currency": series.metadata.currency,
        "adjustment": series.metadata.adjustment,
        "normalization_version": series.metadata.normalization_version,
        "points": [[point.observation_date.isoformat(), point.value] for point in series.points],
    }
    if transform_config is not None:
        payload["transform_config"] = dict(transform_config)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()
