"""G3: series validation, alignment, content hashing, and lineage (no FastAPI, no network)."""

from __future__ import annotations

import ast
import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.market.ingestion.models import (
    NORMALIZATION_VERSION,
    DataQualitySummary,
    DataSourceMetadata,
    Frequency,
    HistoricalPoint,
    HistoricalSeries,
    InstrumentRef,
)
from app.market.ingestion.normalize import STALE_AFTER_DAYS, is_stale
from app.market.quality import (
    MIN_OBSERVATIONS,
    AlignmentResult,
    DuplicateDatesError,
    InsufficientAlignedHistoryError,
    InsufficientObservationsError,
    NonFiniteValueError,
    NonPositivePriceError,
    SeriesLineage,
    UnknownUnitError,
    UnsortedDatesError,
    align_series,
    content_hash,
    validate_series,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
_QUALITY_ROOT = APP_ROOT / "market" / "quality"


def _metadata(**overrides: object) -> DataSourceMetadata:
    base: dict[str, object] = {
        "source": "yahoo",
        "source_symbol": "AAPL",
        "unit": "price",
        "currency": "USD",
        "frequency": Frequency.DAILY,
        "adjustment": "adjusted",
        "retrieved_at": datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        "first_observation": date(2021, 1, 4),
        "last_observation": date(2021, 1, 8),
        "observation_count": 5,
        "normalization_version": NORMALIZATION_VERSION,
    }
    base.update(overrides)
    return DataSourceMetadata.model_validate(base)


def _points(*pairs: tuple[str, float]) -> list[HistoricalPoint]:
    return [HistoricalPoint(observation_date=date.fromisoformat(day), value=value) for day, value in pairs]


_DEFAULT_PAIRS: tuple[tuple[str, float], ...] = (
    ("2021-01-04", 129.41),
    ("2021-01-05", 130.12),
    ("2021-01-06", 126.60),
    ("2021-01-07", 130.92),
    ("2021-01-08", 132.05),
)


def _series(
    *,
    instrument_id: str = "equity:US:AAPL",
    asset_type: str = "equity",
    source: str = "yahoo",
    source_symbol: str = "AAPL",
    unit: str = "price",
    adjustment: str = "adjusted",
    pairs: tuple[tuple[str, float], ...] | None = None,
    points: list[HistoricalPoint] | None = None,
    missing_count: int = 0,
    duplicate_count: int = 0,
    stale: bool = False,
    retrieved_at: datetime | None = None,
) -> HistoricalSeries:
    resolved = list(points) if points is not None else _points(*(pairs or _DEFAULT_PAIRS))
    first = resolved[0].observation_date if resolved else None
    last = resolved[-1].observation_date if resolved else None
    meta_kwargs: dict[str, object] = {
        "source": source,
        "source_symbol": source_symbol,
        "unit": unit,
        "adjustment": adjustment,
        "first_observation": first,
        "last_observation": last,
        "observation_count": len(resolved),
    }
    if retrieved_at is not None:
        meta_kwargs["retrieved_at"] = retrieved_at
    return HistoricalSeries(
        instrument=InstrumentRef(instrument_id=instrument_id, asset_type=asset_type, currency="USD"),
        points=resolved,
        metadata=_metadata(**meta_kwargs),
        quality=DataQualitySummary(
            missing_count=missing_count,
            duplicate_count=duplicate_count,
            stale=stale,
        ),
    )


def test_stale_after_days_is_seven_calendar_days() -> None:
    assert STALE_AFTER_DAYS == 7


def test_min_observations_library_default_is_five() -> None:
    assert MIN_OBSERVATIONS == 5


def test_is_stale_false_on_seven_day_boundary() -> None:
    retrieved_at = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    horizon = retrieved_at.date()
    last = horizon - timedelta(days=STALE_AFTER_DAYS)
    assert is_stale(last_observation=last, requested_end=horizon, retrieved_at=retrieved_at) is False


def test_is_stale_true_one_day_past_seven_day_boundary() -> None:
    retrieved_at = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    horizon = retrieved_at.date()
    last = horizon - timedelta(days=STALE_AFTER_DAYS + 1)
    assert is_stale(last_observation=last, requested_end=horizon, retrieved_at=retrieved_at) is True


def test_validate_series_returns_lineage_with_required_fields() -> None:
    series = _series()
    lineage = validate_series(series, requested_end=date(2021, 1, 8))
    assert isinstance(lineage, SeriesLineage)
    payload = lineage.model_dump()
    assert set(payload) >= {
        "source",
        "source_symbol",
        "instrument_id",
        "unit",
        "frequency",
        "currency",
        "adjustment",
        "first_observation",
        "last_observation",
        "observation_count",
        "retrieved_at",
        "missing_count",
        "duplicate_count",
        "stale",
        "content_hash",
        "normalization_version",
    }
    assert lineage.instrument_id == "equity:US:AAPL"
    assert lineage.source == "yahoo"
    assert lineage.source_symbol == "AAPL"
    assert lineage.unit == "price"
    assert lineage.frequency == "daily"
    assert lineage.currency == "USD"
    assert lineage.adjustment == "adjusted"
    assert lineage.first_observation == date(2021, 1, 4)
    assert lineage.last_observation == date(2021, 1, 8)
    assert lineage.observation_count == 5
    assert lineage.missing_count == 0
    assert lineage.duplicate_count == 0
    assert lineage.stale is False
    assert lineage.normalization_version == NORMALIZATION_VERSION
    assert lineage.content_hash == content_hash(series)


def test_validate_series_rejects_unsorted_dates() -> None:
    points = _points(
        ("2021-01-05", 130.12),
        ("2021-01-04", 129.41),
        ("2021-01-06", 126.60),
        ("2021-01-07", 130.92),
        ("2021-01-08", 132.05),
    )
    with pytest.raises(UnsortedDatesError):
        validate_series(_series(points=points), requested_end=date(2021, 1, 8))


def test_validate_series_rejects_duplicate_dates() -> None:
    points = _points(
        ("2021-01-04", 129.41),
        ("2021-01-05", 130.12),
        ("2021-01-05", 130.50),
        ("2021-01-06", 126.60),
        ("2021-01-07", 130.92),
        ("2021-01-08", 132.05),
    )
    with pytest.raises(DuplicateDatesError):
        validate_series(_series(points=points), requested_end=date(2021, 1, 8))


def test_validate_series_rejects_non_finite_values() -> None:
    points = _points(*_DEFAULT_PAIRS)
    points[2] = HistoricalPoint.model_construct(observation_date=date(2021, 1, 6), value=math.nan)
    with pytest.raises(NonFiniteValueError):
        validate_series(_series(points=points), requested_end=date(2021, 1, 8))


def test_validate_series_rejects_non_positive_price() -> None:
    for value in (0.0, -1.0):
        pairs = list(_DEFAULT_PAIRS)
        pairs[0] = ("2021-01-04", value)
        with pytest.raises(NonPositivePriceError):
            validate_series(_series(pairs=tuple(pairs)), requested_end=date(2021, 1, 8))


def test_validate_series_allows_non_positive_percent() -> None:
    pairs = (
        ("2021-01-04", -0.25),
        ("2021-01-05", 0.0),
        ("2021-01-06", 1.81),
        ("2021-01-07", 1.83),
        ("2021-01-08", 1.88),
    )
    lineage = validate_series(
        _series(
            instrument_id="macro:FRED:DGS10",
            asset_type="macro",
            source="fred",
            source_symbol="DGS10",
            unit="percent",
            adjustment="unadjusted",
            pairs=pairs,
        ),
        requested_end=date(2021, 1, 8),
    )
    assert lineage.unit == "percent"
    assert lineage.observation_count == 5


def test_validate_series_rejects_unknown_unit() -> None:
    with pytest.raises(UnknownUnitError):
        validate_series(_series(unit="bps"), requested_end=date(2021, 1, 8))


def test_validate_series_rejects_below_minimum_observations() -> None:
    pairs = _DEFAULT_PAIRS[:4]
    with pytest.raises(InsufficientObservationsError):
        validate_series(_series(pairs=pairs), requested_end=date(2021, 1, 8))


def test_validate_series_respects_caller_min_observations_floor() -> None:
    with pytest.raises(InsufficientObservationsError):
        validate_series(_series(), requested_end=date(2021, 1, 8), min_observations=10)


def test_validate_series_records_fred_style_missing_count() -> None:
    series = _series(
        instrument_id="macro:FRED:DGS10",
        asset_type="macro",
        source="fred",
        source_symbol="DGS10",
        unit="percent",
        adjustment="unadjusted",
        missing_count=1,
    )
    lineage = validate_series(series, requested_end=date(2021, 1, 8))
    assert lineage.missing_count == 1
    assert lineage.observation_count == 5


def test_validate_series_stale_flag_follows_seven_day_rule() -> None:
    retrieved_at = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    requested_end = date(2026, 1, 15)
    fresh_last = requested_end - timedelta(days=STALE_AFTER_DAYS)
    stale_last = requested_end - timedelta(days=STALE_AFTER_DAYS + 1)
    fresh_pairs = tuple(
        ((fresh_last - timedelta(days=offset)).isoformat(), 100.0 + offset) for offset in range(4, -1, -1)
    )
    stale_pairs = tuple(
        ((stale_last - timedelta(days=offset)).isoformat(), 100.0 + offset) for offset in range(4, -1, -1)
    )
    fresh = validate_series(
        _series(pairs=fresh_pairs, retrieved_at=retrieved_at, stale=True),
        requested_end=requested_end,
    )
    stale = validate_series(
        _series(pairs=stale_pairs, retrieved_at=retrieved_at, stale=False),
        requested_end=requested_end,
    )
    assert fresh.stale is False
    assert stale.stale is True


def test_align_series_intersection_drops_aapl_extra_dates_deterministically() -> None:
    shared = (
        ("2021-01-05", 130.0),
        ("2021-01-06", 131.0),
        ("2021-01-07", 132.0),
        ("2021-01-08", 133.0),
        ("2021-01-11", 134.0),
    )
    aapl = _series(
        instrument_id="equity:US:AAPL",
        source_symbol="AAPL",
        pairs=(("2021-01-04", 129.0), *shared),
    )
    msft = _series(
        instrument_id="equity:US:MSFT",
        source_symbol="MSFT",
        pairs=shared,
    )
    result = align_series({"equity:US:MSFT": msft, "equity:US:AAPL": aapl})
    assert isinstance(result, AlignmentResult)
    assert result.dates == (
        date(2021, 1, 5),
        date(2021, 1, 6),
        date(2021, 1, 7),
        date(2021, 1, 8),
        date(2021, 1, 11),
    )
    assert result.series_ids == ("equity:US:AAPL", "equity:US:MSFT")
    assert result.dropped_dates["equity:US:AAPL"] == (date(2021, 1, 4),)
    assert result.dropped_dates["equity:US:MSFT"] == ()
    aapl_aligned = result.aligned["equity:US:AAPL"]
    assert [point.observation_date for point in aapl_aligned] == list(result.dates)
    assert [point.value for point in aapl_aligned] == [130.0, 131.0, 132.0, 133.0, 134.0]
    assert date(2021, 1, 4) not in {point.observation_date for point in aapl_aligned}


def test_align_series_does_not_forward_fill_gaps() -> None:
    aapl = _series(
        instrument_id="equity:US:AAPL",
        pairs=(
            ("2021-01-04", 100.0),
            ("2021-01-05", 101.0),
            ("2021-01-06", 102.0),
            ("2021-01-07", 103.0),
            ("2021-01-08", 104.0),
        ),
    )
    spy = _series(
        instrument_id="equity:US:SPY",
        source_symbol="SPY",
        pairs=(
            ("2021-01-04", 200.0),
            ("2021-01-05", 201.0),
            ("2021-01-06", 202.0),
            ("2021-01-07", 203.0),
            ("2021-01-11", 204.0),
        ),
    )
    result = align_series({"equity:US:AAPL": aapl, "equity:US:SPY": spy}, min_aligned=4)
    assert result.dates == (
        date(2021, 1, 4),
        date(2021, 1, 5),
        date(2021, 1, 6),
        date(2021, 1, 7),
    )
    spy_values = [point.value for point in result.aligned["equity:US:SPY"]]
    assert spy_values == [200.0, 201.0, 202.0, 203.0]
    assert 204.0 not in spy_values
    assert date(2021, 1, 8) in result.dropped_dates["equity:US:AAPL"]
    assert date(2021, 1, 11) in result.dropped_dates["equity:US:SPY"]


def test_align_series_order_is_sorted_by_instrument_id() -> None:
    spy = _series(instrument_id="equity:US:SPY", source_symbol="SPY")
    aapl = _series(instrument_id="equity:US:AAPL", source_symbol="AAPL")
    nvda = _series(instrument_id="equity:US:NVDA", source_symbol="NVDA")
    result = align_series(
        {
            "equity:US:SPY": spy,
            "equity:US:NVDA": nvda,
            "equity:US:AAPL": aapl,
        }
    )
    assert result.series_ids == ("equity:US:AAPL", "equity:US:NVDA", "equity:US:SPY")
    assert list(result.aligned) == list(result.series_ids)


def test_align_series_fails_below_min_aligned() -> None:
    left = _series(
        instrument_id="equity:US:AAPL",
        pairs=(
            ("2021-01-04", 1.0),
            ("2021-01-05", 2.0),
            ("2021-01-06", 3.0),
            ("2021-01-07", 4.0),
            ("2021-01-08", 5.0),
        ),
    )
    right = _series(
        instrument_id="equity:US:MSFT",
        source_symbol="MSFT",
        pairs=(
            ("2021-01-06", 3.0),
            ("2021-01-07", 4.0),
            ("2021-01-08", 5.0),
            ("2021-01-11", 6.0),
            ("2021-01-12", 7.0),
        ),
    )
    with pytest.raises(InsufficientAlignedHistoryError):
        align_series({"equity:US:AAPL": left, "equity:US:MSFT": right})


def test_content_hash_ignores_retrieved_at() -> None:
    early = _series(retrieved_at=datetime(2026, 1, 1, 8, 0, tzinfo=UTC))
    late = _series(retrieved_at=datetime(2026, 1, 20, 18, 30, tzinfo=UTC))
    assert content_hash(early) == content_hash(late)


def test_content_hash_changes_when_one_observation_changes() -> None:
    original = _series()
    mutated_pairs = list(_DEFAULT_PAIRS)
    mutated_pairs[2] = ("2021-01-06", 999.99)
    mutated = _series(pairs=tuple(mutated_pairs))
    assert content_hash(original) != content_hash(mutated)


def test_content_hash_includes_transform_config() -> None:
    series = _series()
    bare = content_hash(series)
    with_config = content_hash(series, transform_config={"method": "log_return", "lag": 1})
    other_config = content_hash(series, transform_config={"method": "simple_return", "lag": 1})
    assert bare != with_config
    assert with_config != other_config
    assert content_hash(series, transform_config={"lag": 1, "method": "log_return"}) == with_config


def test_content_hash_is_sha256_of_canonical_json_excluding_retrieved_at() -> None:
    series = _series()
    payload = {
        "adjustment": series.metadata.adjustment,
        "currency": series.metadata.currency,
        "frequency": series.metadata.frequency.value,
        "instrument_id": series.instrument.instrument_id,
        "normalization_version": series.metadata.normalization_version,
        "points": [[point.observation_date.isoformat(), point.value] for point in series.points],
        "source": series.metadata.source,
        "source_symbol": series.metadata.source_symbol,
        "unit": series.metadata.unit,
    }
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert content_hash(series) == expected
    assert "retrieved_at" not in json.dumps(payload)


def test_quality_library_does_not_import_fastapi_adapters_or_quant_core() -> None:
    assert _QUALITY_ROOT.is_dir()
    forbidden_roots = {"fastapi", "httpx"}
    for py in _QUALITY_ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(f"{node.module}.{alias.name}" for alias in node.names)
        roots = {name.split(".", 1)[0] for name in imported}
        assert forbidden_roots.isdisjoint(roots), py
        for name in imported:
            assert not name.startswith("app.risk"), f"{py} imports {name}"
            assert not name.startswith("app.pricing"), f"{py} imports {name}"
            assert name not in {"app.market.ingestion.yahoo", "app.market.ingestion.fred"}
