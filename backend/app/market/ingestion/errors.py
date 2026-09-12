"""Provider error taxonomy for public-data ingestion (not FastAPI)."""

from __future__ import annotations


class ProviderError(Exception):
    """Base adapter failure. ``code`` is the stable taxonomy token."""

    code = "unavailable"

    def __init__(self, message: str = "") -> None:
        super().__init__(message)


class UnavailableError(ProviderError):
    code = "unavailable"


class AuthorizationError(ProviderError):
    code = "authorization"


class NotFoundError(ProviderError):
    code = "not_found"


class RateLimitedError(ProviderError):
    code = "rate_limited"


class MalformedResponseError(ProviderError):
    code = "malformed_response"


class InsufficientHistoryError(ProviderError):
    code = "insufficient_history"
