"""AI provider configuration and adapters (OpenAI risk assistant)."""

from app.ai.assistant import (
    BoundedRiskAssistant,
    FunctionCallOutput,
    OneShotRiskAssistant,
    RiskAssistant,
    RiskAssistantRequest,
    RiskAssistantResult,
    RiskAssistantToolTurn,
    SIDE_EFFECTING_TOOLS,
    adapt_model_as_assistant,
)
from app.ai.config import AISettings, get_ai_settings, get_openai_api_key
from app.ai.policy import ASSISTANT_POLICY_INSTRUCTION, ASSISTANT_POLICY_VERSION
from app.ai.request_builder import (
    OpenAIResponsesRequest,
    build_openai_continue_request,
    build_openai_responses_request,
)

__all__ = [
    "AISettings",
    "ASSISTANT_POLICY_INSTRUCTION",
    "ASSISTANT_POLICY_VERSION",
    "BoundedRiskAssistant",
    "FunctionCallOutput",
    "OneShotRiskAssistant",
    "OpenAIResponsesRequest",
    "RiskAssistant",
    "RiskAssistantRequest",
    "RiskAssistantResult",
    "RiskAssistantToolTurn",
    "SIDE_EFFECTING_TOOLS",
    "adapt_model_as_assistant",
    "build_openai_continue_request",
    "build_openai_responses_request",
    "get_ai_settings",
    "get_openai_api_key",
]
