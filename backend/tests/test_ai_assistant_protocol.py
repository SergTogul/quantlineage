"""T20 — RiskAssistant protocol and one-shot milestone-1 adapter."""

from __future__ import annotations

from app.ai.assistant import (
    OneShotRiskAssistant,
    RiskAssistantRequest,
    RiskAssistantResult,
    adapt_model_as_assistant,
)
from app.risk.query import (
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskToolName,
    tool_contract_schemas,
)


class _ScriptedModel:
    def __init__(self, response: RiskAssistantModelResponse) -> None:
        self.response = response
        self.requests: list[RiskAssistantModelRequest] = []

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        self.requests.append(request)
        return self.response


def test_one_shot_assistant_maps_tool_selection() -> None:
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_CONTRIBUTORS,
            intent="contributors",
            tool_args={},
            rationale="top contributors",
        )
    )
    assistant = OneShotRiskAssistant(model)

    result = assistant.run(
        RiskAssistantRequest(
            question="Top contributors?",
            tools=tool_contract_schemas(),
            portfolio_id="global-macro",
            max_rounds=1,
        )
    )

    assert isinstance(result, RiskAssistantResult)
    assert result.rounds_used == 1
    assert result.stopped_reason == "tool_selected"
    assert result.requires_clarification is False
    assert len(result.tool_turns) == 1
    assert result.tool_turns[0].tool_name == "get_contributors"
    assert len(model.requests) == 1
    assert model.requests[0].portfolio_id == "global-macro"


def test_one_shot_assistant_maps_clarification() -> None:
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            intent="ambiguous",
            requires_clarification=True,
            clarification="Do you want VaR or limits?",
        )
    )
    assistant = adapt_model_as_assistant(model)

    result = assistant.run(
        RiskAssistantRequest(question="How risky are we?", tools=tool_contract_schemas())
    )

    assert result.stopped_reason == "clarification"
    assert result.requires_clarification is True
    assert result.clarification == "Do you want VaR or limits?"
    assert result.tool_turns == []


def test_one_shot_assistant_maps_refusal() -> None:
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            intent="unsupported",
            refusal="I cannot provide trading advice.",
        )
    )
    assistant = OneShotRiskAssistant(model)

    result = assistant.run(
        RiskAssistantRequest(question="What should I buy?", tools=[])
    )

    assert result.stopped_reason == "refusal"
    assert result.refusal == "I cannot provide trading advice."
    assert result.requires_clarification is True
    assert result.tool_turns == []


def test_one_shot_ignores_max_rounds_above_one_for_milestone1() -> None:
    """T20 adapter always performs a single model.complete; loop is T21."""
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_LIMITS,
            intent="limits",
        )
    )
    assistant = OneShotRiskAssistant(model)

    result = assistant.run(
        RiskAssistantRequest(question="Any breaches?", tools=[], max_rounds=4)
    )

    assert len(model.requests) == 1
    assert result.rounds_used == 1
    assert result.stopped_reason == "tool_selected"
