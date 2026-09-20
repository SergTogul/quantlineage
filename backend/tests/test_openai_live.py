"""T14 / C12 — Opt-in live OpenAI conversational smoke test.

Skipped unless both ``OPENAI_API_KEY`` and ``RUN_LIVE_AI_TESTS=1`` are set.
Normal CI never sets the run flag, so this file is network-free in default pipelines.

When enabled, the smoke proves tool selection → ``function_call_output`` →
final narration (not one-shot routing).
"""

from __future__ import annotations

import json
import os

import pytest

from app.ai.assistant import FunctionCallOutput
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
        RiskToolName.GET_TOP_RISK_CONTRIBUTORS,
    }
)
_CANNED_TOOL_OUTPUT = {
    "tool": "get_portfolio_summary",
    "portfolio_id": "rates-macro",
    "position_count": 3,
    "status": "ok",
}


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

    settings = get_ai_settings(
        provider="openai",
        openai_model=model_name,
        assistant_loop="conversational",
    )
    resources = build_risk_assistant_resources(settings=settings)
    assert resources.model is not None
    yield resources
    resources.close()


def test_live_openai_tool_then_function_output_then_narration(
    live_resources: RiskAssistantResources,
) -> None:
    """Cheap conversational smoke: select → function_call_output → final text.

    Does not submit a RiskRun. Tool JSON is a canned allowlisted payload so the
    live model only narrates; QuantLineage remains the source of numbers.
    """
    model = live_resources.model
    assert model is not None
    continue_after_tools = getattr(model, "continue_after_tools", None)
    assert callable(continue_after_tools), (
        "Live smoke requires continue_after_tools for reserved narration."
    )

    request = RiskAssistantModelRequest(
        question=_SMOKE_QUESTION,
        tools=tool_contract_schemas(),
        portfolio_id="rates-macro",
    )
    selected = model.complete(request)

    assert selected.tool_name is not None, (
        "Expected one allowlisted tool; got clarification/refusal instead."
    )
    assert selected.tool_name in {name.value for name in TOOL_CONTRACTS}
    assert selected.tool_name not in {name.value for name in _HEAVY_SIDE_EFFECT_TOOLS}
    assert selected.tool_name == _EXPECTED_TOOL.value
    assert selected.tool_call_id
    assert selected.provider_response_id
    assert selected.proposed_answer is None

    continued = continue_after_tools(
        previous_response_id=selected.provider_response_id,
        tool_outputs=[
            FunctionCallOutput(
                call_id=selected.tool_call_id,
                output=json.dumps(_CANNED_TOOL_OUTPUT),
            )
        ],
        request=request,
        reserve_narration=True,
    )

    assert continued.tool_name is None
    assert continued.proposed_answer
    assert continued.proposed_answer.strip()
