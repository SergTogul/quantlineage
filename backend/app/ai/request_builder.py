"""Build minimal OpenAI Responses API requests for one routing turn."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.ai.config import AISettings
from app.ai.policy import ASSISTANT_MULTI_TOOL_POLICY_INSTRUCTION, ASSISTANT_POLICY_INSTRUCTION
from app.ai.tool_schemas import openai_function_tools
from app.risk.query import RiskAssistantModelRequest

_MAX_FUNCTION_OUTPUT_CHARS = 4000


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
            "max_tool_calls": settings.max_tool_rounds,
            "tool_choice": "auto",
        },
        timeout_seconds=settings.timeout_seconds,
    )


def build_openai_followup_request(
    *,
    settings: AISettings,
    previous_response_id: str,
    outputs: list[Any],
) -> OpenAIResponsesRequest:
    """Build a Responses API follow-up with ``function_call_output`` items."""
    if settings.openai_model is None:
        raise ValueError("openai_model is required to build an OpenAI Responses request.")
    if not previous_response_id.strip():
        raise ValueError("previous_response_id is required for a tool-output follow-up.")

    return OpenAIResponsesRequest(
        create_params={
            "model": settings.openai_model,
            "instructions": ASSISTANT_MULTI_TOOL_POLICY_INSTRUCTION
            if settings.multi_tool
            else ASSISTANT_POLICY_INSTRUCTION,
            "previous_response_id": previous_response_id,
            "input": [_function_call_output_item(item) for item in outputs],
            "tools": openai_function_tools(),
            "max_output_tokens": settings.max_output_tokens,
            "max_tool_calls": settings.max_tool_rounds,
            "tool_choice": "auto",
        },
        timeout_seconds=settings.timeout_seconds,
    )


def apply_multi_tool_instructions(payload: OpenAIResponsesRequest) -> OpenAIResponsesRequest:
    """Copy a first-round request onto the multi-tool investigation policy."""
    params = dict(payload.create_params)
    params["instructions"] = ASSISTANT_MULTI_TOOL_POLICY_INSTRUCTION
    return OpenAIResponsesRequest(
        create_params=params,
        timeout_seconds=payload.timeout_seconds,
    )


def _function_call_output_item(output: Any) -> dict[str, Any]:
    payload = {
        "name": getattr(output, "name", None),
        "allowed": getattr(output, "allowed", True),
        "result": getattr(output, "output", {}),
        "error": getattr(output, "error", None),
    }
    serialized = json.dumps(payload, default=str)
    if len(serialized) > _MAX_FUNCTION_OUTPUT_CHARS:
        serialized = serialized[:_MAX_FUNCTION_OUTPUT_CHARS]
    return {
        "type": "function_call_output",
        "call_id": getattr(output, "call_id", ""),
        "output": serialized,
    }


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
    return "\n".join(lines)


def request_payload_text(payload: OpenAIResponsesRequest) -> str:
    """Serialize the outbound request for structural assertions in tests."""
    return json.dumps(payload.create_params, sort_keys=True)
