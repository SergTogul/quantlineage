"""Shared HTTP helpers for ingestion adapters. Never log secrets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.market.ingestion.errors import (
    AuthorizationError,
    MalformedResponseError,
    NotFoundError,
    ProviderError,
    RateLimitedError,
    UnavailableError,
)

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 2
_USER_AGENT = "RiskForge/wave-a (public-data ingestion)"


def new_client() -> httpx.Client:
    return httpx.Client(timeout=DEFAULT_TIMEOUT, headers={"User-Agent": _USER_AGENT})


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: Mapping[str, str] | None = None,
) -> Any:
    """GET/POST JSON with bounded retry for timeout/5xx. Never retries 429."""
    attempts = MAX_RETRIES + 1
    for attempt in range(attempts):
        try:
            response = client.request(method, url, params=params)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt >= attempts - 1:
                raise UnavailableError("provider unavailable") from None
            continue
        status = response.status_code
        if status >= 500:
            if attempt >= attempts - 1:
                raise UnavailableError("provider unavailable") from None
            continue
        if status == 429:
            raise RateLimitedError("provider rate limited")
        if status in {401, 403}:
            raise AuthorizationError("provider authorization failed")
        if status == 404:
            raise NotFoundError("provider resource not found")
        if status >= 400:
            raise _unexpected_client_error(response)
        try:
            return response.json()
        except ValueError:
            raise MalformedResponseError("provider returned malformed JSON") from None
    raise UnavailableError("provider unavailable")


def _unexpected_client_error(response: httpx.Response) -> ProviderError:
    payload: Any = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    message = ""
    if isinstance(payload, dict):
        raw = payload.get("error_message") or payload.get("message")
        if isinstance(raw, str):
            message = raw
    if "does not exist" in message.lower():
        return NotFoundError("provider resource not found")
    return MalformedResponseError("provider returned an unexpected error response")
