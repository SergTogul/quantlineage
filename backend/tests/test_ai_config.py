"""Unit tests for AI provider configuration (T01)."""

from __future__ import annotations

import importlib
import os
import sys

import pytest

from app.ai.config import (
    DEFAULT_AI_TIMEOUT_SECONDS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_TOOL_ROUNDS,
    MAX_AI_TIMEOUT_SECONDS,
    MAX_TOOL_ROUNDS,
    get_ai_settings,
    get_openai_api_key,
)


@pytest.fixture(autouse=True)
def _clear_ai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OPENAI_API_KEY",
        "AI_PROVIDER",
        "OPENAI_MODEL",
        "AI_TIMEOUT_SECONDS",
        "AI_MAX_OUTPUT_TOKENS",
        "AI_MAX_TOOL_ROUNDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_deterministic_provider() -> None:
    settings = get_ai_settings()
    assert settings.provider == "deterministic"
    assert settings.openai_model is None
    assert settings.timeout_seconds == DEFAULT_AI_TIMEOUT_SECONDS
    assert settings.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS
    assert settings.max_tool_rounds == DEFAULT_MAX_TOOL_ROUNDS


def test_supported_providers_are_deterministic_and_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    assert get_ai_settings().provider == "deterministic"

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    assert get_ai_settings().provider == "openai"

    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    with pytest.raises(ValueError, match="Supported providers"):
        get_ai_settings()


def test_openai_mode_requires_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        get_ai_settings()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(ValueError, match="OPENAI_MODEL is required"):
        get_ai_settings()

    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    settings = get_ai_settings()
    assert settings.provider == "openai"
    assert settings.openai_model == "gpt-test"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("0", "positive number"),
        ("-1", "positive number"),
        ("121", "positive number"),
        ("not-a-number", "positive number"),
    ],
)
def test_timeout_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    message: str,
) -> None:
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", raw)
    with pytest.raises(ValueError, match=message):
        get_ai_settings()


def test_timeout_accepts_valid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "45.5")
    assert get_ai_settings().timeout_seconds == 45.5

    monkeypatch.setenv("AI_TIMEOUT_SECONDS", str(MAX_AI_TIMEOUT_SECONDS))
    assert get_ai_settings().timeout_seconds == MAX_AI_TIMEOUT_SECONDS


def test_max_tool_rounds_defaults_to_one(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_ai_settings().max_tool_rounds == 1


@pytest.mark.parametrize("rounds", [1, 2, 3, 4])
def test_max_tool_rounds_allows_one_through_four(
    monkeypatch: pytest.MonkeyPatch,
    rounds: int,
) -> None:
    monkeypatch.setenv("AI_MAX_TOOL_ROUNDS", str(rounds))
    assert get_ai_settings().max_tool_rounds == rounds


@pytest.mark.parametrize(
    "raw",
    ["0", "5", "-1", "not-int"],
)
def test_max_tool_rounds_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    monkeypatch.setenv("AI_MAX_TOOL_ROUNDS", raw)
    with pytest.raises(ValueError, match=f"1 and {MAX_TOOL_ROUNDS}"):
        get_ai_settings()


def test_max_tool_rounds_explicit_arg_bounded() -> None:
    assert get_ai_settings(max_tool_rounds=3).max_tool_rounds == 3
    with pytest.raises(ValueError, match=f"1 and {MAX_TOOL_ROUNDS}"):
        get_ai_settings(max_tool_rounds=5)


def test_api_key_excluded_from_settings_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-super-secret-key-value"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    settings = get_ai_settings()
    rendered = repr(settings)

    assert "openai_api_key" not in rendered.lower()
    assert secret not in rendered
    assert "AISettings(" in rendered


def test_api_key_excluded_from_error_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-leaked-if-present"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    with pytest.raises(ValueError) as exc:
        get_ai_settings()

    assert secret not in str(exc.value)
    assert "OPENAI_MODEL is required" in str(exc.value)


def test_loading_does_not_override_exported_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "45")
    before = os.environ.copy()

    settings = get_ai_settings()

    assert os.environ == before
    assert settings.provider == "deterministic"
    assert settings.timeout_seconds == 45.0


def test_get_openai_api_key_reads_without_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "  sk-test  ")
    before = os.environ.copy()

    assert get_openai_api_key() == "sk-test"
    assert os.environ == before


def test_importing_config_does_not_create_openai_client_or_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network or OpenAI client creation during import")

    monkeypatch.setattr("socket.socket", _forbidden)

    module_name = "app.ai.config"
    sys.modules.pop(module_name, None)
    # Keep sibling packages; only prove *this* module's import is offline and
    # does not construct an OpenAI client (openai may already be in sys.modules
    # from earlier tests in the full suite).
    openai_was_loaded = "openai" in sys.modules

    imported = importlib.import_module(module_name)

    assert imported.AISettings.__name__ == "AISettings"
    assert callable(imported.get_ai_settings)
    assert "openai" not in getattr(imported, "__dict__", {})
    # Importing config must not newly pull in the OpenAI SDK.
    if not openai_was_loaded:
        assert "openai" not in sys.modules
    # And must not bind a client constructor as a side effect of import.
    assert not hasattr(imported, "OpenAI")
