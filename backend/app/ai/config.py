"""AI provider settings loaded from environment variables.

Reads ``os.environ`` only; never writes or overrides exported variables.
The OpenAI API key is accessed separately via :func:`get_openai_api_key` so it
is not stored on :class:`AISettings` or included in repr / routine logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

AIProvider = Literal["deterministic", "openai"]

DEFAULT_AI_PROVIDER: AIProvider = "deterministic"
DEFAULT_AI_TIMEOUT_SECONDS = 30.0
MAX_AI_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_OUTPUT_TOKENS = 512
MAX_AI_OUTPUT_TOKENS = 4096
REQUIRED_MAX_TOOL_ROUNDS = 1

_SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"deterministic", "openai"})


@dataclass(frozen=True, slots=True)
class AISettings:
    """Resolved AI provider settings (no secrets)."""

    provider: AIProvider
    openai_model: str | None
    timeout_seconds: float
    max_output_tokens: int
    max_tool_rounds: int


def get_openai_api_key() -> str | None:
    """Return ``OPENAI_API_KEY`` when explicitly set (non-blank)."""
    raw = os.environ.get("OPENAI_API_KEY")
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _parse_provider(raw: str | None) -> AIProvider:
    if raw is None or not raw.strip():
        return DEFAULT_AI_PROVIDER
    provider = raw.strip().lower()
    if provider not in _SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(_SUPPORTED_PROVIDERS))
        raise ValueError(
            f"Invalid AI_PROVIDER: {provider!r}. "
            f"Supported providers: {supported}."
        )
    return provider  # type: ignore[return-value]


def _parse_timeout(raw: str | None) -> float:
    if raw is None or not raw.strip():
        return DEFAULT_AI_TIMEOUT_SECONDS
    try:
        timeout = float(raw.strip())
    except ValueError as exc:
        raise ValueError(
            "Invalid AI_TIMEOUT_SECONDS: "
            f"{raw.strip()!r}. Expected a positive number up to "
            f"{MAX_AI_TIMEOUT_SECONDS:g}."
        ) from exc
    if timeout <= 0 or timeout > MAX_AI_TIMEOUT_SECONDS:
        raise ValueError(
            "Invalid AI_TIMEOUT_SECONDS: "
            f"{timeout!r}. Expected a positive number up to "
            f"{MAX_AI_TIMEOUT_SECONDS:g}."
        )
    return timeout


def _parse_max_output_tokens(raw: str | None) -> int:
    if raw is None or not raw.strip():
        return DEFAULT_MAX_OUTPUT_TOKENS
    try:
        tokens = int(raw.strip())
    except ValueError as exc:
        raise ValueError(
            "Invalid AI_MAX_OUTPUT_TOKENS: "
            f"{raw.strip()!r}. Expected a positive integer up to "
            f"{MAX_AI_OUTPUT_TOKENS}."
        ) from exc
    if tokens <= 0 or tokens > MAX_AI_OUTPUT_TOKENS:
        raise ValueError(
            "Invalid AI_MAX_OUTPUT_TOKENS: "
            f"{tokens!r}. Expected a positive integer up to "
            f"{MAX_AI_OUTPUT_TOKENS}."
        )
    return tokens


def _parse_max_tool_rounds(raw: str | None) -> int:
    if raw is None or not raw.strip():
        return REQUIRED_MAX_TOOL_ROUNDS
    try:
        rounds = int(raw.strip())
    except ValueError as exc:
        raise ValueError(
            "Invalid AI_MAX_TOOL_ROUNDS: "
            f"{raw.strip()!r}. Milestone 1 requires exactly "
            f"{REQUIRED_MAX_TOOL_ROUNDS}."
        ) from exc
    if rounds != REQUIRED_MAX_TOOL_ROUNDS:
        raise ValueError(
            "Invalid AI_MAX_TOOL_ROUNDS: "
            f"{rounds!r}. Milestone 1 requires exactly "
            f"{REQUIRED_MAX_TOOL_ROUNDS}."
        )
    return rounds


def _optional_model(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def get_ai_settings(
    *,
    provider: AIProvider | None = None,
    openai_model: str | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    max_tool_rounds: int | None = None,
) -> AISettings:
    """Load AI settings from explicit args or environment.

    Env vars:
    - ``AI_PROVIDER`` — ``deterministic`` (default) or ``openai``
    - ``OPENAI_MODEL`` — model name (required when provider is openai)
    - ``AI_TIMEOUT_SECONDS`` — request timeout (default 30, max 120)
    - ``AI_MAX_OUTPUT_TOKENS`` — output token cap (default 512, max 4096)
    - ``AI_MAX_TOOL_ROUNDS`` — must be ``1`` in milestone 1

    ``OPENAI_API_KEY`` is read via :func:`get_openai_api_key` when provider is
    ``openai``; it is never stored on the returned settings object.
    """
    resolved_provider = (
        provider
        if provider is not None
        else _parse_provider(os.environ.get("AI_PROVIDER"))
    )
    resolved_model = (
        openai_model
        if openai_model is not None
        else _optional_model(os.environ.get("OPENAI_MODEL"))
    )
    if timeout_seconds is not None:
        resolved_timeout = timeout_seconds
        if resolved_timeout <= 0 or resolved_timeout > MAX_AI_TIMEOUT_SECONDS:
            raise ValueError(
                "Invalid timeout_seconds: "
                f"{resolved_timeout!r}. Expected a positive number up to "
                f"{MAX_AI_TIMEOUT_SECONDS:g}."
            )
    else:
        resolved_timeout = _parse_timeout(os.environ.get("AI_TIMEOUT_SECONDS"))
    if max_output_tokens is not None:
        resolved_output_tokens = max_output_tokens
        if resolved_output_tokens <= 0 or resolved_output_tokens > MAX_AI_OUTPUT_TOKENS:
            raise ValueError(
                "Invalid max_output_tokens: "
                f"{resolved_output_tokens!r}. Expected a positive integer up to "
                f"{MAX_AI_OUTPUT_TOKENS}."
            )
    else:
        resolved_output_tokens = _parse_max_output_tokens(
            os.environ.get("AI_MAX_OUTPUT_TOKENS")
        )
    if max_tool_rounds is not None:
        resolved_rounds = max_tool_rounds
        if resolved_rounds != REQUIRED_MAX_TOOL_ROUNDS:
            raise ValueError(
                "Invalid max_tool_rounds: "
                f"{resolved_rounds!r}. Milestone 1 requires exactly "
                f"{REQUIRED_MAX_TOOL_ROUNDS}."
            )
    else:
        resolved_rounds = _parse_max_tool_rounds(
            os.environ.get("AI_MAX_TOOL_ROUNDS")
        )

    if resolved_provider == "openai":
        if get_openai_api_key() is None:
            raise ValueError(
                "OPENAI_API_KEY is required when AI_PROVIDER=openai."
            )
        if resolved_model is None:
            raise ValueError(
                "OPENAI_MODEL is required when "
                "AI_PROVIDER=openai."
            )

    return AISettings(
        provider=resolved_provider,
        openai_model=resolved_model,
        timeout_seconds=resolved_timeout,
        max_output_tokens=resolved_output_tokens,
        max_tool_rounds=resolved_rounds,
    )
