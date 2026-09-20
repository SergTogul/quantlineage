"""Higher-level RiskAssistant protocol for bounded multi-tool investigation.

Milestone 1 keeps :class:`~app.risk.query.RiskAssistantModel` as the one-tool
adapter. This module adds a turn-based interface that T21 can loop without
executing tools inside the model adapter.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.risk.query import RiskAssistantModel, RiskAssistantModelRequest, RiskAssistantModelResponse

ONE_TOOL_CALL_ID = "call_0"

_MULTI_ROUND_UNSUPPORTED = (
    "The one-tool assistant cannot continue after a prior tool result. "
    "Ask a single supported risk question."
)


class RiskAssistantToolCall(BaseModel):
    """One allowlisted function call requested by the model. Never executed here."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class RiskAssistantToolOutput(BaseModel):
    """Application-executed tool result to send back on a later turn (T21)."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    name: str
    output: dict[str, Any] = Field(default_factory=dict)
    allowed: bool = True
    error: str | None = None


class RiskAssistantRequest(BaseModel):
    """One orchestration turn. Prior outputs enable the T21 Responses loop."""

    model_config = ConfigDict(extra="forbid")

    question: str
    tools: list[dict[str, Any]]
    portfolio_id: str | None = None
    available_run_ids: list[str] = Field(default_factory=list)
    prior_outputs: list[RiskAssistantToolOutput] = Field(default_factory=list)
    previous_response_id: str | None = None
    round_index: int = 0
    max_rounds: int = 1
    instruction: str = (
        "Select at most one deterministic QuantLineage tool. Do not calculate or invent "
        "VaR, Greeks, P&L, prices, stress losses, or limit values. Ask for clarification "
        "or refuse unsupported/advisory prompts instead of calling a numerical tool."
    )


class RiskAssistantTurn(BaseModel):
    """Model decision for one turn. The application executes tools, if any."""

    model_config = ConfigDict(extra="forbid")

    tool_calls: list[RiskAssistantToolCall] = Field(default_factory=list)
    finished: bool = False
    requires_clarification: bool = False
    clarification: str | None = None
    refusal: str | None = None
    intent: str | None = None
    rationale: str | None = None
    proposed_answer: str | None = None
    response_id: str | None = None


class RiskAssistant(Protocol):
    """Provider-agnostic assistant that proposes turns and never executes tools."""

    def complete_turn(self, request: RiskAssistantRequest) -> RiskAssistantTurn:
        """Return tool calls, a clarification, or a refusal for this round."""


def to_model_request(request: RiskAssistantRequest) -> RiskAssistantModelRequest:
    """Project a multi-tool request onto the milestone 1 one-shot model request."""
    return RiskAssistantModelRequest(
        question=request.question,
        tools=request.tools,
        portfolio_id=request.portfolio_id,
        available_run_ids=list(request.available_run_ids),
        instruction=request.instruction,
    )


def model_response_to_turn(response: RiskAssistantModelResponse) -> RiskAssistantTurn:
    """Adapt one milestone 1 model response into a RiskAssistant turn."""
    if (
        response.refusal
        or response.requires_clarification
        or response.tool_name is None
    ):
        return RiskAssistantTurn(
            tool_calls=[],
            finished=True,
            requires_clarification=bool(
                response.requires_clarification or not response.refusal
            ),
            clarification=response.clarification,
            refusal=response.refusal,
            intent=response.intent,
            rationale=response.rationale,
            proposed_answer=response.proposed_answer,
        )
    return RiskAssistantTurn(
        tool_calls=[
            RiskAssistantToolCall(
                call_id=ONE_TOOL_CALL_ID,
                name=response.tool_name,
                arguments=dict(response.tool_args),
            )
        ],
        finished=False,
        intent=response.intent,
        rationale=response.rationale,
        proposed_answer=response.proposed_answer,
    )


class OneToolRiskAssistant:
    """Compatibility adapter: wrap :class:`RiskAssistantModel` as :class:`RiskAssistant`.

    Produces at most one tool call and refuses to continue a multi-round loop.
    Does not execute tools.
    """

    def __init__(self, model: RiskAssistantModel) -> None:
        self.model = model

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        """Delegate to the wrapped milestone 1 adapter."""
        return self.model.complete(request)

    def complete_turn(self, request: RiskAssistantRequest) -> RiskAssistantTurn:
        """Return one tool call or a safe stop. Never executes a tool."""
        if request.round_index != 0 or request.prior_outputs:
            return RiskAssistantTurn(
                tool_calls=[],
                finished=True,
                requires_clarification=True,
                clarification=_MULTI_ROUND_UNSUPPORTED,
                intent="ambiguous",
                proposed_answer=None,
            )
        model_response = self.model.complete(to_model_request(request))
        return model_response_to_turn(model_response)
