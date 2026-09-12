"""G1: FRED adapter — fixture HTTP via httpx.MockTransport."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import httpx
import pytest

Handler = Callable[[httpx.Request], httpx.Response]

from app.market.ingestion.errors import (
    AuthorizationError,
    InsufficientHistoryError,
    MalformedResponseError,
    NotFoundError,
    RateLimitedError,
    UnavailableError,
)
from app.market.ingestion.fred import FredAdapter
from app.market.ingestion.models import MacroSeriesRef

_DGS10 = MacroSeriesRef(instrument_id="macro:FRED:DGS10", series_id="DGS10", currency="USD")
_START = date(2020, 1, 2)
_END = date(2020, 1, 6)
_SECRET = "super-secret-fred-key"

_OBS_DGS10 = {
    "observations": [
        {"date": "2020-01-02", "value": "1.88"},
        {"date": "2020-01-03", "value": "."},
        {"date": "2020-01-06", "value": "1.81"},
    ]
}


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)


def _fred(handler: Handler, *, api_key: str = _SECRET) -> FredAdapter:
    return FredAdapter(client=_client(handler), api_key=api_key)


def test_fred_valid_series_parses_percent_levels() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.stlouisfed.org"
        assert request.url.path == "/fred/series/observations"
        assert request.url.params.get("series_id") == "DGS10"
        assert request.url.params.get("file_type") == "json"
        assert request.url.params.get("api_key") == _SECRET
        assert request.url.params.get("observation_start") == "2020-01-02"
        assert request.url.params.get("observation_end") == "2020-01-06"
        return httpx.Response(200, json=_OBS_DGS10)

    series = _fred(handler).fetch_series(_DGS10, start=_START, end=_END)
    assert [p.value for p in series.points] == [1.88, 1.81]
    assert [p.observation_date for p in series.points] == [date(2020, 1, 2), date(2020, 1, 6)]
    assert series.metadata.unit == "percent"
    assert series.metadata.source == "fred"
    assert series.metadata.source_symbol == "DGS10"
    assert series.metadata.currency == "USD"
    assert series.metadata.normalization_version == "wave-a-v1"
    assert series.instrument.instrument_id == "macro:FRED:DGS10"
    assert series.instrument.asset_type == "macro"


def test_fred_dot_is_missing_not_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OBS_DGS10)

    series = _fred(handler).fetch_series(_DGS10, start=_START, end=_END)
    assert 0.0 not in [p.value for p in series.points]
    assert series.quality.missing_count == 1
    assert series.metadata.observation_count == 2


def test_fred_malformed_value_fails_closed() -> None:
    payload = {"observations": [{"date": "2020-01-02", "value": "n/a"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(MalformedResponseError) as exc:
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)
    assert exc.value.code == "malformed_response"


def test_fred_429_is_rate_limited_without_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error_message": "Too Many Requests"})

    with pytest.raises(RateLimitedError) as exc:
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)
    assert exc.value.code == "rate_limited"
    assert calls["n"] == 1
    assert _SECRET not in str(exc.value)
    assert _SECRET not in repr(exc.value)


def test_fred_5xx_retries_then_unavailable() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="error")

    with pytest.raises(UnavailableError):
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)
    assert calls["n"] == 3


def test_fred_timeout_retries_then_unavailable() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("timed out")

    with pytest.raises(UnavailableError) as exc:
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)
    assert calls["n"] == 3
    assert _SECRET not in str(exc.value)


def test_fred_403_is_authorization_without_leaking_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error_code": 403, "error_message": "Invalid API Key."})

    with pytest.raises(AuthorizationError) as exc:
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)
    assert _SECRET not in str(exc.value)
    assert _SECRET not in repr(exc.value)
    assert "api_key=" not in str(exc.value).lower()


def test_fred_missing_api_key_is_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call FRED without a key")

    adapter = FredAdapter(client=_client(handler), api_key=None)
    with pytest.raises(AuthorizationError) as exc:
        adapter.fetch_series(_DGS10, start=_START, end=_END)
    assert "api_key" not in str(exc.value).lower() or "missing" in str(exc.value).lower()


def test_fred_series_does_not_exist_is_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error_code": 400, "error_message": "Bad Request.  The series does not exist."},
        )

    with pytest.raises(NotFoundError):
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)


def test_fred_http_404_is_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    with pytest.raises(NotFoundError):
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)


def test_fred_empty_observations_is_insufficient_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": []})

    with pytest.raises(InsufficientHistoryError):
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)


def test_fred_invalid_json_is_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    with pytest.raises(MalformedResponseError):
        _fred(handler).fetch_series(_DGS10, start=_START, end=_END)
