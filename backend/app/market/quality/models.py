"""Quality and lineage models. Reuses DataQualitySummary; does not duplicate it."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.market.ingestion.models import HistoricalPoint

ALLOWED_UNITS = frozenset({"price", "percent"})
MIN_OBSERVATIONS = 5


class SeriesLineage(BaseModel):
    """Inspectable identity and quality of one normalized series (AD-A6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    source_symbol: str
    instrument_id: str
    unit: str
    frequency: str
    currency: str
    adjustment: str
    first_observation: date | None
    last_observation: date | None
    observation_count: int
    retrieved_at: datetime
    missing_count: int
    duplicate_count: int
    stale: bool
    content_hash: str
    normalization_version: str


class AlignmentResult(BaseModel):
    """Intersection-aligned series, ordered by instrument_id. No forward-fill."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dates: tuple[date, ...]
    series_ids: tuple[str, ...]
    aligned: dict[str, tuple[HistoricalPoint, ...]] = Field(default_factory=dict)
    dropped_dates: dict[str, tuple[date, ...]] = Field(default_factory=dict)
