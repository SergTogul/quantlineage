"""Instrument catalog search and quality routes (QuantLineage Wave A)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.errors import error_payload
from app.market.catalog import CatalogRecord, CatalogSearchHit, get_catalog_record, search_catalog
from app.market.ingestion.errors import ProviderError
from app.market.ingestion.fred import FredAdapter
from app.market.ingestion.models import Frequency, InstrumentRef, MacroSeriesRef
from app.market.ingestion.protocols import HistoricalDataProvider, InstrumentSearchProvider, MacroDataProvider
from app.market.ingestion.yahoo import YahooFinanceAdapter
from app.market.quality import SeriesLineage, SeriesValidationError, validate_series

router = APIRouter(tags=["instruments"])

_EQUITY_ETF_TYPES = frozenset({"equity", "etf"})

_PROVIDER_STATUS: dict[str, int] = {
    "unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "authorization": status.HTTP_401_UNAUTHORIZED,
    "not_found": status.HTTP_404_NOT_FOUND,
    "malformed_response": status.HTTP_502_BAD_GATEWAY,
    "insufficient_history": status.HTTP_502_BAD_GATEWAY,
}

_PROVIDER_MESSAGES: dict[str, str] = {
    "unavailable": "Search provider unavailable",
    "rate_limited": "Search provider rate limited",
    "authorization": "Search provider authorization failed",
    "not_found": "Search provider resource not found",
    "malformed_response": "Search provider returned a malformed response",
    "insufficient_history": "Search provider returned insufficient history",
}


def get_search_provider() -> InstrumentSearchProvider:
    """Default Yahoo public-JSON search. Tests inject a fake provider."""
    return YahooFinanceAdapter()


def get_history_provider() -> HistoricalDataProvider:
    """Default Yahoo history. Tests inject a fake provider."""
    return YahooFinanceAdapter()


def get_macro_provider() -> MacroDataProvider:
    """Default FRED series. Tests inject a fake provider."""
    return FredAdapter()


def _provider_http_error(exc: ProviderError) -> HTTPException:
    code = getattr(exc, "code", "unavailable") or "unavailable"
    status_code = _PROVIDER_STATUS.get(code, status.HTTP_503_SERVICE_UNAVAILABLE)
    message = _PROVIDER_MESSAGES.get(code, "Search provider unavailable")
    return HTTPException(
        status_code=status_code,
        detail=error_payload(code=code, message=message, details=None),
    )


def _parse_query_date(raw: str | None, *, field: str) -> date:
    token = (raw or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(code="bad_request", message=f"Invalid {field} date", details=None),
        )
    try:
        return date.fromisoformat(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(code="bad_request", message=f"Invalid {field} date", details=None),
        ) from None


def _fetch_catalog_series(
    record: CatalogRecord,
    *,
    start: date,
    end: date,
    history_provider: HistoricalDataProvider,
    macro_provider: MacroDataProvider,
):
    if record.asset_type in _EQUITY_ETF_TYPES:
        instrument = InstrumentRef(
            instrument_id=record.instrument_id,
            asset_type=record.asset_type,
            currency=record.currency,
        )
        return history_provider.fetch_history(
            instrument, start=start, end=end, frequency=Frequency.DAILY
        )
    if record.asset_type == "macro":
        mapping = record.provider_mappings[0]
        return macro_provider.fetch_series(
            MacroSeriesRef(
                instrument_id=record.instrument_id,
                series_id=mapping.source_symbol,
                currency=record.currency,
            ),
            start=start,
            end=end,
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_payload(code="bad_request", message="Unsupported asset type", details=None),
    )


@router.get("/instruments/search", response_model=list[CatalogSearchHit])
def search_instruments(
    q: str = Query(default=""),
    provider: InstrumentSearchProvider = Depends(get_search_provider),
) -> list[CatalogSearchHit]:
    """Search the curated universe, merged with injected provider hits."""
    if not q.strip():
        return []
    result = search_catalog(q, provider=provider)
    if not result.hits and result.provider_error is not None:
        raise _provider_http_error(result.provider_error)
    return result.hits


@router.get("/instruments/{instrument_id}/quality", response_model=SeriesLineage)
def get_instrument_quality(
    instrument_id: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    history_provider: HistoricalDataProvider = Depends(get_history_provider),
    macro_provider: MacroDataProvider = Depends(get_macro_provider),
) -> SeriesLineage:
    """Validate fetched history and return series lineage plus quality fields."""
    start_date = _parse_query_date(start, field="start")
    end_date = _parse_query_date(end, field="end")
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(code="bad_request", message="start must be on or before end", details=None),
        )
    record = get_catalog_record(instrument_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_payload(code="not_found", message="Instrument not found", details=None),
        )
    try:
        series = _fetch_catalog_series(
            record,
            start=start_date,
            end=end_date,
            history_provider=history_provider,
            macro_provider=macro_provider,
        )
        return validate_series(series, requested_end=end_date)
    except ProviderError as exc:
        raise _provider_http_error(exc) from None
    except SeriesValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(code=exc.code, message="Invalid series", details=None),
        ) from None
