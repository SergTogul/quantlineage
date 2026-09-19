"""T14 — Opt-in live OpenAI routing smoke test.

Skipped unless both ``OPENAI_API_KEY`` and ``RUN_LIVE_AI_TESTS=1`` are set.
Normal CI never sets the run flag, so this file is network-free in default pipelines.
"""

from __future__ import annotations

import os

import pytest

from app.ai.config import get_ai_settings, get_openai_api_key
from app.ai.factory import RiskAssistantResources, build_risk_assistant_resources
from app.risk.query import (
    TOOL_CONTRACTS,
    RiskAssistantModelRequest,
    RiskToolName,
    tool_contract_schemas,
)

pytestmark = pytest.mark.live_ai

_LIVE_RUN_FLAG = "RUN_LIVE_AI_TESTS"
_SMOKE_QUESTION = "show the portfolio summary"
_EXPECTED_TOOL = RiskToolName.GET_PORTFOLIO_SUMMARY
_HEAVY_SIDE_EFFECT_TOOLS = frozenset(
    {
        RiskToolName.RUN_PORTFOLIO_RISK,
        RiskToolName.RUN_STRESS,
    }
)


def _live_ai_enabled() -> bool:
    run_flag = os.environ.get(_LIVE_RUN_FLAG, "").strip()
    return get_openai_api_key() is not None and run_flag == "1"


def _skip_reason() -> str:
    missing: list[str] = []
    if get_openai_api_key() is None:
        missing.append("OPENAI_API_KEY")
    if os.environ.get(_LIVE_RUN_FLAG, "").strip() != "1":
        missing.append(f"{_LIVE_RUN_FLAG}=1")
    return "Live AI smoke tests require " + " and ".join(missing) + "."


@pytest.fixture(scope="module")
def live_resources() -> RiskAssistantResources:
    if not _live_ai_enabled():
        pytest.skip(_skip_reason())

    model_name = os.environ.get("OPENAI_MODEL", "").strip()
    if not model_name:
        pytest.skip("OPENAI_MODEL is required for live AI smoke tests.")

    settings = get_ai_settings(provider="openai", openai_model=model_name)
    resources = build_risk_assistant_resources(settings=settings)
    assert resources.model is not None
    yield resources
    resources.close()


def test_live_openai_routes_supported_question_to_allowlisted_tool(
    live_resources: RiskAssistantResources,
) -> None:
    """One cheap routing call; tool selection only — no RiskRun submission."""
    model = live_resources.model
    assert model is not None

    response = model.complete(
        RiskAssistantModelRequest(
            question=_SMOKE_QUESTION,
            tools=tool_contract_schemas(),
            portfolio_id="rates-macro",
        )
    )

    assert response.tool_name is not None, (
        "Expected one allowlisted tool; got clarification/refusal instead."
    )
    assert response.tool_name in {name.value for name in TOOL_CONTRACTS}
    assert response.tool_name not in {name.value for name in _HEAVY_SIDE_EFFECT_TOOLS}
    assert response.tool_name == _EXPECTED_TOOL.value
