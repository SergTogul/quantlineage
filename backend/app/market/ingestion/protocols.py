"""Provider protocols. These must not depend on FastAPI."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.market.ingestion.models import (
    Frequency,
    HistoricalSeries,
    InstrumentCandidate,
    InstrumentRef,
    MacroSeriesRef,
)


class InstrumentSearchProvider(Protocol):
    def search(
        self, query: str, *, asset_types: set[str] | None = None
    ) -> list[InstrumentCandidate]: ...


class HistoricalDataProvider(Protocol):
    def fetch_history(
        self,
        instrument: InstrumentRef,
        *,
        start: date,
        end: date,
        frequency: Frequency,
    ) -> HistoricalSeries: ...


class MacroDataProvider(Protocol):
    def fetch_series(
        self, series: MacroSeriesRef, *, start: date, end: date
    ) -> HistoricalSeries: ...
