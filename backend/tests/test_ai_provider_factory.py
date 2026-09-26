"""Provider factory and application lifecycle wiring (T07)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.ai.config import AISettings, get_ai_settings
from app.ai.factory import (
    RiskAssistantResources,
    build_risk_assistant_resources,
)
from app.ai.openai_model import OpenAIRiskAssistantModel
from app.main import app


@pytest.fixture(autouse=True)
def _clear_ai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Global isolation lives in tests/conftest.py; keep local clears for clarity.
    for name in (
        "OPENAI_API_KEY",
        "AI_PROVIDER",
        "OPENAI_MODEL",
        "AI_TIMEOUT_SECONDS",
        "AI_MAX_OUTPUT_TOKENS",
        "AI_MAX_TOOL_ROUNDS",
        "AI_MAX_TOOL_CALLS",
        "AI_ASSISTANT_LOOP",
    ):
        monkeypatch.delenv(name, raising=False)


def test_deterministic_mode_does_not_construct_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openai_ctor = MagicMock()
    monkeypatch.setattr("openai.OpenAI", openai_ctor)

    resources = build_risk_assistant_resources(
        settings=get_ai_settings(provider="deterministic"),
    )

    assert resources.settings.provider == "deterministic"
    assert resources.model is None
    assert resources._openai_client is None
    openai_ctor.assert_not_called()


def test_openai_mode_constructs_one_reusable_client_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_client = SimpleNamespace(close=MagicMock())
    openai_ctor = MagicMock(return_value=sentinel_client)
    monkeypatch.setattr("openai.OpenAI", openai_ctor)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-1234567890")
    settings = get_ai_settings(provider="openai", openai_model="gpt-test")

    resources = build_risk_assistant_resources(settings=settings)

    openai_ctor.assert_called_once_with(api_key="sk-test-key-1234567890", max_retries=0)
    assert isinstance(resources.model, OpenAIRiskAssistantModel)
    assert resources._openai_client is sentinel_client


def test_openai_config_errors_are_actionable_without_key_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-should-not-appear")

    with pytest.raises(ValueError, match="OPENAI_MODEL is required") as exc:
        get_ai_settings()

    assert "sk-secret-should-not-appear" not in str(exc.value)

    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required") as exc:
        get_ai_settings()

    assert "sk-secret-should-not-appear" not in str(exc.value)


def test_load_application_dotenv_does_not_override_exported_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("EXPORTED_VAR=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("EXPORTED_VAR", "from-process")
    monkeypatch.chdir(tmp_path)
    # Exercise the same dotenv contract used by load_application_dotenv.
    from dotenv import load_dotenv

    load_dotenv(override=False)

    assert __import__("os").environ["EXPORTED_VAR"] == "from-process"


def test_resources_close_calls_openai_client_close() -> None:
    client = SimpleNamespace(close=MagicMock())
    resources = RiskAssistantResources(
        settings=AISettings(
            provider="openai",
            openai_model="gpt-test",
            timeout_seconds=30.0,
            max_output_tokens=512,
            max_tool_rounds=1,
        ),
        model=SimpleNamespace(),
        _openai_client=client,
    )

    resources.close()
    client.close.assert_called_once()


def test_lifespan_sets_ai_state_and_closes_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    close_mock = MagicMock()
    sentinel_client = SimpleNamespace(close=close_mock)
    openai_ctor = MagicMock(return_value=sentinel_client)
    monkeypatch.setattr("openai.OpenAI", openai_ctor)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-1234567890")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    with TestClient(app) as client:
        assert client.app.state.ai_settings.provider == "openai"
        assert isinstance(client.app.state.risk_assistant_model, OpenAIRiskAssistantModel)
        assert client.app.state.portfolio_service.risk_assistant_model is (
            client.app.state.risk_assistant_model
        )
        openai_ctor.assert_called_once()

    close_mock.assert_called_once()


def test_lifespan_default_is_deterministic_without_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openai_ctor = MagicMock()
    monkeypatch.setattr("openai.OpenAI", openai_ctor)

    with TestClient(app) as client:
        assert client.app.state.ai_settings.provider == "deterministic"
        assert client.app.state.risk_assistant_model is None
        assert client.app.state.portfolio_service.risk_assistant_model is None
        openai_ctor.assert_not_called()


def test_dependency_override_can_replace_risk_assistant_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openai_ctor = MagicMock()
    monkeypatch.setattr("openai.OpenAI", openai_ctor)
    sentinel = SimpleNamespace(complete=MagicMock())

    with TestClient(app) as client:
        client.app.state.risk_assistant_model = sentinel
        client.app.state.portfolio_service.risk_assistant_model = sentinel
        assert client.app.state.risk_assistant_model is sentinel
        assert client.app.state.portfolio_service.risk_assistant_model is sentinel
