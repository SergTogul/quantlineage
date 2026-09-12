"""G6: QuantLineage product API — history, freeze, snapshot (fake providers, no live network)."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.instruments import get_history_provider, get_macro_provider
from app.main import app
from app.market.history.spec import WAVE_A_DATASET_ID
from app.market.ingestion.errors import NotFoundError, RateLimitedError, UnavailableError
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

MAX_HISTORY_DAYS = 1826

_LEVEL_DATES = (
    date(2021, 1, 4),
    date(2021, 1, 5),
    date(2021, 1, 6),
    date(2021, 1, 7),
    date(2021, 1, 8),
    date(2021, 1, 11),
)
_FRIDAY = date(2024, 1, 5)
_MONDAY = date(2024, 1, 8)
_THURSDAY = date(2024, 1, 4)
_TUESDAY = date(2024, 1, 9)
_STALE_AS_OF = date(2024, 1, 22)

_EQUITY_LEVELS: dict[str, tuple[float, ...]] = {
    "equity:US:AAPL": (100.0, 101.0, 102.0, 103.0, 104.0, 105.0),
    "equity:US:MSFT": (200.0, 204.0, 208.0, 212.0, 216.0, 220.0),
    "equity:US:NVDA": (50.0, 51.0, 52.0, 53.0, 54.0, 55.0),
    "equity:US:SPY": (400.0, 402.0, 404.0, 406.0, 408.0, 410.0),
}
_RATE_LEVELS: dict[str, tuple[float, ...]] = {
    "macro:FRED:DGS2": (4.25, 4.30, 4.35, 4.40, 4.45, 4.50),
    "macro:FRED:DGS5": (4.00, 4.02, 4.04, 4.06, 4.08, 4.10),
    "macro:FRED:DGS10": (1.00, 1.10, 1.20, 1.30, 1.40, 1.50),
}
_EQUITY_FRIDAY: dict[str, float] = {
    "equity:US:AAPL": 185.0,
    "equity:US:MSFT": 370.0,
    "equity:US:NVDA": 480.0,
    "equity:US:SPY": 470.0,
}
_EQUITY_THURSDAY: dict[str, float] = {
    "equity:US:AAPL": 180.0,
    "equity:US:MSFT": 360.0,
    "equity:US:NVDA": 470.0,
    "equity:US:SPY": 460.0,
}
_RATE_FRIDAY: dict[str, float] = {
    "macro:FRED:DGS2": 4.10,
    "macro:FRED:DGS5": 4.15,
    "macro:FRED:DGS10": 4.25,
}
_RATE_THURSDAY: dict[str, float] = {
    "macro:FRED:DGS2": 4.05,
    "macro:FRED:DGS5": 4.12,
    "macro:FRED:DGS10": 4.20,
}


class FakeHistoryProvider:
    def __init__(
        self,
        series: HistoricalSeries | None = None,
        catalog: dict[str, HistoricalSeries] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.series = series
        self.catalog = catalog
        self.error = error
        self.calls: list[tuple[str, date, date, Frequency]] = []

    def fetch_history(
        self, instrument: InstrumentRef, *, start: date, end: date, frequency: Frequency
    ) -> HistoricalSeries:
        self.calls.append((instrument.instrument_id, start, end, frequency))
        if self.error is not None:
            raise self.error
        if self.catalog is not None:
            found = self.catalog.get(instrument.instrument_id)
            if found is None:
                raise NotFoundError(instrument.instrument_id)
            return found
        assert self.series is not None
        return self.series


class FakeMacroProvider:
    def __init__(
        self,
        series: HistoricalSeries | None = None,
        catalog: dict[str, HistoricalSeries] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.series = series
        self.catalog = catalog
        self.error = error
        self.calls: list[tuple[str, str, date, date]] = []

    def fetch_series(self, series: MacroSeriesRef, *, start: date, end: date) -> HistoricalSeries:
        self.calls.append((series.instrument_id, series.series_id, start, end))
        if self.error is not None:
            raise self.error
        if self.catalog is not None:
            found = self.catalog.get(series.instrument_id)
            if found is None:
                raise NotFoundError(series.instrument_id)
            return found
        assert self.series is not None
        return self.series


def _points(*pairs: tuple[str, float]) -> list[HistoricalPoint]:
    return [HistoricalPoint(observation_date=date.fromisoformat(day), value=value) for day, value in pairs]


def _metadata(
    *,
    source: str,
    source_symbol: str,
    unit: str,
    adjustment: str,
    points: list[HistoricalPoint],
) -> DataSourceMetadata:
    return DataSourceMetadata(
        source=source,
        source_symbol=source_symbol,
        unit=unit,
        currency="USD",
        frequency=Frequency.DAILY,
        adjustment=adjustment,
        retrieved_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        first_observation=points[0].observation_date if points else None,
        last_observation=points[-1].observation_date if points else None,
        observation_count=len(points),
        normalization_version=NORMALIZATION_VERSION,
    )


def _series(
    *,
    instrument_id: str,
    asset_type: str,
    source: str,
    source_symbol: str,
    unit: str,
    adjustment: str,
    pairs: list[tuple[date, float]],
) -> HistoricalSeries:
    points = [HistoricalPoint(observation_date=day, value=value) for day, value in pairs]
    return HistoricalSeries(
        instrument=InstrumentRef(instrument_id=instrument_id, asset_type=asset_type, currency="USD"),
        points=points,
        metadata=_metadata(
            source=source,
            source_symbol=source_symbol,
            unit=unit,
            adjustment=adjustment,
            points=points,
        ),
        quality=DataQualitySummary(missing_count=0, duplicate_count=0, stale=False),
    )


def _aapl_series() -> HistoricalSeries:
    return HistoricalSeries(
        instrument=InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD"),
        points=_points(
            ("2021-01-04", 129.41),
            ("2021-01-05", 130.12),
            ("2021-01-06", 126.60),
            ("2021-01-07", 130.92),
            ("2021-01-08", 132.05),
        ),
        metadata=_metadata(
            source="yahoo",
            source_symbol="AAPL",
            unit="price",
            adjustment="adjusted",
            points=_points(
                ("2021-01-04", 129.41),
                ("2021-01-05", 130.12),
                ("2021-01-06", 126.60),
                ("2021-01-07", 130.92),
                ("2021-01-08", 132.05),
            ),
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
        metadata=_metadata(
            source="fred",
            source_symbol="DGS10",
            unit="percent",
            adjustment="unadjusted",
            points=points,
        ),
        quality=DataQualitySummary(missing_count=1, duplicate_count=0, stale=False),
    )


def _empty_aapl_series() -> HistoricalSeries:
    return HistoricalSeries(
        instrument=InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD"),
        points=[],
        metadata=DataSourceMetadata(
            source="yahoo",
            source_symbol="AAPL",
            unit="price",
            currency="USD",
            frequency=Frequency.DAILY,
            adjustment="adjusted",
            retrieved_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            first_observation=None,
            last_observation=None,
            observation_count=0,
            normalization_version=NORMALIZATION_VERSION,
        ),
        quality=DataQualitySummary(missing_count=0, duplicate_count=0, stale=False),
    )


def _freeze_equity_catalog() -> dict[str, HistoricalSeries]:
    symbols = {"equity:US:AAPL": "AAPL", "equity:US:MSFT": "MSFT", "equity:US:NVDA": "NVDA", "equity:US:SPY": "SPY"}
    catalog: dict[str, HistoricalSeries] = {}
    for instrument_id, symbol in symbols.items():
        pairs = list(zip(_LEVEL_DATES, _EQUITY_LEVELS[instrument_id], strict=True))
        catalog[instrument_id] = _series(
            instrument_id=instrument_id,
            asset_type="etf" if symbol == "SPY" else "equity",
            source="yahoo",
            source_symbol=symbol,
            unit="price",
            adjustment="adjusted",
            pairs=pairs,
        )
    return catalog


def _freeze_macro_catalog() -> dict[str, HistoricalSeries]:
    series_ids = {"macro:FRED:DGS2": "DGS2", "macro:FRED:DGS5": "DGS5", "macro:FRED:DGS10": "DGS10"}
    catalog: dict[str, HistoricalSeries] = {}
    for instrument_id, series_id in series_ids.items():
        pairs = list(zip(_LEVEL_DATES, _RATE_LEVELS[instrument_id], strict=True))
        catalog[instrument_id] = _series(
            instrument_id=instrument_id,
            asset_type="macro",
            source="fred",
            source_symbol=series_id,
            unit="percent",
            adjustment="none",
            pairs=pairs,
        )
    return catalog


def _snapshot_equity_catalog() -> dict[str, HistoricalSeries]:
    symbols = {"equity:US:AAPL": "AAPL", "equity:US:MSFT": "MSFT", "equity:US:NVDA": "NVDA", "equity:US:SPY": "SPY"}
    catalog: dict[str, HistoricalSeries] = {}
    for instrument_id, symbol in symbols.items():
        catalog[instrument_id] = _series(
            instrument_id=instrument_id,
            asset_type="etf" if symbol == "SPY" else "equity",
            source="yahoo",
            source_symbol=symbol,
            unit="price",
            adjustment="adjusted",
            pairs=[
                (_THURSDAY, _EQUITY_THURSDAY[instrument_id]),
                (_FRIDAY, _EQUITY_FRIDAY[instrument_id]),
                (_TUESDAY, _EQUITY_FRIDAY[instrument_id] + 5.0),
            ],
        )
    return catalog


def _snapshot_macro_catalog() -> dict[str, HistoricalSeries]:
    series_ids = {"macro:FRED:DGS2": "DGS2", "macro:FRED:DGS5": "DGS5", "macro:FRED:DGS10": "DGS10"}
    catalog: dict[str, HistoricalSeries] = {}
    for instrument_id, series_id in series_ids.items():
        catalog[instrument_id] = _series(
            instrument_id=instrument_id,
            asset_type="macro",
            source="fred",
            source_symbol=series_id,
            unit="percent",
            adjustment="none",
            pairs=[
                (_THURSDAY, _RATE_THURSDAY[instrument_id]),
                (_FRIDAY, _RATE_FRIDAY[instrument_id]),
            ],
        )
    return catalog


def _override_client(history: FakeHistoryProvider, macro: FakeMacroProvider):
    app.dependency_overrides[get_history_provider] = lambda: history
    app.dependency_overrides[get_macro_provider] = lambda: macro
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_history_provider, None)
        app.dependency_overrides.pop(get_macro_provider, None)


@pytest.fixture
def history_provider() -> FakeHistoryProvider:
    return FakeHistoryProvider(series=_aapl_series())


@pytest.fixture
def macro_provider() -> FakeMacroProvider:
    return FakeMacroProvider(series=_dgs10_series())


@pytest.fixture
def client(history_provider: FakeHistoryProvider, macro_provider: FakeMacroProvider):
    yield from _override_client(history_provider, macro_provider)


@pytest.fixture
def freeze_history() -> FakeHistoryProvider:
    return FakeHistoryProvider(catalog=_freeze_equity_catalog())


@pytest.fixture
def freeze_macro() -> FakeMacroProvider:
    return FakeMacroProvider(catalog=_freeze_macro_catalog())


@pytest.fixture
def freeze_client(freeze_history: FakeHistoryProvider, freeze_macro: FakeMacroProvider, tmp_path, monkeypatch: pytest.MonkeyPatch):
    csv_path = tmp_path / "real_public_wave_a.csv"
    monkeypatch.setenv("QUANTLINEAGE_PUBLIC_HISTORY_CSV", str(csv_path))
    yield from _override_client(freeze_history, freeze_macro)


@pytest.fixture
def snapshot_history() -> FakeHistoryProvider:
    return FakeHistoryProvider(catalog=_snapshot_equity_catalog())


@pytest.fixture
def snapshot_macro() -> FakeMacroProvider:
    return FakeMacroProvider(catalog=_snapshot_macro_catalog())


@pytest.fixture
def snapshot_client(snapshot_history: FakeHistoryProvider, snapshot_macro: FakeMacroProvider):
    yield from _override_client(snapshot_history, snapshot_macro)


def test_aapl_history_returns_normalized_points_and_lineage(
    client: TestClient, history_provider: FakeHistoryProvider, macro_provider: FakeMacroProvider
) -> None:
    series = history_provider.series
    assert series is not None
    expected = validate_series(series, requested_end=date(2021, 1, 8))
    response = client.get(
        "/api/v1/market/history/equity:US:AAPL",
        params={"start": "2021-01-04", "end": "2021-01-08"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["instrument_id"] == "equity:US:AAPL"
    assert body["source"] == "yahoo"
    assert body["source_symbol"] == "AAPL"
    assert body["unit"] == "price"
    assert body["content_hash"] == expected.content_hash
    assert body["content_hash"] == content_hash(series)
    assert body["normalization_version"] == NORMALIZATION_VERSION
    assert body["points"] == [
        {"observation_date": "2021-01-04", "value": 129.41},
        {"observation_date": "2021-01-05", "value": 130.12},
        {"observation_date": "2021-01-06", "value": 126.60},
        {"observation_date": "2021-01-07", "value": 130.92},
        {"observation_date": "2021-01-08", "value": 132.05},
    ]
    assert history_provider.calls == [
        ("equity:US:AAPL", date(2021, 1, 4), date(2021, 1, 8), Frequency.DAILY)
    ]
    assert macro_provider.calls == []
    assert "FRED_API_KEY" not in response.text


def test_fred_history_keeps_percent_levels(client: TestClient) -> None:
    response = client.get(
        "/api/v1/market/history/macro:FRED:DGS10",
        params={"start": "2020-01-02", "end": "2020-01-08"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unit"] == "percent"
    assert body["points"][0]["value"] == pytest.approx(1.88)
    assert body["points"][0]["value"] != pytest.approx(0.0188)


def test_unknown_instrument_history_is_404(client: TestClient, history_provider: FakeHistoryProvider) -> None:
    response = client.get(
        "/api/v1/market/history/equity:US:TSLA",
        params={"start": "2021-01-04", "end": "2021-01-08"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert history_provider.calls == []


def test_history_empty_series_is_not_found(client: TestClient, history_provider: FakeHistoryProvider) -> None:
    history_provider.series = _empty_aapl_series()
    response = client.get(
        "/api/v1/market/history/equity:US:AAPL",
        params={"start": "2021-01-04", "end": "2021-01-08"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_history_missing_dates_are_400(client: TestClient, history_provider: FakeHistoryProvider) -> None:
    response = client.get("/api/v1/market/history/equity:US:AAPL")
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
    assert history_provider.calls == []


def test_history_range_over_1826_days_is_400(client: TestClient, history_provider: FakeHistoryProvider) -> None:
    start = date(2018, 1, 1)
    end = start + timedelta(days=MAX_HISTORY_DAYS + 1)
    response = client.get(
        "/api/v1/market/history/equity:US:AAPL",
        params={"start": start.isoformat(), "end": end.isoformat()},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
    assert history_provider.calls == []


@pytest.mark.parametrize(
    ("exc", "status_code", "code"),
    [
        (UnavailableError("provider unavailable"), 503, "unavailable"),
        (RateLimitedError("provider rate limited"), 429, "rate_limited"),
    ],
)
def test_history_provider_errors_map_to_error_envelope(
    client: TestClient,
    history_provider: FakeHistoryProvider,
    exc: Exception,
    status_code: int,
    code: str,
) -> None:
    history_provider.error = exc
    response = client.get(
        "/api/v1/market/history/equity:US:AAPL",
        params={"start": "2021-01-04", "end": "2021-01-08"},
    )
    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert "traceback" not in response.text.lower()


def test_history_dual_mounted_on_legacy_and_v1(client: TestClient) -> None:
    params = {"start": "2021-01-04", "end": "2021-01-08"}
    legacy = client.get("/market/history/equity:US:AAPL", params=params)
    versioned = client.get("/api/v1/market/history/equity:US:AAPL", params=params)
    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert legacy.json()["content_hash"] == versioned.json()["content_hash"]


def test_history_response_never_includes_fred_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "super-secret-fred-key")
    response = client.get(
        "/api/v1/market/history/macro:FRED:DGS10",
        params={"start": "2020-01-02", "end": "2020-01-08"},
    )
    assert response.status_code == 200
    assert "super-secret-fred-key" not in response.text
    assert "FRED_API_KEY" not in response.text
    assert os.environ["FRED_API_KEY"] == "super-secret-fred-key"


def test_freeze_dataset_then_get_by_id(freeze_client: TestClient, tmp_path) -> None:
    created = freeze_client.post(
        "/api/v1/data/datasets",
        json={"start": "2021-01-04", "end": "2021-01-11"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["dataset_id"] == WAVE_A_DATASET_ID
    assert body["dataset_id"] == "real:public:wave-a"
    assert isinstance(body["dataset_version"], str) and body["dataset_version"]
    assert body["csv_path"] == "real_public_wave_a.csv"
    assert str(tmp_path) not in body["csv_path"]
    assert "FRED_API_KEY" not in created.text

    loaded = freeze_client.get(f"/api/v1/data/datasets/{WAVE_A_DATASET_ID}")
    assert loaded.status_code == 200
    sidecar = loaded.json()
    assert sidecar["dataset_id"] == WAVE_A_DATASET_ID
    assert sidecar["dataset_version"] == body["dataset_version"]
    assert "super-secret-fred-key" not in loaded.text


def test_get_dataset_missing_is_404(freeze_client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTLINEAGE_PUBLIC_HISTORY_CSV", str(tmp_path / "missing.csv"))
    response = freeze_client.get(f"/api/v1/data/datasets/{WAVE_A_DATASET_ID}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_get_unknown_dataset_id_is_404(freeze_client: TestClient) -> None:
    freeze_client.post("/api/v1/data/datasets", json={"start": "2021-01-04", "end": "2021-01-11"})
    response = freeze_client.get("/api/v1/data/datasets/real:public:other")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_freeze_insufficient_overlap_is_400(freeze_client: TestClient, freeze_history: FakeHistoryProvider) -> None:
    short = {
        instrument_id: series.model_copy(update={"points": series.points[:2]})
        for instrument_id, series in freeze_history.catalog.items()
    }
    freeze_history.catalog = short
    response = freeze_client.post(
        "/api/v1/data/datasets",
        json={"start": "2021-01-04", "end": "2021-01-11"},
    )
    assert response.status_code in {400, 422}
    body = response.json()
    assert body["code"] in {
        "insufficient_history",
        "insufficient_aligned_history",
        "insufficient_observations",
    }


def test_freeze_missing_factor_is_mapped(freeze_client: TestClient, freeze_history: FakeHistoryProvider) -> None:
    catalog = dict(freeze_history.catalog)
    catalog.pop("equity:US:AAPL")
    freeze_history.catalog = catalog
    response = freeze_client.post(
        "/api/v1/data/datasets",
        json={"start": "2021-01-04", "end": "2021-01-11"},
    )
    assert response.status_code in {400, 404, 422}
    body = response.json()
    assert body["code"] in {"missing_required_factor", "not_found"}
    assert "message" in body


def test_freeze_dataset_dual_mounted(freeze_client: TestClient) -> None:
    payload = {"start": "2021-01-04", "end": "2021-01-11"}
    legacy = freeze_client.post("/data/datasets", json=payload)
    assert legacy.status_code == 200
    versioned = freeze_client.get(f"/api/v1/data/datasets/{WAVE_A_DATASET_ID}")
    assert versioned.status_code == 200


def test_freeze_never_includes_fred_api_key(
    freeze_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "super-secret-fred-key")
    response = freeze_client.post(
        "/api/v1/data/datasets",
        json={"start": "2021-01-04", "end": "2021-01-11"},
    )
    assert response.status_code == 200
    assert "super-secret-fred-key" not in response.text
    assert "FRED_API_KEY" not in response.text


def test_build_public_snapshot_then_get(
    snapshot_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "super-secret-fred-key")
    created = snapshot_client.post(
        "/api/v1/market/snapshots/from-public-data",
        json={"as_of": "2024-01-08"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["id"] == "real:public:wave-a:2024-01-08"
    assert body["as_of"] == "2024-01-08"
    assert isinstance(body["content_hash"], str) and body["content_hash"]
    assert "lineage" in body
    assert body["lineage"]["marks"]["equity:US:AAPL"]["source_observation_date"] == "2024-01-05"
    assert "super-secret-fred-key" not in created.text

    loaded = snapshot_client.get(f"/api/v1/market/snapshots/{body['id']}")
    assert loaded.status_code == 200
    snapshot = loaded.json()
    assert snapshot["id"] == body["id"]
    assert snapshot["equity_spots"]["AAPL"] == pytest.approx(185.0)
    assert snapshot["key_rates"]["USD"]["10Y"] == pytest.approx(0.0425)
    assert snapshot["key_rates"]["USD"]["10Y"] != pytest.approx(4.25)
    assert "super-secret-fred-key" not in loaded.text
    assert "FRED_API_KEY" not in loaded.text


def test_public_snapshot_stale_fails_clearly(snapshot_client: TestClient) -> None:
    response = snapshot_client.post(
        "/api/v1/market/snapshots/from-public-data",
        json={"as_of": _STALE_AS_OF.isoformat()},
    )
    assert response.status_code in {400, 422}
    body = response.json()
    assert body["code"] in {"stale", "stale_observation"}
    assert isinstance(body["message"], str) and body["message"]


def test_get_unknown_snapshot_is_404(snapshot_client: TestClient) -> None:
    response = snapshot_client.get("/api/v1/market/snapshots/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_public_snapshot_dual_mounted(snapshot_client: TestClient) -> None:
    payload = {"as_of": "2024-01-08"}
    legacy = snapshot_client.post("/market/snapshots/from-public-data", json=payload)
    versioned = snapshot_client.post("/api/v1/market/snapshots/from-public-data", json=payload)
    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert legacy.json()["content_hash"] == versioned.json()["content_hash"]
