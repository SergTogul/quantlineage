"""Multi-tool RiskAssistant protocol and bounded Responses tool loop.

T20 introduced the orchestration interface and one-shot adapter.
T21 adds :class:`BoundedRiskAssistant` which executes validated tools, appends
``function_call_output`` items, and continues for at most four rounds.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.ai.narration import (
    format_tool_turns_deterministically,
    ground_narration,
)
from app.risk.query import (
    RiskAssistantModel,
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskToolName,
    validate_tool_call,
)

StoppedReason = Literal[
    "one_shot",
    "clarification",
    "refusal",
    "tool_selected",
    "round_limit",
    "final",
]

SIDE_EFFECTING_TOOLS: frozenset[str] = frozenset(
    {
        RiskToolName.RUN_PORTFOLIO_RISK.value,
        RiskToolName.RUN_STRESS.value,
        RiskToolName.GET_TOP_RISK_CONTRIBUTORS.value,
    }
)

_SIDE_EFFECT_REFUSAL = (
    "Queued or side-effecting risk tools are not enabled in the bounded "
    "investigation loop. Ask for a read-only risk view, or enable side-effecting "
    "tools explicitly."
)

ToolExecutor = Callable[[str, dict[str, Any]], Any]


class FunctionCallOutput(BaseModel):
    """One Responses API ``function_call_output`` item."""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1)
    output: str = Field(min_length=1)


class RiskAssistantToolTurn(BaseModel):
    """One model tool selection and optional execution result."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    tool_call_id: str | None = None
    rationale: str | None = None
    tool_output: dict[str, Any] | None = None
    tool_error: str | None = None


class RiskAssistantRequest(BaseModel):
    """Input for a bounded investigation turn sequence."""

    model_config = ConfigDict(extra="forbid")

    question: str
    tools: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_id: str | None = None
    available_run_ids: list[str] = Field(default_factory=list)
    max_rounds: int = Field(default=2, ge=1, le=4)
    max_tool_calls: int = Field(default=4, ge=1, le=4)


class RiskAssistantResult(BaseModel):
    """Structured outcome of :meth:`RiskAssistant.run` (no secrets / CoT)."""

    model_config = ConfigDict(extra="forbid")

    intent: str | None = None
    requires_clarification: bool = False
    clarification: str | None = None
    refusal: str | None = None
    proposed_answer: str | None = None
    tool_turns: list[RiskAssistantToolTurn] = Field(default_factory=list)
    rounds_used: int = Field(default=0, ge=0)
    stopped_reason: StoppedReason = "one_shot"
    narration_grounded: bool | None = None


class RiskAssistant(Protocol):
    """Higher-level orchestration seam for bounded multi-tool investigations."""

    def run(self, request: RiskAssistantRequest) -> RiskAssistantResult:
        """Run up to ``request.max_rounds`` model turns and return structured results."""


class RiskAssistantLoopModel(Protocol):
    """Model surface required by :class:`BoundedRiskAssistant`."""

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        """First Responses turn."""

    def continue_after_tools(
        self,
        *,
        previous_response_id: str,
        tool_outputs: Sequence[FunctionCallOutput],
        request: RiskAssistantModelRequest,
        reserve_narration: bool = False,
    ) -> RiskAssistantModelResponse:
        """Continue after appending ``function_call_output`` items."""


class OneShotRiskAssistant:
    """Milestone-1 compatibility adapter: exactly one :meth:`RiskAssistantModel.complete`.

    Does not execute tools or open a Responses function-output loop.
    """

    def __init__(self, model: RiskAssistantModel) -> None:
        self._model = model

    def run(self, request: RiskAssistantRequest) -> RiskAssistantResult:
        model_request = RiskAssistantModelRequest(
            question=request.question,
            tools=request.tools,
            portfolio_id=request.portfolio_id,
            available_run_ids=list(request.available_run_ids),
        )
        response = self._model.complete(model_request)
        return _result_from_one_shot(response)


class BoundedRiskAssistant:
    """Application-managed Responses tool loop (≤4 rounds).

    Executes allowlisted read-only tools, appends ``function_call_output``, and
    continues until a final answer, clarification/refusal, or round limit.
    """

    def __init__(
        self,
        model: RiskAssistantLoopModel,
        tool_executor: ToolExecutor,
        *,
        allow_side_effecting: bool = False,
    ) -> None:
        self._model = model
        self._tool_executor = tool_executor
        self._allow_side_effecting = allow_side_effecting

    def run(self, request: RiskAssistantRequest) -> RiskAssistantResult:
        max_model_turns = min(max(request.max_rounds, 1), 4)
        max_tool_calls = min(max(request.max_tool_calls, 1), 4)
        model_request = RiskAssistantModelRequest(
            question=request.question,
            tools=request.tools,
            portfolio_id=request.portfolio_id,
            available_run_ids=list(request.available_run_ids),
        )

        tool_turns: list[RiskAssistantToolTurn] = []
        pending_outputs: list[FunctionCallOutput] | None = None
        previous_response_id: str | None = None
        last_response: RiskAssistantModelResponse | None = None
        reserve_narration = False
        # One extra slot beyond the model-turn budget for a reserved narration continue.
        for round_index in range(1, max_model_turns + 2):
            if round_index == 1:
                response = self._model.complete(model_request)
            else:
                assert previous_response_id is not None
                assert pending_outputs is not None
                continue_kwargs: dict[str, Any] = {
                    "previous_response_id": previous_response_id,
                    "tool_outputs": pending_outputs,
                    "request": model_request,
                }
                try:
                    response = self._model.continue_after_tools(
                        **continue_kwargs,
                        reserve_narration=reserve_narration,
                    )
                except TypeError:
                    response = self._model.continue_after_tools(**continue_kwargs)
            last_response = response

            if response.refusal:
                return RiskAssistantResult(
                    intent=response.intent or "unsupported",
                    requires_clarification=True,
                    refusal=response.refusal,
                    tool_turns=tool_turns,
                    rounds_used=round_index,
                    stopped_reason="refusal",
                )
            if response.requires_clarification or (
                response.tool_name is None and not response.proposed_answer
            ):
                return RiskAssistantResult(
                    intent=response.intent or "ambiguous",
                    requires_clarification=True,
                    clarification=response.clarification,
                    tool_turns=tool_turns,
                    rounds_used=round_index,
                    stopped_reason="clarification",
                )
            if response.tool_name is None and response.proposed_answer:
                return self._finalize_narration(
                    response=response,
                    tool_turns=tool_turns,
                    rounds_used=round_index,
                )

            tool_name = response.tool_name
            if isinstance(tool_name, RiskToolName):
                tool_name = tool_name.value
            tool_name_str = str(tool_name)

            if (
                not self._allow_side_effecting
                and tool_name_str in SIDE_EFFECTING_TOOLS
            ):
                return RiskAssistantResult(
                    intent="unsupported",
                    requires_clarification=True,
                    refusal=_SIDE_EFFECT_REFUSAL,
                    tool_turns=tool_turns,
                    rounds_used=round_index,
                    stopped_reason="refusal",
                )

            if reserve_narration or len(tool_turns) >= max_tool_calls:
                return RiskAssistantResult(
                    intent=response.intent,
                    tool_turns=tool_turns,
                    rounds_used=round_index,
                    stopped_reason="round_limit",
                )

            checked = validate_tool_call(tool_name_str, response.tool_args)
            if not checked.allowed or checked.tool_name is None:
                return RiskAssistantResult(
                    intent="unsupported",
                    requires_clarification=True,
                    refusal=checked.refusal
                    or "Unknown tool is not in the QuantLineage allowlist.",
                    tool_turns=tool_turns,
                    rounds_used=round_index,
                    stopped_reason="refusal",
                )

            call_id = response.tool_call_id or f"call_round_{round_index}"
            turn, output_item = self._execute_turn(
                tool_name=checked.tool_name.value,
                tool_args=dict(checked.args or {}),
                tool_call_id=call_id,
                rationale=response.rationale,
            )
            tool_turns.append(turn)
            pending_outputs = [output_item]
            previous_response_id = (
                response.provider_response_id or f"resp_round_{round_index}"
            )
            reserve_narration = (
                len(tool_turns) >= max_tool_calls or round_index >= max_model_turns
            )
            # Always continue so the executed result is sent as function_call_output.

        assert last_response is not None
        return RiskAssistantResult(
            intent=last_response.intent,
            tool_turns=tool_turns,
            rounds_used=max_model_turns + 1,
            stopped_reason="round_limit",
        )

    def _finalize_narration(
        self,
        *,
        response: RiskAssistantModelResponse,
        tool_turns: list[RiskAssistantToolTurn],
        rounds_used: int,
        stopped_reason: StoppedReason = "final",
    ) -> RiskAssistantResult:
        payloads = [
            turn.tool_output
            for turn in tool_turns
            if isinstance(turn.tool_output, dict)
        ]
        grounding = ground_narration(response.proposed_answer or "", payloads)
        if grounding.accepted:
            return RiskAssistantResult(
                intent=response.intent or "final",
                proposed_answer=grounding.narration,
                tool_turns=tool_turns,
                rounds_used=rounds_used,
                stopped_reason=stopped_reason,
                narration_grounded=True,
            )

        fallback = format_tool_turns_deterministically(tool_turns)
        return RiskAssistantResult(
            intent=response.intent or "final",
            proposed_answer=fallback,
            tool_turns=tool_turns,
            rounds_used=rounds_used,
            stopped_reason=stopped_reason,
            narration_grounded=False,
        )

    def _execute_turn(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_call_id: str,
        rationale: str | None,
    ) -> tuple[RiskAssistantToolTurn, FunctionCallOutput]:
        try:
            raw = self._tool_executor(tool_name, tool_args)
            if isinstance(raw, dict):
                payload: dict[str, Any] = raw
            else:
                payload = {"result": raw}
            turn = RiskAssistantToolTurn(
                tool_name=tool_name,
                tool_args=tool_args,
                tool_call_id=tool_call_id,
                rationale=rationale,
                tool_output=payload,
            )
            output = FunctionCallOutput(
                call_id=tool_call_id,
                output=json.dumps(payload, default=str, sort_keys=True),
            )
            return turn, output
        except Exception as exc:
            from app.ai.config import get_openai_api_key
            from app.ai.errors import log_tool_exception, safe_tool_error_payload

            log_tool_exception(exc, api_key=get_openai_api_key())
            error_payload = safe_tool_error_payload(exc, api_key=get_openai_api_key())
            turn = RiskAssistantToolTurn(
                tool_name=tool_name,
                tool_args=tool_args,
                tool_call_id=tool_call_id,
                rationale=rationale,
                tool_error=error_payload["error"]["message"],
            )
            output = FunctionCallOutput(
                call_id=tool_call_id,
                output=json.dumps(error_payload, sort_keys=True),
            )
            return turn, output


def adapt_model_as_assistant(model: RiskAssistantModel) -> RiskAssistant:
    """Wrap a milestone-1 model as a :class:`RiskAssistant` without changing behavior."""
    return OneShotRiskAssistant(model)


def _result_from_one_shot(response: RiskAssistantModelResponse) -> RiskAssistantResult:
    if response.refusal:
        return RiskAssistantResult(
            intent=response.intent or "unsupported",
            requires_clarification=True,
            refusal=response.refusal,
            rounds_used=1,
            stopped_reason="refusal",
        )
    if response.requires_clarification or response.tool_name is None:
        return RiskAssistantResult(
            intent=response.intent or "ambiguous",
            requires_clarification=True,
            clarification=response.clarification,
            rounds_used=1,
            stopped_reason="clarification",
        )

    tool_name = response.tool_name
    if isinstance(tool_name, RiskToolName):
        tool_name = tool_name.value

    return RiskAssistantResult(
        intent=response.intent,
        tool_turns=[
            RiskAssistantToolTurn(
                tool_name=str(tool_name),
                tool_args=dict(response.tool_args or {}),
                tool_call_id=response.tool_call_id,
                rationale=response.rationale,
            )
        ],
        rounds_used=1,
        stopped_reason="tool_selected",
        proposed_answer=response.proposed_answer,
    )
