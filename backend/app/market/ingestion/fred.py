"""FRED REST adapter for USD rates/macro series."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.market.ingestion.errors import (
    AuthorizationError,
    InsufficientHistoryError,
    MalformedResponseError,
)
from app.market.ingestion.http import new_client, request_json
from app.market.ingestion.models import (
    NORMALIZATION_VERSION,
    DataQualitySummary,
    DataSourceMetadata,
    Frequency,
    HistoricalSeries,
    InstrumentRef,
    MacroSeriesRef,
)
from app.market.ingestion.normalize import collect_points, is_stale, parse_observation_value

FRED_BASE = "https://api.stlouisfed.org"
_FRED_MISSING = frozenset({"."})


class FredAdapter:
    """MacroDataProvider for official FRED observations JSON."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        api_key: str | None = None,
    ) -> None:
        self._client = client if client is not None else new_client()
        if api_key is not None:
            self._api_key = api_key
        else:
            self._api_key = os.environ.get("FRED_API_KEY")

    def fetch_series(
        self, series: MacroSeriesRef, *, start: date, end: date
    ) -> HistoricalSeries:
        key = (self._api_key or "").strip()
        if not key:
            raise AuthorizationError("FRED credentials are not configured")
        payload = request_json(
            self._client,
            "GET",
            f"{FRED_BASE}/fred/series/observations",
            params={
                "series_id": series.series_id,
                "file_type": "json",
                "api_key": key,
                "observation_start": start.isoformat(),
                "observation_end": end.isoformat(),
            },
        )
        observations = _require_observations(payload)
        rows: list[tuple[date, float | None]] = []
        for raw in observations:
            if not isinstance(raw, dict):
                raise MalformedResponseError("provider returned malformed JSON")
            day = _parse_date(raw.get("date"))
            if day < start or day > end:
                continue
            value = parse_observation_value(raw.get("value"), missing_tokens=_FRED_MISSING)
            rows.append((day, value))
        points, missing, duplicates = collect_points(rows)
        if not points:
            raise InsufficientHistoryError("no usable FRED observations")
        retrieved_at = datetime.now(UTC)
        last = points[-1].observation_date
        instrument = InstrumentRef(
            instrument_id=series.instrument_id,
            asset_type="macro",
            currency=series.currency,
        )
        metadata = DataSourceMetadata(
            source="fred",
            source_symbol=series.series_id,
            unit="percent",
            currency=series.currency,
            frequency=Frequency.DAILY,
            adjustment="unadjusted",
            retrieved_at=retrieved_at,
            first_observation=points[0].observation_date,
            last_observation=last,
            observation_count=len(points),
            normalization_version=NORMALIZATION_VERSION,
        )
        quality = DataQualitySummary(
            missing_count=missing,
            duplicate_count=duplicates,
            stale=is_stale(last_observation=last, requested_end=end, retrieved_at=retrieved_at),
        )
        return HistoricalSeries(
            instrument=instrument,
            points=points,
            metadata=metadata,
            quality=quality,
        )


def _require_observations(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        raise MalformedResponseError("provider returned malformed JSON")
    value = payload.get("observations")
    if not isinstance(value, list):
        raise MalformedResponseError("provider returned malformed JSON")
    return value


def _parse_date(raw: Any) -> date:
    if not isinstance(raw, str):
        raise MalformedResponseError("provider returned malformed JSON")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise MalformedResponseError("provider returned malformed JSON") from None
