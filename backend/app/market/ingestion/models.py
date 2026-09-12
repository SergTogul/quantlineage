"""Normalized public-data models. Provider JSON must not appear here."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

NORMALIZATION_VERSION = "wave-a-v1"


class Frequency(str, Enum):
    DAILY = "daily"


class InstrumentRef(BaseModel):
    """Canonical internal instrument identity (AD-A8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str
    asset_type: str
    currency: str


class InstrumentCandidate(BaseModel):
    """Search hit. Capability flags default false when unknown (AD-A9)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str
    display_name: str
    provider: str
    source_symbol: str
    asset_type: str
    currency: str
    supported_for_history: bool = False
    supported_for_snapshot: bool = False
    supported_for_risk_factor: bool = False


class HistoricalPoint(BaseModel):
    """One calendar-date observation. Value must be a finite float."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_date: date
    value: float = Field(allow_inf_nan=False)


class DataSourceMetadata(BaseModel):
    """Lineage for a normalized series (AD-A3 / AD-A6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    source_symbol: str
    unit: str
    currency: str
    frequency: Frequency
    adjustment: str
    retrieved_at: datetime
    first_observation: date | None
    last_observation: date | None
    observation_count: int
    normalization_version: str = NORMALIZATION_VERSION


class DataQualitySummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    missing_count: int
    duplicate_count: int
    stale: bool
    notes: str | None = None


class HistoricalSeries(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument: InstrumentRef
    points: list[HistoricalPoint]
    metadata: DataSourceMetadata
    quality: DataQualitySummary


class MacroSeriesRef(BaseModel):
    """FRED (or compatible) series plus canonical internal id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str
    series_id: str
    currency: str = "USD"
