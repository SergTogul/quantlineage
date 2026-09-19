"""Typed errors for the OpenAI risk assistant adapter."""

from __future__ import annotations

import re
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"Authorization:\s*[^\s,;]+", re.IGNORECASE),
)


class OpenAIProviderError(Exception):
    """Base adapter failure. ``code`` is a stable taxonomy token."""

    code = "provider_error"
    retryable = False

    def __init__(self, message: str = "") -> None:
        super().__init__(message)


class OpenAIModelParseError(OpenAIProviderError):
    """Malformed or unsupported model output."""

    code = "model_parse"


class OpenAIMultipleToolCallsError(OpenAIModelParseError):
    code = "multiple_tool_calls"


class OpenAIMalformedToolArgumentsError(OpenAIModelParseError):
    code = "malformed_tool_arguments"


class OpenAIIncompleteResponseError(OpenAIModelParseError):
    code = "incomplete_response"


class OpenAITransientProviderError(OpenAIProviderError):
    """Retryable SDK or network failures."""

    retryable = True


class OpenAITimeoutError(OpenAITransientProviderError):
    code = "timeout"


class OpenAIRateLimitError(OpenAITransientProviderError):
    code = "rate_limited"


class OpenAIServerError(OpenAITransientProviderError):
    code = "server_error"


class OpenAIConfigurationError(OpenAIProviderError):
    """Non-retryable configuration or request-shape failures."""

    code = "configuration"


class OpenAIAuthenticationError(OpenAIConfigurationError):
    code = "authentication"


def sanitize_provider_message(
    message: str | None,
    *,
    api_key: str | None = None,
) -> str:
    """Return a user/log-safe message with secrets and auth material removed."""
    text = (message or "").strip()
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text.strip()


def map_openai_sdk_error(
    exc: BaseException,
    *,
    api_key: str | None = None,
) -> OpenAIProviderError:
    """Map SDK exceptions to typed, redacted adapter errors."""
    if isinstance(exc, OpenAIProviderError):
        return exc

    message = sanitize_provider_message(str(exc), api_key=api_key)

    if isinstance(exc, APITimeoutError):
        return OpenAITimeoutError(message or "OpenAI request timed out.")
    if isinstance(exc, RateLimitError):
        return OpenAIRateLimitError(message or "OpenAI rate limit exceeded.")
    if isinstance(exc, AuthenticationError):
        return OpenAIAuthenticationError(message or "OpenAI authentication failed.")
    if isinstance(exc, PermissionDeniedError):
        return OpenAIAuthenticationError(message or "OpenAI permission denied.")
    if isinstance(exc, (BadRequestError, NotFoundError)):
        return OpenAIConfigurationError(message or "OpenAI request configuration is invalid.")
    if isinstance(exc, InternalServerError):
        return OpenAIServerError(message or "OpenAI server error.")
    if isinstance(exc, APIConnectionError):
        return OpenAIServerError(message or "OpenAI connection error.")
    if isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return OpenAIRateLimitError(message or "OpenAI rate limit exceeded.")
        if status_code in {401, 403}:
            return OpenAIAuthenticationError(message or "OpenAI authentication failed.")
        if status_code is not None and status_code >= 500:
            return OpenAIServerError(message or "OpenAI server error.")
        if status_code is not None and status_code in {400, 404, 422}:
            return OpenAIConfigurationError(
                message or "OpenAI request configuration is invalid."
            )
        return OpenAIServerError(message or "OpenAI provider request failed.")

    return OpenAIProviderError(message or "OpenAI provider request failed.")


def redact_request_kwargs(kwargs: dict[str, Any], *, api_key: str | None = None) -> dict[str, Any]:
    """Return a log-safe copy of outbound SDK kwargs."""
    redacted = dict(kwargs)
    for secret_key in ("api_key", "authorization", "headers"):
        if secret_key in redacted:
            redacted[secret_key] = "[REDACTED]"
    if api_key and "input" in redacted:
        input_text = redacted.get("input")
        if isinstance(input_text, str):
            redacted["input"] = sanitize_provider_message(input_text, api_key=api_key)
    return redacted
