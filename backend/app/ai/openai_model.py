"""OpenAI Responses API adapter for one QuantLineage tool-selection turn."""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.ai.config import AISettings
from app.ai.request_builder import build_openai_responses_request
from app.risk.query import RiskAssistantModelRequest, RiskAssistantModelResponse


class OpenAIResponsesClient(Protocol):
    """Minimal client surface used by :class:`OpenAIRiskAssistantModel`."""

    class ResponsesResource(Protocol):
        def create(self, **kwargs: Any) -> Any: ...

    responses: ResponsesResource


class OpenAIRiskAssistantModel:
    """OpenAI-backed model adapter for one strict tool-selection turn."""

    def __init__(
        self,
        client: OpenAIResponsesClient,
        settings: AISettings,
    ) -> None:
        self._client = client
        self._settings = settings

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        """Return one tool request, clarification, or refusal from OpenAI."""
        openai_request = build_openai_responses_request(request, self._settings)
        sdk_response = self._client.responses.create(
            **openai_request.create_params,
            timeout=openai_request.timeout_seconds,
        )
        return _parse_sdk_response(sdk_response)


def _parse_sdk_response(response: Any) -> RiskAssistantModelResponse:
    output = getattr(response, "output", None) or []
    function_calls = [
        item for item in output if getattr(item, "type", None) == "function_call"
    ]
    assistant_text = _extract_assistant_text(output)
    rationale = _optional_rationale(assistant_text)

    if not function_calls:
        return _parse_text_only_response(output, assistant_text)

    if len(function_calls) > 1:
        raise ValueError(
            f"Expected at most one function call, got {len(function_calls)}."
        )

    call = function_calls[0]
    name = getattr(call, "name", None)
    if not name:
        raise ValueError("Function call is missing a tool name.")

    raw_arguments = getattr(call, "arguments", None)
    try:
        tool_args = json.loads(raw_arguments if raw_arguments else "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Malformed function call arguments for {name!r}."
        ) from exc
    if not isinstance(tool_args, dict):
        raise ValueError(f"Function call arguments must be a JSON object for {name!r}.")

    return RiskAssistantModelResponse(
        tool_name=name,
        tool_args=tool_args,
        rationale=rationale,
        proposed_answer=None,
    )


def _parse_text_only_response(
    output: list[Any],
    assistant_text: str | None,
) -> RiskAssistantModelResponse:
    refusal_text = _extract_refusal_text(output)
    if refusal_text:
        return RiskAssistantModelResponse(
            intent="unsupported",
            refusal=refusal_text,
            proposed_answer=None,
        )

    text = (assistant_text or "").strip()
    if text:
        return RiskAssistantModelResponse(
            intent="ambiguous",
            requires_clarification=True,
            clarification=text,
            proposed_answer=None,
        )

    return RiskAssistantModelResponse(
        intent="ambiguous",
        requires_clarification=True,
        clarification=(
            "Please choose a deterministic risk view: VaR/ES, limits, contributors, "
            "worst stress, or portfolio summary."
        ),
        proposed_answer=None,
    )


def _extract_assistant_text(output: list[Any]) -> str | None:
    parts: list[str] = []
    for item in output:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "output_text":
                text = getattr(content, "text", None)
                if text:
                    parts.append(text)
    if not parts:
        return None
    return "\n".join(parts)


def _extract_refusal_text(output: list[Any]) -> str | None:
    parts: list[str] = []
    for item in output:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "refusal":
                text = getattr(content, "refusal", None)
                if text:
                    parts.append(text)
    if not parts:
        return None
    return " ".join(part.strip() for part in parts if part.strip())


def _optional_rationale(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    if any(character.isdigit() for character in text):
        return None
    return text.strip()
