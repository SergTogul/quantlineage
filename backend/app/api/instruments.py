"""Instrument catalog search routes (QuantLineage Wave A / G2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.errors import error_payload
from app.market.catalog import CatalogSearchHit, search_catalog
from app.market.ingestion.errors import ProviderError
from app.market.ingestion.protocols import InstrumentSearchProvider
from app.market.ingestion.yahoo import YahooFinanceAdapter

router = APIRouter(tags=["instruments"])

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


def _provider_http_error(exc: ProviderError) -> HTTPException:
    code = getattr(exc, "code", "unavailable") or "unavailable"
    status_code = _PROVIDER_STATUS.get(code, status.HTTP_503_SERVICE_UNAVAILABLE)
    message = _PROVIDER_MESSAGES.get(code, "Search provider unavailable")
    return HTTPException(
        status_code=status_code,
        detail=error_payload(code=code, message=message, details=None),
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
