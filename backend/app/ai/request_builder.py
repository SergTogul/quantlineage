"""Build minimal OpenAI Responses API requests for routing and tool-loop turns."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from app.ai.config import AISettings
from app.ai.policy import (
    ASSISTANT_POLICY_INSTRUCTION,
    NARRATION_POLICY_INSTRUCTION,
    ROUTING_POLICY_INSTRUCTION,
)
from app.ai.tool_schemas import openai_function_tools
from app.risk.query import RiskAssistantModelRequest

# One function call per Responses create(); the assistant owns the round budget.
_MAX_TOOL_CALLS_PER_ROUND = 1


@dataclass(frozen=True, slots=True)
class OpenAIResponsesRequest:
    """SDK kwargs plus client timeout for one assistant routing turn."""

    create_params: dict[str, Any]
    timeout_seconds: float


def build_openai_responses_request(
    request: RiskAssistantModelRequest,
    settings: AISettings,
) -> OpenAIResponsesRequest:
    """Build a minimal Responses API payload from the model request and settings."""
    if settings.openai_model is None:
        raise ValueError("openai_model is required to build an OpenAI Responses request.")

    return OpenAIResponsesRequest(
        create_params={
            "model": settings.openai_model,
            "instructions": ASSISTANT_POLICY_INSTRUCTION,
            "input": _format_user_input(request),
            "tools": openai_function_tools(),
            "max_output_tokens": settings.max_output_tokens,
            "max_tool_calls": _MAX_TOOL_CALLS_PER_ROUND,
            "tool_choice": "auto",
        },
        timeout_seconds=settings.timeout_seconds,
    )


def build_openai_continue_request(
    *,
    previous_response_id: str,
    tool_outputs: Sequence[Any],
    settings: AISettings,
    reserve_narration: bool = False,
) -> OpenAIResponsesRequest:
    """Continue a Responses turn with ``function_call_output`` items.

    Every continue, including ``previous_response_id`` turns, supplies a
    versioned instruction: routing policy while tools may still be selected,
    narration policy when ``reserve_narration`` is true.

    ``settings.max_tool_rounds`` / ``max_tool_calls`` are owned by
    :class:`BoundedRiskAssistant`. Each continue still allows at most one tool
    call unless ``reserve_narration`` forces a final text turn.
    """
    if settings.openai_model is None:
        raise ValueError("openai_model is required to build an OpenAI Responses request.")
    if not previous_response_id.strip():
        raise ValueError("previous_response_id is required to continue a Responses turn.")

    input_items: list[dict[str, str]] = []
    for item in tool_outputs:
        call_id = getattr(item, "call_id", None)
        output = getattr(item, "output", None)
        if not call_id or output is None:
            raise ValueError("Each tool output must provide call_id and output.")
        input_items.append(
            {
                "type": "function_call_output",
                "call_id": str(call_id),
                "output": str(output),
            }
        )
    if not input_items:
        raise ValueError("At least one function_call_output is required to continue.")

    create_params: dict[str, Any] = {
        "model": settings.openai_model,
        "instructions": (
            NARRATION_POLICY_INSTRUCTION
            if reserve_narration
            else ROUTING_POLICY_INSTRUCTION
        ),
        "previous_response_id": previous_response_id.strip(),
        "input": input_items,
        "tools": openai_function_tools(),
        "max_output_tokens": settings.max_output_tokens,
        "tool_choice": "none" if reserve_narration else "auto",
    }
    if not reserve_narration:
        create_params["max_tool_calls"] = _MAX_TOOL_CALLS_PER_ROUND

    return OpenAIResponsesRequest(
        create_params=create_params,
        timeout_seconds=settings.timeout_seconds,
    )


def _format_user_input(request: RiskAssistantModelRequest) -> str:
    lines = [f"Question: {request.question.strip()}"]
    context_parts: list[str] = []
    if request.portfolio_id:
        context_parts.append(f"portfolio_id={request.portfolio_id}")
    if request.available_run_ids:
        context_parts.append(
            "available_run_ids=" + ",".join(request.available_run_ids)
        )
    if context_parts:
        lines.append("Routing context: " + "; ".join(context_parts))
    if request.conversation_history:
        lines.append("Prior conversation:")
        for turn in request.conversation_history:
            question = str(turn.get("question") or "").strip()
            tool_name = str(turn.get("tool_name") or "").strip()
            tool_args = turn.get("tool_args") or {}
            if question:
                lines.append(f"- User: {question}")
            if tool_name:
                lines.append(f"  Tool: {tool_name} args={json.dumps(tool_args, sort_keys=True)}")
    return "\n".join(lines)


def request_payload_text(payload: OpenAIResponsesRequest) -> str:
    """Serialize the outbound request for structural assertions in tests."""
    return json.dumps(payload.create_params, sort_keys=True)
