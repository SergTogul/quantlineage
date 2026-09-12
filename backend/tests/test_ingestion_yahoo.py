"""G1: Yahoo Finance adapter — fixture HTTP via httpx.MockTransport."""

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
from app.market.ingestion.models import Frequency, InstrumentRef
from app.market.ingestion.yahoo import YahooFinanceAdapter

_AAPL = InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD")
_START = date(2021, 1, 4)
_END = date(2021, 1, 6)

_SEARCH_AAPL = {
    "quotes": [
        {
            "symbol": "AAPL",
            "shortname": "Apple Inc.",
            "longname": "Apple Inc.",
            "quoteType": "EQUITY",
            "exchange": "NMS",
            "currency": "USD",
        },
        {
            "symbol": "SPY",
            "shortname": "SPDR S&P 500 ETF Trust",
            "quoteType": "ETF",
            "exchange": "PCX",
            "currency": "USD",
        },
    ]
}

_CHART_AAPL = {
    "chart": {
        "result": [
            {
                "meta": {"currency": "USD", "symbol": "AAPL", "instrumentType": "EQUITY"},
                "timestamp": [1609718400, 1609804800, 1609891200],
                "indicators": {
                    "quote": [{"close": [100.0, 101.0, 102.0], "open": [99.0, 100.0, 101.0]}],
                    "adjclose": [{"adjclose": [129.41, 130.12, None]}],
                },
            }
        ],
        "error": None,
    }
}


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)


def _yahoo(handler: Handler) -> YahooFinanceAdapter:
    return YahooFinanceAdapter(client=_client(handler))


def test_yahoo_valid_search_maps_equity_and_etf_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "query1.finance.yahoo.com"
        assert request.url.path == "/v1/finance/search"
        assert request.url.params.get("q") == "AAPL"
        return httpx.Response(200, json=_SEARCH_AAPL)

    hits = _yahoo(handler).search("AAPL")
    assert [h.instrument_id for h in hits] == ["equity:US:AAPL", "etf:US:SPY"]
    apple = hits[0]
    assert apple.display_name == "Apple Inc."
    assert apple.provider == "yahoo"
    assert apple.source_symbol == "AAPL"
    assert apple.asset_type == "equity"
    assert apple.currency == "USD"
    assert apple.supported_for_history is True
    assert apple.supported_for_snapshot is False
    assert apple.supported_for_risk_factor is False
    spy = hits[1]
    assert spy.asset_type == "etf"
    assert spy.supported_for_history is True


def test_yahoo_search_filters_asset_types() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SEARCH_AAPL)

    hits = _yahoo(handler).search("AAPL", asset_types={"etf"})
    assert [h.instrument_id for h in hits] == ["etf:US:SPY"]


def test_yahoo_empty_search_returns_empty_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"quotes": []})

    assert _yahoo(handler).search("ZZZZZZZZ") == []


def test_yahoo_history_uses_adjusted_close_not_raw_close() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "query1.finance.yahoo.com"
        assert request.url.path == "/v8/finance/chart/AAPL"
        assert request.url.params.get("interval") == "1d"
        assert "adjclose" in str(request.url).lower() or request.url.params.get(
            "includeAdjustedClose"
        ) in {"true", "True", "1"}
        return httpx.Response(200, json=_CHART_AAPL)

    series = _yahoo(handler).fetch_history(
        _AAPL, start=_START, end=_END, frequency=Frequency.DAILY
    )
    assert [p.value for p in series.points] == [129.41, 130.12]
    assert [p.observation_date for p in series.points] == [date(2021, 1, 4), date(2021, 1, 5)]
    assert series.metadata.unit == "price"
    assert series.metadata.adjustment == "adjusted"
    assert series.metadata.source == "yahoo"
    assert series.metadata.source_symbol == "AAPL"
    assert series.metadata.currency == "USD"
    assert series.metadata.frequency == Frequency.DAILY
    assert series.metadata.normalization_version == "wave-a-v1"
    assert series.metadata.observation_count == 2
    assert series.metadata.first_observation == date(2021, 1, 4)
    assert series.metadata.last_observation == date(2021, 1, 5)
    assert series.quality.missing_count == 1
    assert series.instrument.instrument_id == "equity:US:AAPL"


def test_yahoo_malformed_adjclose_fails_closed() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "USD", "symbol": "AAPL"},
                    "timestamp": [1609718400],
                    "indicators": {"adjclose": [{"adjclose": ["not-a-number"]}]},
                }
            ],
            "error": None,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(MalformedResponseError) as exc:
        _yahoo(handler).fetch_history(_AAPL, start=_START, end=_END, frequency=Frequency.DAILY)
    assert exc.value.code == "malformed_response"


def test_yahoo_missing_adjclose_block_is_malformed() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "USD", "symbol": "AAPL"},
                    "timestamp": [1609718400],
                    "indicators": {"quote": [{"close": [100.0]}]},
                }
            ],
            "error": None,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(MalformedResponseError):
        _yahoo(handler).fetch_history(_AAPL, start=_START, end=_END, frequency=Frequency.DAILY)


def test_yahoo_429_is_rate_limited_without_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"finance": {"error": "Too Many Requests"}})

    with pytest.raises(RateLimitedError) as exc:
        _yahoo(handler).search("AAPL")
    assert exc.value.code == "rate_limited"
    assert calls["n"] == 1


def test_yahoo_5xx_retries_then_unavailable() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="unavailable")

    with pytest.raises(UnavailableError) as exc:
        _yahoo(handler).search("AAPL")
    assert exc.value.code == "unavailable"
    assert calls["n"] == 3


def test_yahoo_5xx_then_success_uses_bounded_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=_SEARCH_AAPL)

    hits = _yahoo(handler).search("AAPL")
    assert len(hits) == 2
    assert calls["n"] == 3


def test_yahoo_timeout_retries_then_unavailable() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("timed out")

    with pytest.raises(UnavailableError):
        _yahoo(handler).search("AAPL")
    assert calls["n"] == 3


def test_yahoo_401_is_authorization() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(AuthorizationError):
        _yahoo(handler).search("AAPL")


def test_yahoo_404_is_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    with pytest.raises(NotFoundError):
        _yahoo(handler).fetch_history(_AAPL, start=_START, end=_END, frequency=Frequency.DAILY)


def test_yahoo_chart_error_body_is_not_found() -> None:
    payload = {
        "chart": {
            "result": None,
            "error": {"code": "Not Found", "description": "No data found, symbol may be delisted"},
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(NotFoundError):
        _yahoo(handler).fetch_history(_AAPL, start=_START, end=_END, frequency=Frequency.DAILY)


def test_yahoo_empty_usable_points_is_insufficient_history() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "USD", "symbol": "AAPL"},
                    "timestamp": [1609718400],
                    "indicators": {"adjclose": [{"adjclose": [None]}]},
                }
            ],
            "error": None,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(InsufficientHistoryError) as exc:
        _yahoo(handler).fetch_history(_AAPL, start=_START, end=_END, frequency=Frequency.DAILY)
    assert exc.value.code == "insufficient_history"


def test_yahoo_invalid_json_is_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>nope</html>")

    with pytest.raises(MalformedResponseError):
        _yahoo(handler).search("AAPL")
