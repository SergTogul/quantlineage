"""HTTP wiring for BoundedRiskAssistant when AI_MAX_TOOL_ROUNDS > 1."""

from __future__ import annotations

from typing import Any

from app.ai.config import AISettings
from app.ai.errors import OpenAITimeoutError
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.query import (
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskToolName,
)
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService


class _ScriptedLoopModel:
    def __init__(self, responses: list[RiskAssistantModelResponse], *, continue_error=None) -> None:
        self._responses = list(responses)
        self.continue_error = continue_error
        self.complete_count = 0
        self.continue_count = 0

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        self.complete_count += 1
        if not self._responses:
            raise AssertionError("complete queue exhausted")
        return self._responses.pop(0)

    def continue_after_tools(self, **_kwargs: Any) -> RiskAssistantModelResponse:
        self.continue_count += 1
        if self.continue_error is not None:
            raise self.continue_error
        if not self._responses:
            raise AssertionError("continue queue exhausted")
        return self._responses.pop(0)


def _settings(*, rounds: int) -> AISettings:
    return AISettings(
        provider="openai",
        openai_model="gpt-test-model",
        timeout_seconds=30.0,
        max_output_tokens=512,
        max_tool_rounds=rounds,
    )


def _service(model, *, rounds: int) -> PortfolioService:
    return PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
        risk_assistant_model=model,
        ai_settings=_settings(rounds=rounds),
    )


def test_default_one_round_stays_on_one_shot_complete() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_CONTRIBUTORS,
                intent="contributors",
            )
        ]
    )
    service = _service(model, rounds=1)

    response = service.query(SAMPLE_PORTFOLIO, "show top risk contributors")

    assert model.complete_count == 1
    assert model.continue_count == 0
    assert response.tool_name == "get_contributors"
    assert response.data.get("investigation") is None


def test_multi_round_http_executes_tools_and_continues() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                intent="var_es",
                tool_call_id="call_var",
                provider_response_id="resp_1",
            ),
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_LIMITS,
                intent="limits",
                tool_call_id="call_limits",
                provider_response_id="resp_2",
            ),
            RiskAssistantModelResponse(
                proposed_answer="Limits and VaR were calculated by QuantLineage tools.",
                intent="final",
                provider_response_id="resp_3",
            ),
        ]
    )
    service = _service(model, rounds=4)

    response = service.query(SAMPLE_PORTFOLIO, "Show VaR then any limit breaches")

    assert model.complete_count == 1
    assert model.continue_count == 2
    assert response.tool_name == "get_limits"
    assert response.data["investigation"]["tool_names"] == [
        "get_var_es",
        "get_limits",
    ]
    assert response.data["investigation"]["rounds_used"] == 3
    assert response.data["investigation"]["narration_grounded"] is True
    assert "assistant" in response.data
    assert response.data["assistant"]["mode"] == "model-routed"
    assert response.data["assistant"]["fallback"] is False


def test_ungrounded_http_narration_falls_back_to_deterministic_formatter() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                intent="var_es",
                tool_call_id="call_var",
                provider_response_id="resp_1",
            ),
            RiskAssistantModelResponse(
                proposed_answer="99% VaR is 999999999.",
                intent="final",
                provider_response_id="resp_2",
            ),
        ]
    )
    service = _service(model, rounds=4)

    response = service.query(SAMPLE_PORTFOLIO, "What is 99% VaR?")

    assert "999999999" not in response.answer
    assert response.data["investigation"]["narration_grounded"] is False
    assert response.tool_name == "get_var_es"


def test_provider_error_after_a_tool_does_not_replay() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_VAR_ES,
                intent="var_es",
                tool_call_id="call_var",
                provider_response_id="resp_1",
            )
        ],
        continue_error=OpenAITimeoutError("timed out"),
    )
    service = _service(model, rounds=4)
    original = service.var_report
    calls = {"n": 0}

    def _count(*args: Any, **kwargs: Any):
        calls["n"] += 1
        return original(*args, **kwargs)

    service.var_report = _count  # type: ignore[method-assign]

    response = service.query(SAMPLE_PORTFOLIO, "What is 99% VaR?")

    assert calls["n"] == 1
    assert model.continue_count == 1
    assert response.requires_clarification is True
    assert response.data["investigation"]["truncated"] is True
    assert response.data["assistant"]["mode"] == "fallback"
    assert response.data["assistant"]["fallback"] is True
    assert "not replayed" in response.answer.lower()


def test_bounded_greeks_question_calls_the_model() -> None:
    model = _ScriptedLoopModel(
        [
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_POSITION_GREEKS,
                tool_args={"greek": "delta"},
                intent="position_greeks",
                tool_call_id="call_greeks",
                provider_response_id="resp_1",
            ),
            RiskAssistantModelResponse(
                proposed_answer="Position delta ranking was calculated by QuantLineage.",
                intent="final",
                provider_response_id="resp_2",
            ),
        ]
    )
    service = _service(model, rounds=2)

    response = service.query(SAMPLE_PORTFOLIO, "Which options have the largest delta?")

    assert model.complete_count == 1
    assert model.continue_count == 1
    assert response.tool_name == "get_position_greeks"
    assert response.data["assistant"]["mode"] == "model-routed"
