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
    from app.ai.narration import GroundingClaim, build_grounding_manifest

    claims = build_grounding_manifest(
        "get_var_es",
        {"var_99": 1234.0, "confidence": 0.99},
    )
    assert any(c.metric == "var" and abs(c.value - 1234.0) < 1e-9 for c in claims)
    confidence = next(c for c in claims if c.metric == "confidence")
    assert confidence.unit == "ratio"
    assert confidence.allow_percent_from_fraction is True
    assert all(isinstance(c, GroundingClaim) for c in claims)


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


def test_year_or_id_cannot_ground_invented_var() -> None:
    payloads = [
        {
            "as_of_year": 2024,
            "run_id": "32798",
            "portfolio_id": "p-2024",
            "methods": [{"method": "historical", "var": 100.0, "confidence": 0.99}],
        }
    ]
    year_attack = ground_narration("99% VaR is 2024.", payloads)
    assert year_attack.accepted is False
    assert any("2024" in token for token in year_attack.rejected_tokens)

    id_attack = ground_narration("VaR is 32798.", payloads)
    assert id_attack.accepted is False
    assert any("32798" in token for token in id_attack.rejected_tokens)


def test_delta_value_cannot_ground_a_var_claim() -> None:
    payloads = [
        {
            "greek": "delta",
            "positions": [{"position_id": "opt-1", "greek": "delta", "value": 444.0}],
        }
    ]
    result = ground_narration("Historical 99% VaR is 444.", payloads)
    assert result.accepted is False
    assert any("444" in token for token in result.rejected_tokens)


def test_rounding_and_thousands_formatting_are_tolerated() -> None:
    payloads = [{"methods": [{"var": 32798.4, "confidence": 0.99}]}]
    assert ground_narration("VaR is 32,798.", payloads).accepted is True
    assert ground_narration("VaR is 32798.", payloads).accepted is True
    assert ground_narration("VaR is 32,798.4.", payloads).accepted is True
    assert ground_narration("VaR is 32000.", payloads).accepted is False


def test_fraction_to_percent_only_for_percentage_or_ratio_fields() -> None:
    percent_ok = ground_narration(
        "Contribution share is 42%.",
        [{"contribution_pct": 42.0, "count": 42}],
    )
    assert percent_ok.accepted is True

    ratio_ok = ground_narration(
        "Historical 99% VaR is 444.",
        [{"methods": [{"var": 444.0, "confidence": 0.99}]}],
    )
    assert ratio_ok.accepted is True

    not_percent = ground_narration(
        "VaR is 50%.",
        [{"methods": [{"var": 0.5, "confidence": 0.99}]}],
    )
    assert not_percent.accepted is False


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
