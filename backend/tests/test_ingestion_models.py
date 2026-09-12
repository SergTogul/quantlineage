"""G1: normalized ingestion models, error taxonomy, and provider protocols."""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.market.ingestion.errors import (
    AuthorizationError,
    InsufficientHistoryError,
    MalformedResponseError,
    NotFoundError,
    ProviderError,
    RateLimitedError,
    UnavailableError,
)
from app.market.ingestion.models import (
    NORMALIZATION_VERSION,
    DataQualitySummary,
    DataSourceMetadata,
    Frequency,
    HistoricalPoint,
    HistoricalSeries,
    InstrumentCandidate,
    InstrumentRef,
    MacroSeriesRef,
)
from app.market.ingestion.protocols import (
    HistoricalDataProvider,
    InstrumentSearchProvider,
    MacroDataProvider,
)

_AD_A3_FIELDS = frozenset(
    {
        "instrument_id",
        "source",
        "source_symbol",
        "observation_date",
        "value",
        "unit",
        "currency",
        "frequency",
        "adjustment",
        "retrieved_at",
    }
)


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
        "last_observation": date(2021, 1, 5),
        "observation_count": 2,
        "normalization_version": NORMALIZATION_VERSION,
    }
    base.update(overrides)
    return DataSourceMetadata.model_validate(base)


def test_normalization_version_is_wave_a_v1() -> None:
    assert NORMALIZATION_VERSION == "wave-a-v1"


def test_frequency_includes_daily() -> None:
    assert Frequency.DAILY == "daily"


def test_instrument_ref_uses_canonical_ids() -> None:
    equity = InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD")
    macro = InstrumentRef(instrument_id="macro:FRED:DGS10", asset_type="macro", currency="USD")
    assert equity.instrument_id == "equity:US:AAPL"
    assert macro.instrument_id == "macro:FRED:DGS10"


def test_instrument_ref_rejects_provider_payload_leak() -> None:
    with pytest.raises(ValidationError):
        InstrumentRef.model_validate(
            {
                "instrument_id": "equity:US:AAPL",
                "asset_type": "equity",
                "currency": "USD",
                "yahoo_quote": {"symbol": "AAPL"},
            }
        )


def test_instrument_candidate_capabilities_default_false() -> None:
    hit = InstrumentCandidate(
        instrument_id="equity:US:AAPL",
        display_name="Apple Inc.",
        provider="yahoo",
        source_symbol="AAPL",
        asset_type="equity",
        currency="USD",
    )
    assert hit.supported_for_history is False
    assert hit.supported_for_snapshot is False
    assert hit.supported_for_risk_factor is False


def test_historical_point_rejects_nan_and_inf() -> None:
    HistoricalPoint(observation_date=date(2021, 1, 4), value=129.41)
    with pytest.raises(ValidationError):
        HistoricalPoint(observation_date=date(2021, 1, 4), value=float("nan"))
    with pytest.raises(ValidationError):
        HistoricalPoint(observation_date=date(2021, 1, 4), value=float("inf"))
    with pytest.raises(ValidationError):
        HistoricalPoint(observation_date=date(2021, 1, 4), value=float("-inf"))


def test_historical_series_carries_explicit_units_and_ad_a3_fields() -> None:
    instrument = InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD")
    points = [
        HistoricalPoint(observation_date=date(2021, 1, 4), value=129.41),
        HistoricalPoint(observation_date=date(2021, 1, 5), value=130.12),
    ]
    series = HistoricalSeries(
        instrument=instrument,
        points=points,
        metadata=_metadata(),
        quality=DataQualitySummary(missing_count=0, duplicate_count=0, stale=False),
    )
    assert series.metadata.unit == "price"
    assert series.metadata.normalization_version == "wave-a-v1"
    point = series.points[0]
    represented = {
        "instrument_id": series.instrument.instrument_id,
        "source": series.metadata.source,
        "source_symbol": series.metadata.source_symbol,
        "observation_date": point.observation_date,
        "value": point.value,
        "unit": series.metadata.unit,
        "currency": series.metadata.currency,
        "frequency": series.metadata.frequency,
        "adjustment": series.metadata.adjustment,
        "retrieved_at": series.metadata.retrieved_at,
    }
    assert set(represented) >= _AD_A3_FIELDS
    assert represented["value"] == 129.41


def test_data_quality_summary_notes_are_optional() -> None:
    quality = DataQualitySummary(missing_count=1, duplicate_count=0, stale=True)
    assert quality.notes is None
    with_notes = DataQualitySummary(
        missing_count=0,
        duplicate_count=2,
        stale=False,
        notes="duplicate observation dates dropped",
    )
    assert with_notes.notes is not None


def test_macro_series_ref_wraps_canonical_id_and_fred_series() -> None:
    ref = MacroSeriesRef(instrument_id="macro:FRED:DGS10", series_id="DGS10")
    assert ref.instrument_id == "macro:FRED:DGS10"
    assert ref.series_id == "DGS10"
    assert ref.currency == "USD"


def test_provider_error_taxonomy_codes() -> None:
    mapping = {
        UnavailableError: "unavailable",
        AuthorizationError: "authorization",
        NotFoundError: "not_found",
        RateLimitedError: "rate_limited",
        MalformedResponseError: "malformed_response",
        InsufficientHistoryError: "insufficient_history",
    }
    for exc_type, code in mapping.items():
        err = exc_type("probe")
        assert isinstance(err, ProviderError)
        assert err.code == code
        assert "probe" in str(err)


def test_provider_protocols_do_not_depend_on_fastapi() -> None:
    assert hasattr(InstrumentSearchProvider, "search")
    assert hasattr(HistoricalDataProvider, "fetch_history")
    assert hasattr(MacroDataProvider, "fetch_series")
    import app.market.ingestion.protocols as protocols

    assert protocols.__file__ is not None
    tree = ast.parse(Path(protocols.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert "fastapi" not in imported
