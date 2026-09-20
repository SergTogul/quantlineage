"""T22 — Numeric narration grounding."""

from __future__ import annotations

from typing import Any

from app.ai.assistant import (
    BoundedRiskAssistant,
    RiskAssistantRequest,
    RiskAssistantResult,
)
from app.ai.narration import (
    NarrationGroundingResult,
    collect_allowed_numeric_tokens,
    format_tool_turns_deterministically,
    ground_narration,
)
from app.risk.query import (
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskToolName,
)


class _ScriptedLoopModel:
    def __init__(self, responses: list[RiskAssistantModelResponse]) -> None:
        self._responses = list(responses)

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        del request
        return self._responses.pop(0)

    def continue_after_tools(self, **_kwargs: Any) -> RiskAssistantModelResponse:
        return self._responses.pop(0)


def test_ground_narration_accepts_numbers_present_in_payload() -> None:
    payloads = [{"methods": [{"var": 444.0, "expected_shortfall": 555.0, "confidence": 0.99}]}]
    result = ground_narration(
        "Historical 99% VaR is 444 and Expected Shortfall is 555.",
        payloads,
    )
    assert isinstance(result, NarrationGroundingResult)
    assert result.accepted is True
    assert result.rejected_tokens == []
    assert result.narration is not None
    assert "444" in result.narration


def test_ground_narration_rejects_unsupported_numeric_claims() -> None:
    payloads = [{"methods": [{"var": 444.0, "expected_shortfall": 555.0}]}]
    result = ground_narration(
        "99% VaR is 999999999.",
        payloads,
    )
    assert result.accepted is False
    assert any("999999999" in token for token in result.rejected_tokens)
    assert result.narration is None


def test_ground_narration_accepts_non_numeric_prose() -> None:
    result = ground_narration("Investigation complete.", [{"ok": True}])
    assert result.accepted is True
    assert result.narration == "Investigation complete."


def test_collect_allowed_tokens_includes_fmt_and_percent_forms() -> None:
    allowed = collect_allowed_numeric_tokens(
        [{"var_99": 1234.0, "confidence": 0.99}]
    )
    assert "1234" in allowed or "1,234" in allowed
    assert "99" in allowed or "99%" in allowed


def test_bounded_assistant_accepts_grounded_final_narration() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                tool_args={},
                tool_call_id="call_1",
                provider_response_id="resp_1",
            ),
            RiskAssistantModelResponse(
                proposed_answer="Historical VaR is 444.",
                provider_response_id="resp_2",
                intent="final",
            ),
        ]
    )

    def execute(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        del tool_args
        assert tool_name == "get_var_es"
        return {"methods": [{"method": "historical", "var": 444.0, "confidence": 0.99}]}

    assistant = BoundedRiskAssistant(model, execute)
    result = assistant.run(
        RiskAssistantRequest(question="Show VaR", tools=[], max_rounds=4)
    )

    assert result.stopped_reason == "final"
    assert result.proposed_answer == "Historical VaR is 444."
    assert result.narration_grounded is True


def test_bounded_assistant_falls_back_when_narration_has_hallucinated_numbers() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                tool_args={},
                tool_call_id="call_1",
                provider_response_id="resp_1",
            ),
            RiskAssistantModelResponse(
                proposed_answer="99% VaR is 999999999.",
                provider_response_id="resp_2",
                intent="final",
            ),
        ]
    )

    payload = {
        "methods": [
            {
                "method": "historical",
                "confidence": 0.99,
                "var": 444.0,
                "expected_shortfall": 555.0,
            }
        ]
    }

    def execute(_tool_name: str, _tool_args: dict[str, Any]) -> dict[str, Any]:
        return payload

    assistant = BoundedRiskAssistant(model, execute)
    result = assistant.run(
        RiskAssistantRequest(question="Show VaR", tools=[], max_rounds=4)
    )

    assert isinstance(result, RiskAssistantResult)
    assert result.stopped_reason == "final"
    assert result.narration_grounded is False
    assert result.proposed_answer is not None
    assert "999999999" not in result.proposed_answer
    assert "444" in result.proposed_answer
    # Deterministic formatter path
    assert "VaR" in result.proposed_answer


def test_format_tool_turns_deterministically_uses_last_successful_payload() -> None:
    from app.ai.assistant import RiskAssistantToolTurn

    turns = [
        RiskAssistantToolTurn(
            tool_name="get_var_es",
            tool_args={},
            tool_output={
                "methods": [
                    {
                        "method": "historical",
                        "confidence": 0.99,
                        "var": 444.0,
                        "expected_shortfall": 555.0,
                    }
                ]
            },
        )
    ]
    text = format_tool_turns_deterministically(turns)
    assert text is not None
    assert "444" in text
    assert "555" in text
