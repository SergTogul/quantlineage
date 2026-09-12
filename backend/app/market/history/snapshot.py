"""Build a frozen MarketSnapshot from injected public history/macro providers.

Providers are injected (tests use fakes). Pricing and RiskRun consume the
persisted snapshot id and never call Yahoo/FRED. Cash books need spots + USD
key rates only — this builder does not attach vol surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.domain.models import MarketSnapshot, RiskRun, as_of_wire
from app.market.history.spec import WAVE_A_SPEC, FactorMapping, PublicHistoryDatasetSpec
from app.market.history.transforms import percent_level_to_decimal
from app.market.ingestion.errors import NotFoundError
from app.market.ingestion.models import (
    Frequency,
    HistoricalPoint,
    HistoricalSeries,
    InstrumentRef,
    MacroSeriesRef,
)
from app.market.ingestion.normalize import STALE_AFTER_DAYS, is_stale
from app.market.ingestion.protocols import HistoricalDataProvider, MacroDataProvider
from app.persistence.repositories import MarketSnapshotRepository, RiskRunRepository
from app.risk.factor_types import EquitySpot, RateZero, parse_factor_column_id

SNAPSHOT_LOOKBACK_DAYS = 30
"""Fetch window so a 7-day stale print is visible and rejected, not silently skipped."""


class PublicSnapshotError(Exception):
    code = "public_snapshot_failed"

    def __init__(self, message: str = "") -> None:
        super().__init__(message)


class StalePublicSnapshotError(PublicSnapshotError):
    code = "stale_observation"


class MissingPublicSnapshotMarkError(PublicSnapshotError):
    code = "missing_required_mark"


class UnsavedPublicSnapshotError(PublicSnapshotError):
    code = "unsaved_snapshot"


@dataclass(frozen=True, slots=True)
class PublicSnapshotBuild:
    snapshot: MarketSnapshot
    lineage: dict[str, Any]


def build_public_snapshot(
    *,
    as_of: date,
    history_provider: HistoricalDataProvider,
    macro_provider: MacroDataProvider,
    spec: PublicHistoryDatasetSpec = WAVE_A_SPEC,
    lookback_days: int = SNAPSHOT_LOOKBACK_DAYS,
) -> PublicSnapshotBuild:
    """Latest valid observation ≤ as_of for each Wave A mapping; fail closed if stale."""
    start = as_of - timedelta(days=lookback_days)
    equity_spots: dict[str, float] = {}
    key_rates_usd: dict[str, float] = {}
    usd_discount: float | None = None
    marks: dict[str, dict[str, Any]] = {}

    for mapping in spec.factor_mappings:
        series = _fetch_mapping(
            mapping,
            start=start,
            end=as_of,
            frequency=spec.frequency,
            history_provider=history_provider,
            macro_provider=macro_provider,
        )
        point = _latest_on_or_before(series.points, as_of)
        if point is None:
            raise MissingPublicSnapshotMarkError(
                f"no observation on or before {as_of.isoformat()} for {mapping.instrument_id}"
            )
        stale = is_stale(
            last_observation=point.observation_date,
            requested_end=as_of,
            retrieved_at=series.metadata.retrieved_at,
        )
        if stale:
            raise StalePublicSnapshotError(
                f"{mapping.instrument_id} last observation {point.observation_date.isoformat()} "
                f"is more than {STALE_AFTER_DAYS} days before {as_of.isoformat()}"
            )
        snapshot_value = _snapshot_value(mapping, point.value)
        factor = parse_factor_column_id(mapping.factor_column)
        if isinstance(factor, EquitySpot):
            equity_spots[factor.symbol] = snapshot_value
        elif isinstance(factor, RateZero):
            key_rates_usd[factor.tenor] = snapshot_value
            if mapping.source_symbol == "DGS10":
                usd_discount = snapshot_value
        else:
            raise MissingPublicSnapshotMarkError(f"missing required factor {mapping.instrument_id}")
        marks[mapping.instrument_id] = {
            "provider": series.metadata.source,
            "source_symbol": series.metadata.source_symbol,
            "source_observation_date": point.observation_date.isoformat(),
            "unit": series.metadata.unit,
            "stale": False,
            "snapshot_value": snapshot_value,
        }

    if usd_discount is None:
        raise MissingPublicSnapshotMarkError("missing required factor macro:FRED:DGS10")

    snapshot = MarketSnapshot(
        id=f"{spec.dataset_id}:{as_of.isoformat()}",
        as_of=as_of,
        equity_spots=equity_spots,
        rates={"USD": usd_discount},
        key_rates={"USD": key_rates_usd},
    )
    lineage = {
        "dataset_id": spec.dataset_id,
        "as_of": as_of_wire(as_of),
        "stale_after_days": STALE_AFTER_DAYS,
        "marks": marks,
    }
    return PublicSnapshotBuild(snapshot=snapshot, lineage=lineage)


def persist_public_snapshot(
    repo: MarketSnapshotRepository, built: PublicSnapshotBuild
) -> str:
    """Write the frozen snapshot before any RiskRun may bind its id."""
    return repo.save(built.snapshot, meta=built.lineage)


def bind_risk_run_to_saved_snapshot(
    *,
    run_repo: RiskRunRepository,
    market_repo: MarketSnapshotRepository,
    run: RiskRun,
    snapshot_id: str,
) -> RiskRun:
    """Bind only a snapshot that already exists in the repository."""
    stored = market_repo.get(snapshot_id)
    if stored is None:
        raise UnsavedPublicSnapshotError(f"snapshot not persisted: {snapshot_id}")
    bound = run.model_copy(
        update={
            "market_snapshot_id": stored.id,
            "as_of": stored.as_of,
        }
    )
    return run_repo.create(bound)


def _snapshot_value(mapping: FactorMapping, raw: float) -> float:
    if mapping.kind == "rate":
        return percent_level_to_decimal(raw)
    return float(raw)


def _latest_on_or_before(points: list[HistoricalPoint], as_of: date) -> HistoricalPoint | None:
    eligible = [point for point in points if point.observation_date <= as_of]
    if not eligible:
        return None
    return max(eligible, key=lambda point: point.observation_date)


def _fetch_mapping(
    mapping: FactorMapping,
    *,
    start: date,
    end: date,
    frequency: Frequency,
    history_provider: HistoricalDataProvider,
    macro_provider: MacroDataProvider,
) -> HistoricalSeries:
    try:
        if mapping.kind == "equity":
            instrument = InstrumentRef(
                instrument_id=mapping.instrument_id,
                asset_type=mapping.asset_type,
                currency="USD",
            )
            return history_provider.fetch_history(
                instrument, start=start, end=end, frequency=frequency
            )
        if mapping.kind == "rate":
            series_ref = MacroSeriesRef(
                instrument_id=mapping.instrument_id,
                series_id=mapping.source_symbol,
                currency="USD",
            )
            return macro_provider.fetch_series(series_ref, start=start, end=end)
    except NotFoundError as exc:
        raise MissingPublicSnapshotMarkError(
            f"missing required factor {mapping.instrument_id}"
        ) from exc
    raise MissingPublicSnapshotMarkError(f"missing required factor {mapping.instrument_id}")
