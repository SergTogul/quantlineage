"""T20 — RiskAssistant protocol and one-tool compatibility adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.ai.assistant import (
    ONE_TOOL_CALL_ID,
    OneToolRiskAssistant,
    RiskAssistantRequest,
    RiskAssistantToolOutput,
    RiskAssistantTurn,
    model_response_to_turn,
    to_model_request,
)
from app.ai.config import get_ai_settings
from app.ai.factory import build_risk_assistant_resources
from app.risk.query import (
    DeterministicRiskAssistantModel,
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskQueryEngine,
    tool_contract_schemas,
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


class _RecordingModel:
    def __init__(self, response: RiskAssistantModelResponse) -> None:
        self.response = response
        self.requests: list[RiskAssistantModelRequest] = []

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        self.requests.append(request)
        return self.response


class _ExecutingModel:
    """Fails if the adapter (or a later loop) tries to run a portfolio tool."""

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        raise AssertionError("tool execution is not part of RiskAssistant.complete_turn")


def test_one_tool_adapter_maps_single_function_call() -> None:
    model = _RecordingModel(
        RiskAssistantModelResponse(
            tool_name="get_contributors",
            tool_args={"top_n": 5},
            intent="contributors",
            rationale="route to contributors",
        )
    )
    assistant = OneToolRiskAssistant(model)
    request = RiskAssistantRequest(
        question="Biggest risk contributors?",
        tools=tool_contract_schemas(),
        portfolio_id="rates-macro",
        available_run_ids=["run-a"],
    )

    turn = assistant.complete_turn(request)

    assert turn.finished is False
    assert len(turn.tool_calls) == 1
    call = turn.tool_calls[0]
    assert call.call_id == ONE_TOOL_CALL_ID
    assert call.name == "get_contributors"
    assert call.arguments == {"top_n": 5}
    assert turn.intent == "contributors"
    assert turn.proposed_answer is None
    assert len(model.requests) == 1
    assert model.requests[0].question == "Biggest risk contributors?"
    assert model.requests[0].portfolio_id == "rates-macro"
    assert model.requests[0].available_run_ids == ["run-a"]


def test_one_tool_adapter_maps_clarification_and_refusal() -> None:
    clarification = OneToolRiskAssistant(
        _RecordingModel(
            RiskAssistantModelResponse(
                tool_name=None,
                requires_clarification=True,
                clarification="Which risk run id should I use?",
                intent="ambiguous",
            )
        )
    ).complete_turn(
        RiskAssistantRequest(question="Compare the runs", tools=tool_contract_schemas())
    )
    assert clarification.finished is True
    assert clarification.tool_calls == []
    assert clarification.requires_clarification is True
    assert clarification.clarification == "Which risk run id should I use?"

    refusal = OneToolRiskAssistant(
        _RecordingModel(
            RiskAssistantModelResponse(
                tool_name="get_var_es",
                refusal="I cannot give trading advice.",
                intent="unsupported",
            )
        )
    ).complete_turn(
        RiskAssistantRequest(question="What should I buy?", tools=tool_contract_schemas())
    )
    assert refusal.finished is True
    assert refusal.tool_calls == []
    assert refusal.refusal == "I cannot give trading advice."
    assert refusal.requires_clarification is False


def test_one_tool_adapter_does_not_execute_tools() -> None:
    assistant = OneToolRiskAssistant(_ExecutingModel())
    turn = assistant.complete_turn(
        RiskAssistantRequest(
            question="Show VaR",
            tools=tool_contract_schemas(),
            prior_outputs=[
                RiskAssistantToolOutput(
                    call_id="call_0",
                    name="get_var_es",
                    output={"var_99": 12.5},
                )
            ],
            round_index=1,
            max_rounds=4,
        )
    )
    assert turn.finished is True
    assert turn.tool_calls == []
    assert turn.proposed_answer is None
    assert "cannot continue" in (turn.clarification or "")


def test_one_tool_adapter_refuses_follow_up_rounds_without_calling_model() -> None:
    model = _RecordingModel(
        RiskAssistantModelResponse(tool_name="get_limits", tool_args={})
    )
    assistant = OneToolRiskAssistant(model)
    follow_up = RiskAssistantRequest(
        question="Now compare with the previous run",
        tools=tool_contract_schemas(),
        round_index=1,
        max_rounds=4,
        prior_outputs=[
            RiskAssistantToolOutput(call_id="call_0", name="get_limits", output={})
        ],
    )

    turn = assistant.complete_turn(follow_up)

    assert model.requests == []
    assert turn.finished is True
    assert turn.tool_calls == []
    assert turn.requires_clarification is True


def test_complete_still_delegates_to_milestone_1_model() -> None:
    model = _RecordingModel(
        RiskAssistantModelResponse(tool_name="get_var_es", tool_args={})
    )
    assistant = OneToolRiskAssistant(model)
    request = RiskAssistantModelRequest(
        question="What is 99% VaR?",
        tools=tool_contract_schemas(),
    )

    response = assistant.complete(request)

    assert response.tool_name == "get_var_es"
    assert model.requests == [request]


def test_deterministic_model_still_works_through_adapter() -> None:
    model = DeterministicRiskAssistantModel(RiskQueryEngine())
    assistant = OneToolRiskAssistant(model)
    turn = assistant.complete_turn(
        RiskAssistantRequest(
            question="show top risk contributors",
            tools=tool_contract_schemas(),
        )
    )
    assert turn.finished is False
    assert [call.name for call in turn.tool_calls] == ["get_contributors"]

    routed = model.complete(
        RiskAssistantModelRequest(
            question="show top risk contributors",
            tools=tool_contract_schemas(),
        )
    )
    assert routed.tool_name == "get_contributors"


def test_to_model_request_does_not_send_prior_outputs() -> None:
    request = RiskAssistantRequest(
        question="Explain the change",
        tools=[{"name": "get_run_provenance"}],
        prior_outputs=[
            RiskAssistantToolOutput(
                call_id="call_0",
                name="get_risk_run",
                output={"run_id": "abc"},
            )
        ],
        round_index=1,
        max_rounds=4,
    )
    projected = to_model_request(request)
    dumped = projected.model_dump()
    assert "prior_outputs" not in dumped
    assert dumped["question"] == "Explain the change"
    assert dumped["tools"] == [{"name": "get_run_provenance"}]


def test_model_response_to_turn_does_not_invent_numeric_answer() -> None:
    turn = model_response_to_turn(
        RiskAssistantModelResponse(
            tool_name="get_var_es",
            tool_args={},
            proposed_answer="VaR is 42",
        )
    )
    assert turn.proposed_answer == "VaR is 42"
    assert turn.tool_calls[0].arguments == {}
    assert not any(isinstance(value, (int, float)) for value in turn.tool_calls[0].arguments.values())


def test_factory_wraps_openai_model_without_replacing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_client = SimpleNamespace(close=MagicMock())
    monkeypatch.setattr("openai.OpenAI", MagicMock(return_value=sentinel_client))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-1234567890")
    settings = get_ai_settings(provider="openai", openai_model="gpt-test")

    resources = build_risk_assistant_resources(settings=settings)

    assert resources.model is not None
    assert isinstance(resources.assistant, OneToolRiskAssistant)
    assert resources.assistant.model is resources.model


def test_factory_deterministic_mode_has_no_assistant() -> None:
    resources = build_risk_assistant_resources(
        settings=get_ai_settings(provider="deterministic")
    )
    assert resources.model is None
    assert resources.assistant is None


def test_turn_is_json_safe_and_has_no_secret_fields() -> None:
    turn = RiskAssistantTurn(
        tool_calls=[],
        finished=True,
        clarification="Need a run id",
        proposed_answer=None,
    )
    payload = turn.model_dump()
    assert "api_key" not in payload
    assert "OPENAI_API_KEY" not in payload
    assert payload["proposed_answer"] is None
