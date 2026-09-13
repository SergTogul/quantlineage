"""Materialize public observed history into a frozen per-factor CSV artifact.

Fetch uses injected :class:`HistoricalDataProvider` / :class:`MacroDataProvider`
(tests pass fakes). Risk engines load the frozen file and never call providers.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from app.market.history.artifact import (
    public_history_dataset_dir,
    sidecar_path_for_csv,
    versioned_csv_path,
    write_sidecar,
)
from app.market.history.spec import (
    WAVE_A_SPEC,
    WAVE_A_TRANSFORM_CONFIG,
    CanonicalMappingError,
    FactorMapping,
    PublicHistoryDatasetSpec,
    assert_canonical_mappings,
    assert_series_matches_mapping,
)
from app.market.history.transforms import equity_relative_return, percent_level_move_to_bps
from app.market.ingestion.errors import NotFoundError
from app.market.ingestion.models import (
    HistoricalPoint,
    HistoricalSeries,
    InstrumentRef,
    MacroSeriesRef,
)
from app.market.ingestion.protocols import HistoricalDataProvider, MacroDataProvider
from app.market.quality import (
    InsufficientAlignedHistoryError,
    align_series,
    content_hash,
    validate_series,
)
from app.market.quality.models import SeriesLineage


class FreezeError(Exception):
    code = "freeze_failed"

    def __init__(self, message: str = "") -> None:
        super().__init__(message)


class MissingRequiredFactorError(FreezeError):
    code = "missing_required_factor"


@dataclass(frozen=True, slots=True)
class FrozenHistoryArtifact:
    dataset_id: str
    dataset_version: str
    csv_path: Path
    sidecar_path: Path


def freeze_public_history(
    *,
    history_provider: HistoricalDataProvider,
    macro_provider: MacroDataProvider,
    output_dir: str | Path,
    spec: PublicHistoryDatasetSpec = WAVE_A_SPEC,
) -> FrozenHistoryArtifact:
    """Fetch → validate → align levels → transform → persist CSV + sidecar."""
    try:
        assert_canonical_mappings(spec)
    except CanonicalMappingError as exc:
        raise FreezeError(str(exc)) from exc
    series_by_id = _fetch_required_series(
        spec, history_provider=history_provider, macro_provider=macro_provider
    )
    min_levels = spec.min_aligned_returns + 1
    lineage_by_id: dict[str, SeriesLineage] = {}
    for mapping in spec.factor_mappings:
        lineage_by_id[mapping.instrument_id] = validate_series(
            series_by_id[mapping.instrument_id],
            requested_end=spec.end,
            min_observations=min_levels,
        )
    alignment = align_series(series_by_id, min_aligned=min_levels)
    level_dates = alignment.dates
    return_dates = level_dates[1:]
    if len(return_dates) < spec.min_aligned_returns:
        raise InsufficientAlignedHistoryError(
            f"aligned returns {len(return_dates)} is below minimum {spec.min_aligned_returns}"
        )

    columns: dict[str, list[float]] = {}
    transformed_series: dict[str, HistoricalSeries] = {}
    mapping_by_id = {item.instrument_id: item for item in spec.factor_mappings}
    for instrument_id in alignment.series_ids:
        mapping = mapping_by_id[instrument_id]
        points = alignment.aligned[instrument_id]
        moves = _level_points_to_moves(mapping, points)
        columns[mapping.factor_column] = moves
        transformed_series[mapping.factor_column] = _transformed_series(
            series_by_id[instrument_id],
            return_dates,
            moves,
        )

    dataset_version = _panel_content_version(transformed_series, WAVE_A_TRANSFORM_CONFIG)
    dataset_dir = public_history_dataset_dir(output_dir)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    csv_path = versioned_csv_path(dataset_dir, dataset_version)
    _write_immutable_factor_csv(csv_path, spec, return_dates, columns)
    sidecar_payload = {
        "alignment": spec.alignment,
        "dataset_id": spec.dataset_id,
        "dataset_name": spec.dataset_name,
        "dataset_version": dataset_version,
        "dropped_dates": {
            instrument_id: [day.isoformat() for day in dates]
            for instrument_id, dates in alignment.dropped_dates.items()
        },
        "end": spec.end.isoformat(),
        "factor_mappings": [
            {
                "asset_type": item.asset_type,
                "factor_column": item.factor_column,
                "instrument_id": item.instrument_id,
                "kind": item.kind,
                "provider": item.provider,
                "source_symbol": item.source_symbol,
                "unit": item.unit,
            }
            for item in spec.factor_mappings
        ],
        "frequency": spec.frequency.value,
        "min_aligned_returns": spec.min_aligned_returns,
        "normalization_version": spec.normalization_version,
        "provider_source": spec.provider_source,
        "source_lineage": {
            instrument_id: lineage.model_dump(mode="json")
            for instrument_id, lineage in lineage_by_id.items()
        },
        "start": spec.start.isoformat(),
        "transform_config": dict(WAVE_A_TRANSFORM_CONFIG),
    }
    sidecar_path = write_sidecar(sidecar_path_for_csv(csv_path), sidecar_payload)
    return FrozenHistoryArtifact(
        dataset_id=spec.dataset_id,
        dataset_version=dataset_version,
        csv_path=csv_path.resolve(),
        sidecar_path=sidecar_path.resolve(),
    )


def _fetch_required_series(
    spec: PublicHistoryDatasetSpec,
    *,
    history_provider: HistoricalDataProvider,
    macro_provider: MacroDataProvider,
) -> dict[str, HistoricalSeries]:
    series_by_id: dict[str, HistoricalSeries] = {}
    for mapping in spec.factor_mappings:
        try:
            series = _fetch_one(
                mapping,
                spec,
                history_provider=history_provider,
                macro_provider=macro_provider,
            )
        except NotFoundError as exc:
            raise MissingRequiredFactorError(
                f"missing required factor {mapping.instrument_id}"
            ) from exc
        if series is None:
            raise MissingRequiredFactorError(f"missing required factor {mapping.instrument_id}")
        try:
            assert_series_matches_mapping(series, mapping)
        except CanonicalMappingError as exc:
            raise FreezeError(str(exc)) from exc
        if not any(point.observation_date <= spec.end for point in series.points):
            raise MissingRequiredFactorError(
                f"no observation on or before {spec.end.isoformat()} for {mapping.instrument_id}"
            )
        series_by_id[mapping.instrument_id] = series
    missing = [
        item.instrument_id for item in spec.factor_mappings if item.instrument_id not in series_by_id
    ]
    if missing:
        raise MissingRequiredFactorError(f"missing required factor {missing[0]}")
    return series_by_id


def _fetch_one(
    mapping: FactorMapping,
    spec: PublicHistoryDatasetSpec,
    *,
    history_provider: HistoricalDataProvider,
    macro_provider: MacroDataProvider,
) -> HistoricalSeries:
    if mapping.kind == "equity":
        instrument = InstrumentRef(
            instrument_id=mapping.instrument_id,
            asset_type=mapping.asset_type,
            currency="USD",
        )
        return history_provider.fetch_history(
            instrument,
            start=spec.start,
            end=spec.end,
            frequency=spec.frequency,
        )
    if mapping.kind == "rate":
        series_ref = MacroSeriesRef(
            instrument_id=mapping.instrument_id,
            series_id=mapping.source_symbol,
            currency="USD",
        )
        return macro_provider.fetch_series(series_ref, start=spec.start, end=spec.end)
    raise MissingRequiredFactorError(f"missing required factor {mapping.instrument_id}")


def _level_points_to_moves(mapping: FactorMapping, points: tuple[HistoricalPoint, ...]) -> list[float]:
    moves: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        if mapping.kind == "equity":
            moves.append(equity_relative_return(previous.value, current.value))
        else:
            moves.append(percent_level_move_to_bps(previous.value, current.value))
    return moves


def _transformed_series(
    source: HistoricalSeries,
    return_dates: tuple[date, ...],
    moves: list[float],
) -> HistoricalSeries:
    points = [
        HistoricalPoint(observation_date=day, value=value)
        for day, value in zip(return_dates, moves, strict=True)
    ]
    metadata = source.metadata.model_copy(
        update={
            "first_observation": points[0].observation_date if points else None,
            "last_observation": points[-1].observation_date if points else None,
            "observation_count": len(points),
        }
    )
    return source.model_copy(update={"points": points, "metadata": metadata})


def _panel_content_version(
    series_by_column: Mapping[str, HistoricalSeries],
    transform_config: Mapping[str, str],
) -> str:
    column_hashes = {
        column: content_hash(series, transform_config=transform_config)
        for column, series in series_by_column.items()
    }
    blob = json.dumps(column_hashes, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _write_immutable_factor_csv(
    csv_path: Path,
    spec: PublicHistoryDatasetSpec,
    return_dates: tuple[date, ...],
    columns: Mapping[str, list[float]],
) -> None:
    """Write ``{content-hash}.csv``. Refuse to replace existing bytes with different content."""
    tmp_path = csv_path.with_name(csv_path.name + ".tmp")
    _write_factor_csv(tmp_path, spec, return_dates, columns)
    new_bytes = tmp_path.read_bytes()
    if csv_path.is_file() and csv_path.read_bytes() != new_bytes:
        tmp_path.unlink(missing_ok=True)
        raise FreezeError(
            f"refusing to overwrite frozen public history {csv_path.name} with different bytes"
        )
    tmp_path.replace(csv_path)


def _write_factor_csv(
    csv_path: Path,
    spec: PublicHistoryDatasetSpec,
    return_dates: tuple[date, ...],
    columns: Mapping[str, list[float]],
) -> None:
    fieldnames = ["date", *(item.factor_column for item in spec.factor_mappings)]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for index, day in enumerate(return_dates):
            row: dict[str, str] = {"date": day.isoformat()}
            for item in spec.factor_mappings:
                row[item.factor_column] = format(columns[item.factor_column][index], ".17g")
            writer.writerow(row)
