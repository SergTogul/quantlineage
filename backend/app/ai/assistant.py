"""Multi-tool RiskAssistant protocol (milestone 2 seam).

T20 introduces the orchestration interface and a one-shot adapter over the
existing :class:`~app.risk.query.RiskAssistantModel` so milestone 1 stays intact
until T21 implements the bounded Responses tool loop.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.risk.query import (
    RiskAssistantModel,
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskToolName,
)

StoppedReason = Literal[
    "one_shot",
    "clarification",
    "refusal",
    "tool_selected",
    "round_limit",
    "final",
]


class RiskAssistantToolTurn(BaseModel):
    """One model tool selection (execution is owned by the orchestrator / T21)."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    tool_call_id: str | None = None
    rationale: str | None = None


class RiskAssistantRequest(BaseModel):
    """Input for a bounded investigation turn sequence."""

    model_config = ConfigDict(extra="forbid")

    question: str
    tools: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_id: str | None = None
    available_run_ids: list[str] = Field(default_factory=list)
    max_rounds: int = Field(default=1, ge=1, le=4)


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


class RiskAssistant(Protocol):
    """Higher-level orchestration seam for bounded multi-tool investigations."""

    def run(self, request: RiskAssistantRequest) -> RiskAssistantResult:
        """Run up to ``request.max_rounds`` model turns and return structured results."""


class OneShotRiskAssistant:
    """Milestone-1 compatibility adapter: exactly one :meth:`RiskAssistantModel.complete`.

    Does not execute tools or open a Responses function-output loop (T21).
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
                rationale=response.rationale,
            )
        ],
        rounds_used=1,
        stopped_reason="tool_selected",
        proposed_answer=response.proposed_answer,
    )
