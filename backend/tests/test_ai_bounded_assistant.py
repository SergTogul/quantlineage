"""T21 — Bounded Responses tool loop (≤4 rounds)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.ai.assistant import (
    SIDE_EFFECTING_TOOLS,
    BoundedRiskAssistant,
    FunctionCallOutput,
    RiskAssistantRequest,
    RiskAssistantResult,
)
from app.ai.errors import OpenAIModelParseError
from app.risk.query import (
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskToolName,
    tool_contract_schemas,
)


class _ScriptedLoopModel:
    """Returns scripted turns for complete / continue_after_tools."""

    def __init__(self, responses: list[RiskAssistantModelResponse]) -> None:
        self._responses = list(responses)
        self.complete_requests: list[RiskAssistantModelRequest] = []
        self.continue_calls: list[dict[str, Any]] = []

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        self.complete_requests.append(request)
        if not self._responses:
            raise AssertionError("ScriptedLoopModel complete queue exhausted")
        return self._responses.pop(0)

    def continue_after_tools(
        self,
        *,
        previous_response_id: str,
        tool_outputs: list[FunctionCallOutput],
        request: RiskAssistantModelRequest,
        reserve_narration: bool = False,
    ) -> RiskAssistantModelResponse:
        self.continue_calls.append(
            {
                "previous_response_id": previous_response_id,
                "tool_outputs": list(tool_outputs),
                "request": request,
                "reserve_narration": reserve_narration,
            }
        )
        if not self._responses:
            raise AssertionError("ScriptedLoopModel continue queue exhausted")
        return self._responses.pop(0)


def _executor_recording() -> tuple[list[tuple[str, dict[str, Any]]], Any]:
    calls: list[tuple[str, dict[str, Any]]] = []

    def execute(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool_name, dict(tool_args)))
        return {"ok": True, "tool": tool_name, "args": tool_args}

    return calls, execute


def test_bounded_assistant_executes_tool_and_continues_until_final() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                tool_args={},
                tool_call_id="call_var",
                provider_response_id="resp_1",
                intent="var_es",
            ),
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_LIMITS,
                tool_args={},
                tool_call_id="call_limits",
                provider_response_id="resp_2",
                intent="limits",
            ),
            RiskAssistantModelResponse(
                intent="summary",
                proposed_answer="Investigation complete.",
                provider_response_id="resp_3",
            ),
        ]
    )
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(
            question="Compare VaR then limits",
            tools=tool_contract_schemas(),
            portfolio_id="global-macro",
            max_rounds=4,
        )
    )

    assert isinstance(result, RiskAssistantResult)
    assert result.stopped_reason == "final"
    assert result.rounds_used == 3
    assert result.proposed_answer == "Investigation complete."
    assert len(result.tool_turns) == 2
    assert result.tool_turns[0].tool_name == "get_var_es"
    assert result.tool_turns[0].tool_call_id == "call_var"
    assert result.tool_turns[0].tool_output == {
        "ok": True,
        "tool": "get_var_es",
        "args": {},
    }
    assert result.tool_turns[1].tool_name == "get_limits"
    assert len(exec_calls) == 2
    assert len(model.complete_requests) == 1
    assert len(model.continue_calls) == 2
    first_continue = model.continue_calls[0]
    assert first_continue["previous_response_id"] == "resp_1"
    assert len(first_continue["tool_outputs"]) == 1
    output = first_continue["tool_outputs"][0]
    assert output.call_id == "call_var"
    assert json.loads(output.output)["tool"] == "get_var_es"
    assert model.continue_calls[1]["previous_response_id"] == "resp_2"


def test_final_tool_turn_still_sends_function_call_output_for_narration() -> None:
    """C03: last permitted tool turn reserves a narration continue."""
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                tool_args={},
                tool_call_id="call_var",
                provider_response_id="resp_1",
                intent="var_es",
            ),
            RiskAssistantModelResponse(
                intent="final",
                proposed_answer="Historical VaR was calculated by QuantLineage.",
                provider_response_id="resp_2",
            ),
        ]
    )
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(
            question="What is 99% VaR?",
            tools=[],
            max_rounds=2,
            max_tool_calls=1,
        )
    )

    assert result.stopped_reason == "final"
    assert result.rounds_used == 2
    assert len(exec_calls) == 1
    assert len(model.complete_requests) == 1
    assert len(model.continue_calls) == 1
    assert len(model.complete_requests) + len(model.continue_calls) == 2
    output = model.continue_calls[0]["tool_outputs"][0]
    assert output.call_id == "call_var"
    assert json.loads(output.output)["tool"] == "get_var_es"
    assert result.proposed_answer == "Historical VaR was calculated by QuantLineage."
    assert model.continue_calls[0].get("reserve_narration") is True


def test_single_model_turn_does_not_add_a_hidden_continue() -> None:
    """C14: max_rounds=1 is a hard provider-call cap; no hidden +1 narration."""
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                tool_args={},
                tool_call_id="call_var",
                provider_response_id="resp_1",
                intent="var_es",
            ),
            RiskAssistantModelResponse(
                intent="final",
                proposed_answer="This continuation must never run.",
                provider_response_id="resp_2",
            ),
        ]
    )
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(
            question="What is 99% VaR?",
            tools=[],
            max_rounds=1,
            max_tool_calls=1,
        )
    )

    assert result.stopped_reason == "round_limit"
    assert result.rounds_used == 1
    assert len(model.complete_requests) == 1
    assert model.continue_calls == []
    assert len(exec_calls) == 0
    assert result.tool_turns == []


def test_tool_budget_exhausted_does_not_execute_another_tool_after_reserved_narration() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_CONTRIBUTORS,
                tool_args={},
                tool_call_id="call_c1",
                provider_response_id="resp_1",
            ),
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_WORST_STRESS,
                tool_args={},
                tool_call_id="call_c2",
                provider_response_id="resp_2",
            ),
        ]
    )
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(
            question="Contributors then stress",
            tools=[],
            max_rounds=2,
            max_tool_calls=1,
        )
    )

    assert result.stopped_reason == "round_limit"
    assert len(result.tool_turns) == 1
    assert len(exec_calls) == 1
    assert len(model.continue_calls) == 1
    assert result.tool_turns[0].tool_name == "get_contributors"


def test_side_effecting_tools_include_riskrun_submitters() -> None:
    assert "run_portfolio_risk" in SIDE_EFFECTING_TOOLS
    assert "run_stress" in SIDE_EFFECTING_TOOLS
    assert "get_top_risk_contributors" in SIDE_EFFECTING_TOOLS


@pytest.mark.parametrize(
    "tool_name",
    [
        RiskToolName.RUN_PORTFOLIO_RISK,
        RiskToolName.RUN_STRESS,
        RiskToolName.GET_TOP_RISK_CONTRIBUTORS,
    ],
)
def test_bounded_assistant_rejects_each_side_effecting_tool(tool_name: RiskToolName) -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=tool_name,
                tool_args={},
                tool_call_id="call_side",
                provider_response_id="resp_1",
            )
        ]
    )
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(question="Run it", tools=[], max_rounds=2)
    )

    assert result.stopped_reason == "refusal"
    assert result.tool_turns == []
    assert exec_calls == []
    assert model.continue_calls == []


def test_bounded_assistant_clarification_stops_without_execution() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                intent="ambiguous",
                requires_clarification=True,
                clarification="Which run id?",
                provider_response_id="resp_1",
            )
        ]
    )
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(question="Explain the change", tools=[], max_rounds=4)
    )

    assert result.stopped_reason == "clarification"
    assert result.clarification == "Which run id?"
    assert result.tool_turns == []
    assert exec_calls == []
    assert model.continue_calls == []


def test_bounded_assistant_refusal_stops_without_execution() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                intent="unsupported",
                refusal="No trading advice.",
                provider_response_id="resp_1",
            )
        ]
    )
    _, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(question="What should I buy?", tools=[], max_rounds=3)
    )

    assert result.stopped_reason == "refusal"
    assert result.refusal == "No trading advice."
    assert result.requires_clarification is True


def test_bounded_assistant_rejects_side_effecting_tools_by_default() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.RUN_PORTFOLIO_RISK,
                tool_args={"run_type": "var"},
                tool_call_id="call_run",
                provider_response_id="resp_1",
            )
        ]
    )
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(question="Run portfolio risk", tools=[], max_rounds=4)
    )

    assert result.stopped_reason == "refusal"
    assert result.tool_turns == []
    assert exec_calls == []
    assert "side-effect" in (result.refusal or "").lower() or "queued" in (
        result.refusal or ""
    ).lower() or "not enabled" in (result.refusal or "").lower()


@pytest.mark.parametrize("max_rounds", [1, 2, 3, 4])
def test_provider_and_tool_counts_are_exact_at_model_turn_limits(max_rounds: int) -> None:
    """C14: provider calls == configured model turns; tools never need a hidden +1."""
    responses = [
        RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_LIMITS,
            tool_args={},
            tool_call_id=f"call_{i}",
            provider_response_id=f"resp_{i}",
        )
        for i in range(1, 8)
    ]
    model = _ScriptedLoopModel(responses)
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(
            question="Keep going",
            tools=[],
            max_rounds=max_rounds,
            max_tool_calls=max_rounds,
        )
    )

    provider_calls = len(model.complete_requests) + len(model.continue_calls)
    expected_tools = max(max_rounds - 1, 0)
    expected_continues = max(max_rounds - 1, 0)
    assert provider_calls == max_rounds
    assert result.rounds_used == max_rounds
    assert result.stopped_reason == "round_limit"
    assert len(exec_calls) == expected_tools
    assert len(result.tool_turns) == expected_tools
    assert len(model.complete_requests) == 1
    assert len(model.continue_calls) == expected_continues
    if expected_continues:
        assert model.continue_calls[-1]["reserve_narration"] is True


def test_bounded_assistant_caps_max_rounds_at_four() -> None:
    responses = [
        RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_LIMITS,
            tool_args={},
            tool_call_id=f"call_{i}",
            provider_response_id=f"resp_{i}",
        )
        for i in range(1, 6)
    ]
    responses.append(
        RiskAssistantModelResponse(
            intent="final",
            proposed_answer="Stop.",
            provider_response_id="resp_6",
        )
    )
    model = _ScriptedLoopModel(responses)
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    result = assistant.run(
        RiskAssistantRequest(
            question="Keep going",
            tools=[],
            max_rounds=4,
            max_tool_calls=4,
        )
    )

    provider_calls = len(model.complete_requests) + len(model.continue_calls)
    assert provider_calls == 4
    assert result.rounds_used == 4
    assert len(exec_calls) == 3
    assert len(model.continue_calls) == 3
    assert model.continue_calls[-1]["reserve_narration"] is True


def test_continue_type_error_invokes_adapter_once_and_raises_parse_error() -> None:
    """C14: no except TypeError retry that double-invokes continue_after_tools."""

    class _TypeErrorContinueModel:
        def __init__(self) -> None:
            self.complete_count = 0
            self.continue_count = 0

        def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
            del request
            self.complete_count += 1
            return RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                tool_args={},
                tool_call_id="call_var",
                provider_response_id="resp_1",
                intent="var_es",
            )

        def continue_after_tools(self, **kwargs: Any) -> RiskAssistantModelResponse:
            del kwargs
            self.continue_count += 1
            raise TypeError("got an unexpected keyword argument 'reserve_narration'")

    model = _TypeErrorContinueModel()
    exec_calls, execute = _executor_recording()
    assistant = BoundedRiskAssistant(model, execute)

    with pytest.raises(OpenAIModelParseError):
        assistant.run(
            RiskAssistantRequest(
                question="What is 99% VaR?",
                tools=[],
                max_rounds=2,
                max_tool_calls=1,
            )
        )

    assert model.complete_count == 1
    assert model.continue_count == 1
    assert len(exec_calls) == 1


def test_tool_executor_error_is_returned_as_function_output_and_loop_continues() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_RISK_RUN,
                tool_args={"run_id": "missing"},
                tool_call_id="call_run",
                provider_response_id="resp_1",
            ),
            RiskAssistantModelResponse(
                intent="ambiguous",
                requires_clarification=True,
                clarification="Provide a valid run id.",
                provider_response_id="resp_2",
            ),
        ]
    )

    def execute(_name: str, _args: dict[str, Any]) -> dict[str, Any]:
        from app.services.risk_run_service import RiskRunNotFound

        raise RiskRunNotFound("missing")

    assistant = BoundedRiskAssistant(model, execute)
    result = assistant.run(
        RiskAssistantRequest(question="Get that run", tools=[], max_rounds=4)
    )

    assert result.stopped_reason == "clarification"
    assert len(result.tool_turns) == 1
    assert result.tool_turns[0].tool_error is not None
    payload = json.loads(model.continue_calls[0]["tool_outputs"][0].output)
    error = payload["error"]
    assert error["code"] == "risk_run_not_found"
    assert error["retryable"] is False
    assert "missing" not in json.dumps(payload)
    assert "not found" in error["message"].lower()


def test_function_call_output_model_requires_call_id_and_output_string() -> None:
    from pydantic import ValidationError

    item = FunctionCallOutput(call_id="call_1", output='{"ok": true}')
    assert item.call_id == "call_1"
    assert item.output == '{"ok": true}'
    with pytest.raises(ValidationError):
        FunctionCallOutput(call_id="", output="x")
