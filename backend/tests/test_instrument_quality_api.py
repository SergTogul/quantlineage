"""G3: GET /instruments/{id}/quality — fake providers, no live network."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.instruments import get_history_provider, get_macro_provider
from app.main import app
from app.market.ingestion.errors import (
    AuthorizationError,
    MalformedResponseError,
    NotFoundError,
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
    InstrumentRef,
    MacroSeriesRef,
)
from app.market.quality import content_hash, validate_series


class FakeHistoryProvider:
    def __init__(self, series: HistoricalSeries | None = None, *, error: Exception | None = None) -> None:
        self.series = series
        self.error = error
        self.calls: list[tuple[str, date, date, Frequency]] = []

    def fetch_history(self, instrument: InstrumentRef, *, start: date, end: date, frequency: Frequency) -> HistoricalSeries:
        self.calls.append((instrument.instrument_id, start, end, frequency))
        if self.error is not None:
            raise self.error
        assert self.series is not None
        return self.series


class FakeMacroProvider:
    def __init__(self, series: HistoricalSeries | None = None, *, error: Exception | None = None) -> None:
        self.series = series
        self.error = error
        self.calls: list[tuple[str, str, date, date]] = []

    def fetch_series(self, series: MacroSeriesRef, *, start: date, end: date) -> HistoricalSeries:
        self.calls.append((series.instrument_id, series.series_id, start, end))
        if self.error is not None:
            raise self.error
        assert self.series is not None
        return self.series


def _points(*pairs: tuple[str, float]) -> list[HistoricalPoint]:
    return [HistoricalPoint(observation_date=date.fromisoformat(day), value=value) for day, value in pairs]


def _aapl_series() -> HistoricalSeries:
    points = _points(
        ("2021-01-04", 129.41),
        ("2021-01-05", 130.12),
        ("2021-01-06", 126.60),
        ("2021-01-07", 130.92),
        ("2021-01-08", 132.05),
    )
    return HistoricalSeries(
        instrument=InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD"),
        points=points,
        metadata=DataSourceMetadata(
            source="yahoo",
            source_symbol="AAPL",
            unit="price",
            currency="USD",
            frequency=Frequency.DAILY,
            adjustment="adjusted",
            retrieved_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            first_observation=date(2021, 1, 4),
            last_observation=date(2021, 1, 8),
            observation_count=5,
            normalization_version=NORMALIZATION_VERSION,
        ),
        quality=DataQualitySummary(missing_count=0, duplicate_count=0, stale=False),
    )


def _dgs10_series() -> HistoricalSeries:
    points = _points(
        ("2020-01-02", 1.88),
        ("2020-01-03", 1.81),
        ("2020-01-06", 1.79),
        ("2020-01-07", 1.83),
        ("2020-01-08", 1.87),
    )
    return HistoricalSeries(
        instrument=InstrumentRef(instrument_id="macro:FRED:DGS10", asset_type="macro", currency="USD"),
        points=points,
        metadata=DataSourceMetadata(
            source="fred",
            source_symbol="DGS10",
            unit="percent",
            currency="USD",
            frequency=Frequency.DAILY,
            adjustment="unadjusted",
            retrieved_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            first_observation=date(2020, 1, 2),
            last_observation=date(2020, 1, 8),
            observation_count=5,
            normalization_version=NORMALIZATION_VERSION,
        ),
        quality=DataQualitySummary(missing_count=1, duplicate_count=0, stale=False),
    )


@pytest.fixture
def history_provider() -> FakeHistoryProvider:
    return FakeHistoryProvider(_aapl_series())


@pytest.fixture
def macro_provider() -> FakeMacroProvider:
    return FakeMacroProvider(_dgs10_series())


@pytest.fixture
def client(history_provider: FakeHistoryProvider, macro_provider: FakeMacroProvider):
    app.dependency_overrides[get_history_provider] = lambda: history_provider
    app.dependency_overrides[get_macro_provider] = lambda: macro_provider
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_history_provider, None)
        app.dependency_overrides.pop(get_macro_provider, None)


def test_aapl_quality_returns_lineage_from_fake_series(
    client: TestClient, history_provider: FakeHistoryProvider, macro_provider: FakeMacroProvider
) -> None:
    series = history_provider.series
    assert series is not None
    expected = validate_series(series, requested_end=date(2021, 1, 8))
    response = client.get(
        "/api/v1/instruments/equity:US:AAPL/quality",
        params={"start": "2021-01-04", "end": "2021-01-08"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["instrument_id"] == "equity:US:AAPL"
    assert body["source"] == "yahoo"
    assert body["source_symbol"] == "AAPL"
    assert body["unit"] == "price"
    assert body["first_observation"] == "2021-01-04"
    assert body["last_observation"] == "2021-01-08"
    assert body["observation_count"] == 5
    assert body["missing_count"] == 0
    assert body["stale"] is False
    assert body["content_hash"] == expected.content_hash
    assert body["content_hash"] == content_hash(series)
    assert body["normalization_version"] == NORMALIZATION_VERSION
    assert history_provider.calls == [
        ("equity:US:AAPL", date(2021, 1, 4), date(2021, 1, 8), Frequency.DAILY)
    ]
    assert macro_provider.calls == []
    assert "FRED_API_KEY" not in response.text


def test_unknown_instrument_quality_is_404(client: TestClient, history_provider: FakeHistoryProvider) -> None:
    response = client.get(
        "/api/v1/instruments/equity:US:TSLA/quality",
        params={"start": "2021-01-04", "end": "2021-01-08"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert "message" in body
    assert "details" in body
    assert history_provider.calls == []


def test_empty_and_invalid_dates_are_400(client: TestClient, history_provider: FakeHistoryProvider) -> None:
    cases = [
        {},
        {"start": "", "end": "2021-01-08"},
        {"start": "2021-01-04", "end": ""},
        {"start": "   ", "end": "2021-01-08"},
        {"start": "not-a-date", "end": "2021-01-08"},
        {"start": "2021-01-08", "end": "2021-01-04"},
    ]
    for params in cases:
        response = client.get("/api/v1/instruments/equity:US:AAPL/quality", params=params)
        assert response.status_code == 400, params
        body = response.json()
        assert body["code"] == "bad_request"
        assert isinstance(body["message"], str) and body["message"]
        assert "details" in body
    assert history_provider.calls == []


def test_fred_quality_uses_macro_provider(
    client: TestClient, history_provider: FakeHistoryProvider, macro_provider: FakeMacroProvider
) -> None:
    response = client.get(
        "/api/v1/instruments/macro:FRED:DGS10/quality",
        params={"start": "2020-01-02", "end": "2020-01-08"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["instrument_id"] == "macro:FRED:DGS10"
    assert body["source"] == "fred"
    assert body["source_symbol"] == "DGS10"
    assert body["unit"] == "percent"
    assert body["missing_count"] == 1
    assert body["content_hash"] == content_hash(macro_provider.series)
    assert history_provider.calls == []
    assert macro_provider.calls == [("macro:FRED:DGS10", "DGS10", date(2020, 1, 2), date(2020, 1, 8))]


def test_quality_dual_mounted_on_legacy_and_v1(client: TestClient) -> None:
    params = {"start": "2021-01-04", "end": "2021-01-08"}
    legacy = client.get("/instruments/equity:US:AAPL/quality", params=params)
    versioned = client.get("/api/v1/instruments/equity:US:AAPL/quality", params=params)
    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert legacy.json()["content_hash"] == versioned.json()["content_hash"]


@pytest.mark.parametrize(
    ("exc", "status_code", "code"),
    [
        (UnavailableError("provider unavailable"), 503, "unavailable"),
        (RateLimitedError("provider rate limited"), 429, "rate_limited"),
        (AuthorizationError("provider authorization failed"), 401, "authorization"),
        (NotFoundError("provider resource not found"), 404, "not_found"),
        (MalformedResponseError("provider returned malformed JSON"), 502, "malformed_response"),
    ],
)
def test_quality_provider_errors_map_to_error_envelope(
    client: TestClient,
    history_provider: FakeHistoryProvider,
    exc: Exception,
    status_code: int,
    code: str,
) -> None:
    history_provider.error = exc
    response = client.get(
        "/api/v1/instruments/equity:US:AAPL/quality",
        params={"start": "2021-01-04", "end": "2021-01-08"},
    )
    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert "traceback" not in response.text.lower()


def test_quality_response_never_includes_fred_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "super-secret-fred-key")
    response = client.get(
        "/api/v1/instruments/macro:FRED:DGS10/quality",
        params={"start": "2020-01-02", "end": "2020-01-08"},
    )
    assert response.status_code == 200
    assert "super-secret-fred-key" not in response.text
    assert "FRED_API_KEY" not in response.text
    assert os.environ["FRED_API_KEY"] == "super-secret-fred-key"
