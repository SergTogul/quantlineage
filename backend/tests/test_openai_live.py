"""T14 / C12 — Opt-in live OpenAI conversational smoke test.

Skipped unless both ``OPENAI_API_KEY`` and ``RUN_LIVE_AI_TESTS=1`` are set.
Normal CI never sets the run flag, so this file is network-free in default pipelines.

When enabled, the smoke proves tool selection → ``function_call_output`` →
final narration (not one-shot routing).
"""

from __future__ import annotations

import os

import pytest

from app.ai.assistant import BoundedRiskAssistant, RiskAssistantRequest
from app.ai.config import get_ai_settings, get_openai_api_key
from app.ai.factory import RiskAssistantResources, build_risk_assistant_resources
from app.risk.query import (
    TOOL_CONTRACTS,
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
    "market_value": 125000.0,
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
    executed = []
    def execute(name, args):
        assert name == _EXPECTED_TOOL.value
        assert name in {name.value for name in TOOL_CONTRACTS}
        assert name not in {name.value for name in _HEAVY_SIDE_EFFECT_TOOLS}
        executed.append(name)
        return _CANNED_TOOL_OUTPUT

    result = BoundedRiskAssistant(model, execute).run(RiskAssistantRequest(
        question=_SMOKE_QUESTION, tools=tool_contract_schemas(),
        portfolio_id="rates-macro", max_rounds=2, max_tool_calls=1,
        timeout_seconds=live_resources.settings.timeout_seconds,
    ))
    assert executed == [_EXPECTED_TOOL.value]
    assert result.rounds_used == 2
    assert result.narration_grounded is True
    assert result.proposed_answer
    assert "125000" in result.proposed_answer
