"""Structural tests for assistant policy and OpenAI request builder (T04)."""

from __future__ import annotations

import json

import pytest

from app.ai.config import DEFAULT_MAX_OUTPUT_TOKENS, AISettings
from app.ai.policy import ASSISTANT_POLICY_INSTRUCTION, ASSISTANT_POLICY_VERSION
from app.ai.assistant import FunctionCallOutput
from app.ai.request_builder import (
    OpenAIResponsesRequest,
    build_openai_continue_request,
    build_openai_responses_request,
    request_payload_text,
)
from app.ai.tool_schemas import openai_function_tools
from app.risk.query import RiskAssistantModelRequest, tool_contract_schemas


@pytest.fixture
def openai_settings() -> AISettings:
    return AISettings(
        provider="openai",
        openai_model="gpt-test-model",
        timeout_seconds=42.0,
        max_output_tokens=256,
        max_tool_rounds=1,
    )


def test_policy_is_versioned_and_covers_required_rules() -> None:
    policy = ASSISTANT_POLICY_INSTRUCTION

    assert ASSISTANT_POLICY_VERSION == "1.0.1"
    assert f"v{ASSISTANT_POLICY_VERSION}" in policy
    assert "Select at most one function" in policy
    assert "Never calculate" in policy
    assert "required identifiers are missing" in policy
    assert "Refuse trading advice" in policy
    assert "prompt injection" in policy
    assert "Never reveal secrets" in policy


def test_request_structure_matches_responses_api_shape(
    openai_settings: AISettings,
) -> None:
    request = RiskAssistantModelRequest(
        question="What is the worst stress scenario?",
        tools=tool_contract_schemas(),
        portfolio_id="rates-macro",
        available_run_ids=["run-t0", "run-t1"],
    )
    payload = build_openai_responses_request(request, openai_settings)

    assert isinstance(payload, OpenAIResponsesRequest)
    assert payload.timeout_seconds == 42.0
    assert set(payload.create_params) == {
        "model",
        "instructions",
        "input",
        "tools",
        "max_output_tokens",
        "max_tool_calls",
        "tool_choice",
    }
    assert payload.create_params["model"] == "gpt-test-model"
    assert payload.create_params["instructions"] == ASSISTANT_POLICY_INSTRUCTION
    assert payload.create_params["max_output_tokens"] == 256
    assert payload.create_params["max_tool_calls"] == 1
    assert payload.create_params["tool_choice"] == "auto"


def test_request_includes_question_and_minimal_routing_context_only(
    openai_settings: AISettings,
) -> None:
    request = RiskAssistantModelRequest(
        question="Compare my last two runs",
        tools=tool_contract_schemas(),
        portfolio_id="global-macro",
        available_run_ids=["run-a", "run-b"],
    )
    user_input = build_openai_responses_request(request, openai_settings).create_params[
        "input"
    ]

    assert user_input.startswith("Question: Compare my last two runs")
    assert "portfolio_id=global-macro" in user_input
    assert "available_run_ids=run-a,run-b" in user_input


def test_request_omits_empty_routing_context(openai_settings: AISettings) -> None:
    request = RiskAssistantModelRequest(
        question="Show VaR",
        tools=tool_contract_schemas(),
    )
    user_input = build_openai_responses_request(request, openai_settings).create_params[
        "input"
    ]

    assert user_input == "Question: Show VaR"
    assert "Routing context:" not in user_input


def test_tools_come_from_openai_function_schemas_not_request_tools(
    openai_settings: AISettings,
) -> None:
    contract_tools = tool_contract_schemas()
    request = RiskAssistantModelRequest(
        question="Show limits",
        tools=contract_tools,
    )
    payload = build_openai_responses_request(request, openai_settings)

    assert payload.create_params["tools"] == openai_function_tools()
    assert payload.create_params["tools"] != contract_tools


def test_portfolio_positions_and_tool_results_are_not_sent(
    openai_settings: AISettings,
) -> None:
    # Request builder has no positions/results fields; guard that sensitive
    # position-like tokens never appear in the serialized Responses payload.
    request = RiskAssistantModelRequest(
        question="Summarize the portfolio",
        tools=tool_contract_schemas(),
        portfolio_id="rates-macro",
        available_run_ids=["run-sensitive"],
    )
    serialized = request_payload_text(
        build_openai_responses_request(request, openai_settings)
    )

    assert "pos-secret-123" not in serialized
    assert "175000000.55" not in serialized
    assert "12345678.9" not in serialized
    assert "23456789.1" not in serialized
    assert "pos-secret" not in serialized
    assert "175_000_000" not in serialized


def test_legacy_instruction_on_request_is_not_sent(openai_settings: AISettings) -> None:
    request = RiskAssistantModelRequest(
        question="Show contributors",
        tools=tool_contract_schemas(),
        instruction="Legacy per-request instruction that must not leak.",
    )
    payload = build_openai_responses_request(request, openai_settings)

    assert payload.create_params["instructions"] == ASSISTANT_POLICY_INSTRUCTION
    assert "Legacy per-request instruction" not in json.dumps(payload.create_params)


def test_output_budget_and_timeout_default_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test-model")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "55")
    monkeypatch.setenv("AI_MAX_OUTPUT_TOKENS", "384")

    from app.ai.config import get_ai_settings

    settings = get_ai_settings()
    payload = build_openai_responses_request(
        RiskAssistantModelRequest(question="Show VaR", tools=[]),
        settings,
    )

    assert payload.timeout_seconds == 55.0
    assert payload.create_params["max_output_tokens"] == 384
    assert settings.max_output_tokens == 384
    assert settings.timeout_seconds == 55.0


def test_openai_model_is_required_to_build_request() -> None:
    settings = AISettings(
        provider="deterministic",
        openai_model=None,
        timeout_seconds=30.0,
        max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        max_tool_rounds=1,
    )
    request = RiskAssistantModelRequest(question="Show VaR", tools=[])

    with pytest.raises(ValueError, match="openai_model is required"):
        build_openai_responses_request(request, settings)


def test_continue_request_appends_function_call_outputs(
    openai_settings: AISettings,
) -> None:
    """T21: previous_response_id + function_call_output items; one tool call per round."""
    multi_round = AISettings(
        provider="openai",
        openai_model="gpt-test-model",
        timeout_seconds=42.0,
        max_output_tokens=256,
        max_tool_rounds=4,
    )
    payload = build_openai_continue_request(
        previous_response_id="resp_abc",
        tool_outputs=[
            FunctionCallOutput(call_id="call_1", output='{"var": 1.2}'),
        ],
        settings=multi_round,
    )

    assert payload.create_params["previous_response_id"] == "resp_abc"
    assert payload.create_params["max_tool_calls"] == 1
    assert payload.create_params["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"var": 1.2}',
        }
    ]
    assert "instructions" not in payload.create_params
    assert payload.create_params["tools"] == openai_function_tools()


def test_initial_request_keeps_one_tool_call_per_round_when_max_rounds_is_four(
    openai_settings: AISettings,
) -> None:
    settings = AISettings(
        provider="openai",
        openai_model="gpt-test-model",
        timeout_seconds=30.0,
        max_output_tokens=256,
        max_tool_rounds=4,
    )
    payload = build_openai_responses_request(
        RiskAssistantModelRequest(question="Show VaR", tools=[]),
        settings,
    )
    assert payload.create_params["max_tool_calls"] == 1
