"""OpenAI Responses API adapter for one QuantLineage tool-selection turn."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from app.ai.config import AISettings, get_openai_api_key
from app.ai.errors import (
    OpenAIIncompleteResponseError,
    OpenAIMalformedToolArgumentsError,
    OpenAIModelParseError,
    OpenAIMultipleToolCallsError,
    map_openai_sdk_error,
    redact_request_kwargs,
    sanitize_provider_message,
)
from app.ai.request_builder import build_openai_responses_request
from app.risk.query import RiskAssistantModelRequest, RiskAssistantModelResponse

logger = logging.getLogger(__name__)

_DEFAULT_CLARIFICATION = (
    "Please choose a deterministic risk view: VaR/ES, limits, contributors, "
    "worst stress, or portfolio summary."
)


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
        """Return one tool request, clarification, or refusal from OpenAI.

        Incomplete Responses API outputs are retried once before raising.
        """
        openai_request = build_openai_responses_request(request, self._settings)
        create_kwargs = {
            **openai_request.create_params,
            "timeout": openai_request.timeout_seconds,
        }
        last_incomplete: OpenAIIncompleteResponseError | None = None
        for attempt in range(2):
            try:
                sdk_response = self._client.responses.create(**create_kwargs)
            except Exception as exc:
                mapped = map_openai_sdk_error(exc, api_key=get_openai_api_key())
                logger.warning(
                    "OpenAI provider error (%s): %s",
                    mapped.code,
                    mapped,
                    extra={
                        "error_code": mapped.code,
                        "request": redact_request_kwargs(
                            create_kwargs,
                            api_key=get_openai_api_key(),
                        ),
                    },
                )
                raise mapped from exc
            try:
                return _parse_sdk_response(sdk_response)
            except OpenAIIncompleteResponseError as exc:
                last_incomplete = exc
                if attempt == 0:
                    logger.warning(
                        "OpenAI incomplete response; retrying once: %s",
                        exc,
                        extra={"error_code": exc.code, "attempt": attempt},
                    )
                    continue
                raise
        assert last_incomplete is not None  # pragma: no cover - loop always sets
        raise last_incomplete


def _parse_sdk_response(response: Any) -> RiskAssistantModelResponse:
    _raise_for_incomplete_response(response)

    output = getattr(response, "output", None) or []
    function_calls = [
        item for item in output if getattr(item, "type", None) == "function_call"
    ]
    assistant_text = _extract_assistant_text(output)
    rationale = _optional_rationale(assistant_text)

    if not function_calls:
        return _parse_text_only_response(output, assistant_text)

    if len(function_calls) > 1:
        raise OpenAIMultipleToolCallsError(
            f"Expected at most one function call, got {len(function_calls)}."
        )

    call = function_calls[0]
    name = getattr(call, "name", None)
    if not name:
        raise OpenAIModelParseError("Function call is missing a tool name.")

    raw_arguments = getattr(call, "arguments", None)
    try:
        tool_args = json.loads(raw_arguments if raw_arguments else "{}")
    except json.JSONDecodeError as exc:
        raise OpenAIMalformedToolArgumentsError(
            f"Malformed function call arguments for {name!r}."
        ) from exc
    if not isinstance(tool_args, dict):
        raise OpenAIMalformedToolArgumentsError(
            f"Function call arguments must be a JSON object for {name!r}."
        )

    return RiskAssistantModelResponse(
        tool_name=name,
        tool_args=tool_args,
        rationale=rationale,
        proposed_answer=None,
    )


def _raise_for_incomplete_response(response: Any) -> None:
    status = getattr(response, "status", None)
    if status not in {"incomplete", "failed"}:
        return

    error = getattr(response, "error", None)
    raw_message = getattr(error, "message", None) if error is not None else None
    message = sanitize_provider_message(
        raw_message or f"OpenAI response status was {status!r}.",
        api_key=get_openai_api_key(),
    )
    raise OpenAIIncompleteResponseError(message)


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
    if text and not _contains_numeric_prose(text):
        return RiskAssistantModelResponse(
            intent="ambiguous",
            requires_clarification=True,
            clarification=text,
            proposed_answer=None,
        )

    return RiskAssistantModelResponse(
        intent="ambiguous",
        requires_clarification=True,
        clarification=_DEFAULT_CLARIFICATION,
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
    if _contains_numeric_prose(text):
        return None
    return text.strip()


def _contains_numeric_prose(text: str) -> bool:
    return any(character.isdigit() for character in text)
