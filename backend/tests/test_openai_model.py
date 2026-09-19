"""Unit tests for the OpenAI risk assistant model adapter (T05)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
)

from app.ai.config import AISettings
from app.ai.openai_model import OpenAIRiskAssistantModel
from app.ai.policy import ASSISTANT_POLICY_INSTRUCTION
from app.ai.tool_schemas import openai_function_tools
from app.risk.query import RiskAssistantModelRequest, RiskAssistantModelResponse, tool_contract_schemas


@dataclass
class FakeResponses:
    response: Any
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


@dataclass
class FakeOpenAIClient:
    responses: FakeResponses


@pytest.fixture
def openai_settings() -> AISettings:
    return AISettings(
        provider="openai",
        openai_model="gpt-test-model",
        timeout_seconds=42.0,
        max_output_tokens=256,
        max_tool_rounds=1,
    )


def _make_response(*output: Any) -> Response:
    return Response(
        id="resp_test",
        created_at=0,
        model="gpt-test-model",
        object="response",
        output=list(output),
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )


def _function_call(
    *,
    name: str,
    arguments: str = "{}",
    call_id: str = "call_test",
) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def test_complete_parses_one_function_call(openai_settings: AISettings) -> None:
    sdk_response = _make_response(
        _function_call(name="get_var_es", arguments='{"confidence": 0.99}')
    )
    client = FakeOpenAIClient(responses=FakeResponses(response=sdk_response))
    model = OpenAIRiskAssistantModel(client, openai_settings)
    request = RiskAssistantModelRequest(
        question="What is 99% VaR?",
        tools=tool_contract_schemas(),
        portfolio_id="rates-macro",
        available_run_ids=["run-a"],
    )

    result = model.complete(request)

    assert isinstance(result, RiskAssistantModelResponse)
    assert result.tool_name == "get_var_es"
    assert result.tool_args == {"confidence": 0.99}
    assert result.proposed_answer is None
    assert result.requires_clarification is False
    assert result.refusal is None


def test_complete_uses_responses_create_with_request_builder_payload(
    openai_settings: AISettings,
) -> None:
    sdk_response = _make_response(_function_call(name="get_limits"))
    fake_responses = FakeResponses(response=sdk_response)
    client = FakeOpenAIClient(responses=fake_responses)
    model = OpenAIRiskAssistantModel(client, openai_settings)
    request = RiskAssistantModelRequest(
        question="Which limits are breached?",
        tools=tool_contract_schemas(),
        portfolio_id="global-macro",
        available_run_ids=["run-1", "run-2"],
    )

    model.complete(request)

    assert len(fake_responses.calls) == 1
    call = fake_responses.calls[0]
    assert call["model"] == "gpt-test-model"
    assert call["instructions"] == ASSISTANT_POLICY_INSTRUCTION
    assert call["timeout"] == 42.0
    assert call["max_output_tokens"] == 256
    assert call["max_tool_calls"] == 1
    assert call["tool_choice"] == "auto"
    assert call["tools"] == openai_function_tools()
    assert call["input"].startswith("Question: Which limits are breached?")
    assert "portfolio_id=global-macro" in call["input"]
    assert "available_run_ids=run-1,run-2" in call["input"]


def test_complete_does_not_return_numeric_prose_as_proposed_answer(
    openai_settings: AISettings,
) -> None:
    sdk_response = _make_response(
        ResponseOutputMessage(
            id="msg_1",
            type="message",
            role="assistant",
            status="completed",
            content=[
                ResponseOutputText(
                    type="output_text",
                    text="99% VaR is 123456789.",
                    annotations=[],
                )
            ],
        ),
        _function_call(name="get_var_es"),
    )
    client = FakeOpenAIClient(responses=FakeResponses(response=sdk_response))
    model = OpenAIRiskAssistantModel(client, openai_settings)

    result = model.complete(
        RiskAssistantModelRequest(question="Show VaR", tools=tool_contract_schemas())
    )

    assert result.tool_name == "get_var_es"
    assert result.proposed_answer is None
    assert result.rationale is None


def test_complete_keeps_non_numeric_rationale(openai_settings: AISettings) -> None:
    sdk_response = _make_response(
        ResponseOutputMessage(
            id="msg_1",
            type="message",
            role="assistant",
            status="completed",
            content=[
                ResponseOutputText(
                    type="output_text",
                    text="The user asked about limit breach status.",
                    annotations=[],
                )
            ],
        ),
        _function_call(name="get_limits"),
    )
    client = FakeOpenAIClient(responses=FakeResponses(response=sdk_response))
    model = OpenAIRiskAssistantModel(client, openai_settings)

    result = model.complete(
        RiskAssistantModelRequest(question="Any limit breaches?", tools=tool_contract_schemas())
    )

    assert result.tool_name == "get_limits"
    assert result.rationale == "The user asked about limit breach status."
    assert result.proposed_answer is None


def test_complete_does_not_execute_tools(openai_settings: AISettings) -> None:
    sdk_response = _make_response(_function_call(name="get_portfolio_summary"))
    client = FakeOpenAIClient(responses=FakeResponses(response=sdk_response))
    model = OpenAIRiskAssistantModel(client, openai_settings)

    result = model.complete(
        RiskAssistantModelRequest(
            question="Summarize the portfolio",
            tools=tool_contract_schemas(),
        )
    )

    assert result.tool_name == "get_portfolio_summary"
    assert result.tool_args == {}


def test_complete_returns_only_domain_response_not_sdk_objects(
    openai_settings: AISettings,
) -> None:
    sdk_response = _make_response(_function_call(name="get_worst_stress"))
    client = FakeOpenAIClient(responses=FakeResponses(response=sdk_response))
    model = OpenAIRiskAssistantModel(client, openai_settings)

    result = model.complete(
        RiskAssistantModelRequest(question="Worst stress?", tools=tool_contract_schemas())
    )

    assert type(result) is RiskAssistantModelResponse
    assert not isinstance(result, Response)


def test_complete_accepts_injected_client_and_settings(
    openai_settings: AISettings,
) -> None:
    sdk_response = _make_response(_function_call(name="get_contributors"))
    fake_responses = FakeResponses(response=sdk_response)
    client = FakeOpenAIClient(responses=fake_responses)
    model = OpenAIRiskAssistantModel(client=client, settings=openai_settings)

    result = model.complete(
        RiskAssistantModelRequest(question="Top contributors?", tools=tool_contract_schemas())
    )

    assert result.tool_name == "get_contributors"
    assert fake_responses.calls


def test_zero_function_calls_become_clarification(openai_settings: AISettings) -> None:
    sdk_response = _make_response(
        ResponseOutputMessage(
            id="msg_1",
            type="message",
            role="assistant",
            status="completed",
            content=[
                ResponseOutputText(
                    type="output_text",
                    text="Do you want VaR/ES or limits?",
                    annotations=[],
                )
            ],
        )
    )
    client = FakeOpenAIClient(responses=FakeResponses(response=sdk_response))
    model = OpenAIRiskAssistantModel(client, openai_settings)

    result = model.complete(
        RiskAssistantModelRequest(question="How risky are we?", tools=tool_contract_schemas())
    )

    assert result.tool_name is None
    assert result.requires_clarification is True
    assert result.clarification == "Do you want VaR/ES or limits?"
    assert result.proposed_answer is None


def test_zero_function_calls_with_refusal(openai_settings: AISettings) -> None:
    sdk_response = _make_response(
        ResponseOutputMessage(
            id="msg_1",
            type="message",
            role="assistant",
            status="completed",
            content=[
                ResponseOutputRefusal(
                    type="refusal",
                    refusal="I cannot provide trading advice.",
                )
            ],
        )
    )
    client = FakeOpenAIClient(responses=FakeResponses(response=sdk_response))
    model = OpenAIRiskAssistantModel(client, openai_settings)

    result = model.complete(
        RiskAssistantModelRequest(
            question="Should we buy more NVDA?",
            tools=tool_contract_schemas(),
        )
    )

    assert result.tool_name is None
    assert result.intent == "unsupported"
    assert result.refusal == "I cannot provide trading advice."
    assert result.proposed_answer is None


def test_multiple_function_calls_raise_clear_error(openai_settings: AISettings) -> None:
    sdk_response = _make_response(
        _function_call(name="get_var_es", call_id="call_1"),
        _function_call(name="get_limits", call_id="call_2"),
    )
    client = FakeOpenAIClient(responses=FakeResponses(response=sdk_response))
    model = OpenAIRiskAssistantModel(client, openai_settings)

    with pytest.raises(ValueError, match="Expected at most one function call"):
        model.complete(
            RiskAssistantModelRequest(question="Show everything", tools=tool_contract_schemas())
        )
