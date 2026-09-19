"""Construct the configured risk-assistant provider once per application lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.config import AISettings, get_ai_settings, get_openai_api_key
from app.ai.openai_model import OpenAIRiskAssistantModel
from app.risk.query import RiskAssistantModel


def load_application_dotenv() -> None:
    """Load ``.env`` once at startup without overriding exported variables."""
    from dotenv import load_dotenv

    load_dotenv(override=False)


@dataclass(slots=True)
class RiskAssistantResources:
    """Resolved AI settings plus an optional model adapter for one process."""

    settings: AISettings
    model: RiskAssistantModel | None
    _openai_client: Any | None = field(default=None, repr=False)

    def close(self) -> None:
        """Release SDK resources when the application shuts down."""
        if self._openai_client is None:
            return
        close = getattr(self._openai_client, "close", None)
        if callable(close):
            close()


def build_risk_assistant_resources(
    *,
    settings: AISettings | None = None,
) -> RiskAssistantResources:
    """Build provider resources from settings without introducing module globals.

    Deterministic mode returns ``model=None`` and never constructs an OpenAI client.
    OpenAI mode constructs one reusable SDK client and adapter.
    """
    resolved = settings or get_ai_settings()
    if resolved.provider == "deterministic":
        return RiskAssistantResources(settings=resolved, model=None)

    api_key = get_openai_api_key()
    if api_key is None:
        raise ValueError(
            "OPENAI_API_KEY is required when AI_PROVIDER=openai."
        )

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = OpenAIRiskAssistantModel(client, resolved)
    return RiskAssistantResources(
        settings=resolved,
        model=model,
        _openai_client=client,
    )
