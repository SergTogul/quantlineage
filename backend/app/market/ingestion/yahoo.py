"""Yahoo Finance public JSON adapter (search + daily adjusted history)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.market.ingestion.errors import (
    InsufficientHistoryError,
    MalformedResponseError,
    NotFoundError,
)
from app.market.ingestion.http import new_client, request_json
from app.market.ingestion.models import (
    NORMALIZATION_VERSION,
    DataQualitySummary,
    DataSourceMetadata,
    Frequency,
    HistoricalSeries,
    InstrumentCandidate,
    InstrumentRef,
)
from app.market.ingestion.normalize import collect_points, is_stale, parse_observation_value

YAHOO_BASE = "https://query1.finance.yahoo.com"
_HISTORY_TYPES = frozenset({"equity", "etf"})
_US_EXCHANGES = frozenset(
    {
        "NMS",
        "NYQ",
        "NGM",
        "NCM",
        "ASE",
        "PCX",
        "BTS",
        "NAS",
        "NYSE",
        "NASDAQ",
        "NYSEARCA",
        "AMEX",
        "ARCA",
    }
)
_QUOTE_TYPE_MAP = {
    "EQUITY": "equity",
    "ETF": "etf",
    "INDEX": "index",
    "MUTUALFUND": "mutual_fund",
    "CRYPTOCURRENCY": "crypto",
    "CURRENCY": "fx",
    "FUTURE": "future",
    "OPTION": "option",
}


class YahooFinanceAdapter:
    """InstrumentSearchProvider + HistoricalDataProvider for public Yahoo JSON."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client if client is not None else new_client()

    def search(
        self, query: str, *, asset_types: set[str] | None = None
    ) -> list[InstrumentCandidate]:
        payload = request_json(
            self._client,
            "GET",
            f"{YAHOO_BASE}/v1/finance/search",
            params={"q": query},
        )
        quotes = _require_list(payload, "quotes")
        hits: list[InstrumentCandidate] = []
        for raw in quotes:
            candidate = _candidate_from_quote(raw)
            if candidate is None:
                continue
            if asset_types is not None and candidate.asset_type not in asset_types:
                continue
            hits.append(candidate)
        return hits

    def fetch_history(
        self,
        instrument: InstrumentRef,
        *,
        start: date,
        end: date,
        frequency: Frequency,
    ) -> HistoricalSeries:
        _ = frequency  # Wave A Yahoo chart is always daily adjusted close.
        symbol = _source_symbol(instrument.instrument_id)
        period1 = _unix_utc(start)
        period2 = _unix_utc(end) + 86400
        payload = request_json(
            self._client,
            "GET",
            f"{YAHOO_BASE}/v8/finance/chart/{quote(symbol, safe='')}",
            params={
                "interval": "1d",
                "period1": str(period1),
                "period2": str(period2),
                "includeAdjustedClose": "true",
            },
        )
        timestamps, adj_close, currency = _chart_series(payload)
        rows: list[tuple[date, float | None]] = []
        for ts, raw_value in zip(timestamps, adj_close, strict=True):
            try:
                observation_date = datetime.fromtimestamp(int(ts), UTC).date()
            except (TypeError, ValueError, OverflowError, OSError):
                raise MalformedResponseError("provider returned malformed JSON") from None
            if observation_date < start or observation_date > end:
                continue
            rows.append((observation_date, parse_observation_value(raw_value)))
        points, missing, duplicates = collect_points(rows)
        if not points:
            raise InsufficientHistoryError("no usable adjusted-close observations")
        retrieved_at = datetime.now(UTC)
        last = points[-1].observation_date
        metadata = DataSourceMetadata(
            source="yahoo",
            source_symbol=symbol,
            unit="price",
            currency=currency or instrument.currency,
            frequency=Frequency.DAILY,
            adjustment="adjusted",
            retrieved_at=retrieved_at,
            first_observation=points[0].observation_date,
            last_observation=last,
            observation_count=len(points),
            normalization_version=NORMALIZATION_VERSION,
        )
        quality = DataQualitySummary(
            missing_count=missing,
            duplicate_count=duplicates,
            stale=is_stale(last_observation=last, requested_end=end, retrieved_at=retrieved_at),
        )
        return HistoricalSeries(
            instrument=instrument,
            points=points,
            metadata=metadata,
            quality=quality,
        )


def _unix_utc(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


def _source_symbol(instrument_id: str) -> str:
    symbol = instrument_id.rsplit(":", 1)[-1].strip()
    if not symbol:
        raise MalformedResponseError("instrument_id missing source symbol")
    return symbol


def _require_list(payload: Any, key: str) -> list[Any]:
    if not isinstance(payload, dict):
        raise MalformedResponseError("provider returned malformed JSON")
    value = payload.get(key)
    if value is None:
        raise MalformedResponseError("provider returned malformed JSON")
    if not isinstance(value, list):
        raise MalformedResponseError("provider returned malformed JSON")
    return value


def _candidate_from_quote(raw: Any) -> InstrumentCandidate | None:
    if not isinstance(raw, dict):
        return None
    symbol = raw.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        return None
    symbol = symbol.strip().upper()
    quote_type = raw.get("quoteType")
    asset_type = _QUOTE_TYPE_MAP.get(str(quote_type).upper() if quote_type else "", "unknown")
    exchange = str(raw.get("exchange") or "").upper()
    region = "US" if (not exchange or exchange in _US_EXCHANGES) else exchange
    currency = raw.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        currency = "USD"
    display = raw.get("longname") or raw.get("shortname") or symbol
    if not isinstance(display, str) or not display.strip():
        display = symbol
    return InstrumentCandidate(
        instrument_id=f"{asset_type}:{region}:{symbol}",
        display_name=display.strip(),
        provider="yahoo",
        source_symbol=symbol,
        asset_type=asset_type,
        currency=currency.strip().upper(),
        supported_for_history=asset_type in _HISTORY_TYPES,
    )


def _chart_series(payload: Any) -> tuple[list[Any], list[Any], str | None]:
    if not isinstance(payload, dict):
        raise MalformedResponseError("provider returned malformed JSON")
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise MalformedResponseError("provider returned malformed JSON")
    result = chart.get("result")
    error = chart.get("error")
    if error and not result:
        raise NotFoundError("provider resource not found")
    if not isinstance(result, list) or not result:
        raise NotFoundError("provider resource not found")
    first = result[0]
    if not isinstance(first, dict):
        raise MalformedResponseError("provider returned malformed JSON")
    timestamps = first.get("timestamp")
    if not isinstance(timestamps, list):
        raise MalformedResponseError("provider returned malformed JSON")
    indicators = first.get("indicators")
    if not isinstance(indicators, dict):
        raise MalformedResponseError("provider returned malformed JSON")
    adj_block = indicators.get("adjclose")
    if not isinstance(adj_block, list) or not adj_block or not isinstance(adj_block[0], dict):
        raise MalformedResponseError("provider returned malformed JSON")
    adj_close = adj_block[0].get("adjclose")
    if not isinstance(adj_close, list):
        raise MalformedResponseError("provider returned malformed JSON")
    if len(adj_close) != len(timestamps):
        raise MalformedResponseError("provider returned malformed JSON")
    meta = first.get("meta") if isinstance(first.get("meta"), dict) else {}
    currency = meta.get("currency") if isinstance(meta, dict) else None
    if isinstance(currency, str):
        currency = currency.strip().upper() or None
    else:
        currency = None
    return timestamps, adj_close, currency
