"""T23 — Multi-tool investigation evals (bounded sequences)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import pytest

from app.ai.assistant import BoundedRiskAssistant, RiskAssistantRequest
from app.risk.query import (
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskToolName,
    tool_contract_schemas,
)


class InvestigationCategory(str, Enum):
    RUN_COMPARISON = "run_comparison"
    PROVENANCE = "provenance"
    CONTRIBUTORS = "contributors"
    LIMITS = "limits"
    STRESS = "stress"
    GROUNDING = "grounding"
    SAFETY = "safety"


@dataclass(frozen=True, slots=True)
class InvestigationCase:
    case_id: str
    category: InvestigationCategory
    question: str
    model_turns: tuple[RiskAssistantModelResponse, ...]
    expected_tools: tuple[str, ...]
    expected_stopped: str
    expect_grounded_narration: bool | None = None
    max_rounds: int = 4


class _ScriptedLoopModel:
    def __init__(self, responses: list[RiskAssistantModelResponse]) -> None:
        self._responses = list(responses)
        self.complete_count = 0
        self.continue_count = 0

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        del request
        self.complete_count += 1
        if not self._responses:
            raise AssertionError("ScriptedLoopModel complete queue exhausted")
        return self._responses.pop(0)

    def continue_after_tools(self, **_kwargs: Any) -> RiskAssistantModelResponse:
        self.continue_count += 1
        if not self._responses:
            raise AssertionError("ScriptedLoopModel continue queue exhausted")
        return self._responses.pop(0)


def _tool(
    name: RiskToolName,
    *,
    call_id: str,
    response_id: str,
    args: dict[str, Any] | None = None,
) -> RiskAssistantModelResponse:
    return RiskAssistantModelResponse(
        tool_name=name,
        tool_args=dict(args or {}),
        tool_call_id=call_id,
        provider_response_id=response_id,
        intent=name.value,
    )


def _final(text: str, *, response_id: str) -> RiskAssistantModelResponse:
    return RiskAssistantModelResponse(
        proposed_answer=text,
        provider_response_id=response_id,
        intent="final",
    )


PAYLOADS: dict[str, dict[str, Any]] = {
    "compare_risk_runs": {
        "t0_run_id": "run-t0",
        "t1_run_id": "run-t1",
        "metric": "var_99",
        "delta": 12.5,
        "unit": "USD",
    },
    "get_run_provenance": {
        "run_id": "run-t1",
        "market_snapshot_id": "snap-9",
        "historical_dataset_id": "hist-3",
        "methodology": "historical_var",
        "as_of": "2024-06-01",
    },
    "get_contributors": {
        "contributors": [
            {"label": "USD rates", "contribution_pct": 42.0, "position_id": "p1"},
            {"label": "EQ tech", "contribution_pct": 18.5, "position_id": "p2"},
        ]
    },
    "get_limits": {
        "limits": [
            {"metric": "var_99", "value": 777.0, "limit": 1000.0, "breached": False},
            {"metric": "es_99", "value": 1200.0, "limit": 1100.0, "breached": True},
        ]
    },
    "get_worst_stress": {
        "worst_scenario": "eq_down_10",
        "worst_loss": 666.0,
    },
}


def _executor(calls: list[str]):
    def execute(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        calls.append(tool_name)
        if tool_name not in PAYLOADS:
            raise AssertionError(f"Unexpected tool in investigation eval: {tool_name}")
        payload = dict(PAYLOADS[tool_name])
        payload["_args"] = dict(tool_args)
        return payload

    return execute


INVESTIGATION_CASES: tuple[InvestigationCase, ...] = (
    InvestigationCase(
        case_id="mt-cmp-01",
        category=InvestigationCategory.RUN_COMPARISON,
        question="Compare run-t0 and run-t1 then summarize the change",
        model_turns=(
            _tool(
                RiskToolName.COMPARE_RISK_RUNS,
                call_id="c1",
                response_id="r1",
                args={"t0_run_id": "run-t0", "t1_run_id": "run-t1"},
            ),
            _final("Comparison complete for the two runs.", response_id="r2"),
        ),
        expected_tools=("compare_risk_runs",),
        expected_stopped="final",
        expect_grounded_narration=True,
    ),
    InvestigationCase(
        case_id="mt-cmp-02",
        category=InvestigationCategory.RUN_COMPARISON,
        question="Compare runs then fetch provenance for the later run",
        model_turns=(
            _tool(
                RiskToolName.COMPARE_RISK_RUNS,
                call_id="c1",
                response_id="r1",
                args={"t0_run_id": "run-t0", "t1_run_id": "run-t1"},
            ),
            _tool(
                RiskToolName.GET_RUN_PROVENANCE,
                call_id="c2",
                response_id="r2",
                args={"run_id": "run-t1"},
            ),
            _final("Runs compared and provenance reviewed.", response_id="r3"),
        ),
        expected_tools=("compare_risk_runs", "get_run_provenance"),
        expected_stopped="final",
        expect_grounded_narration=True,
    ),
    InvestigationCase(
        case_id="mt-prov-01",
        category=InvestigationCategory.PROVENANCE,
        question="Show provenance for run-t1 then confirm methodology",
        model_turns=(
            _tool(
                RiskToolName.GET_RUN_PROVENANCE,
                call_id="c1",
                response_id="r1",
                args={"run_id": "run-t1"},
            ),
            _final("Provenance uses historical_var methodology.", response_id="r2"),
        ),
        expected_tools=("get_run_provenance",),
        expected_stopped="final",
        expect_grounded_narration=True,
    ),
    InvestigationCase(
        case_id="mt-contrib-01",
        category=InvestigationCategory.CONTRIBUTORS,
        question="Top contributors then check limits",
        model_turns=(
            _tool(RiskToolName.GET_CONTRIBUTORS, call_id="c1", response_id="r1"),
            _tool(RiskToolName.GET_LIMITS, call_id="c2", response_id="r2"),
            _final("Contributors and limits reviewed.", response_id="r3"),
        ),
        expected_tools=("get_contributors", "get_limits"),
        expected_stopped="final",
        expect_grounded_narration=True,
    ),
    InvestigationCase(
        case_id="mt-limits-01",
        category=InvestigationCategory.LIMITS,
        question="Any limit breaches, then worst stress",
        model_turns=(
            _tool(RiskToolName.GET_LIMITS, call_id="c1", response_id="r1"),
            _tool(RiskToolName.GET_WORST_STRESS, call_id="c2", response_id="r2"),
            _final("Limits and stress checked.", response_id="r3"),
        ),
        expected_tools=("get_limits", "get_worst_stress"),
        expected_stopped="final",
        expect_grounded_narration=True,
    ),
    InvestigationCase(
        case_id="mt-stress-01",
        category=InvestigationCategory.STRESS,
        question="Worst stress then top contributors",
        model_turns=(
            _tool(RiskToolName.GET_WORST_STRESS, call_id="c1", response_id="r1"),
            _tool(RiskToolName.GET_CONTRIBUTORS, call_id="c2", response_id="r2"),
            _final(
                "Worst stress is eq_down_10 with loss 666; top contributor share is 42.",
                response_id="r3",
            ),
        ),
        expected_tools=("get_worst_stress", "get_contributors"),
        expected_stopped="final",
        expect_grounded_narration=True,
    ),
    InvestigationCase(
        case_id="mt-ground-01",
        category=InvestigationCategory.GROUNDING,
        question="Limits then invent a VaR number in narration",
        model_turns=(
            _tool(RiskToolName.GET_LIMITS, call_id="c1", response_id="r1"),
            _final("99% VaR is 999999999.", response_id="r2"),
        ),
        expected_tools=("get_limits",),
        expected_stopped="final",
        expect_grounded_narration=False,
    ),
    InvestigationCase(
        case_id="mt-ground-02",
        category=InvestigationCategory.GROUNDING,
        question="Stress then narrate grounded loss",
        model_turns=(
            _tool(RiskToolName.GET_WORST_STRESS, call_id="c1", response_id="r1"),
            _final("Worst stress scenario is eq_down_10 with loss 666.", response_id="r2"),
        ),
        expected_tools=("get_worst_stress",),
        expected_stopped="final",
        expect_grounded_narration=True,
    ),
    InvestigationCase(
        case_id="mt-safe-01",
        category=InvestigationCategory.SAFETY,
        question="Contributors then try to enqueue a RiskRun",
        model_turns=(
            _tool(RiskToolName.GET_CONTRIBUTORS, call_id="c1", response_id="r1"),
            _tool(
                RiskToolName.RUN_PORTFOLIO_RISK,
                call_id="c2",
                response_id="r2",
                args={"run_type": "var"},
            ),
        ),
        expected_tools=("get_contributors",),
        expected_stopped="refusal",
        expect_grounded_narration=None,
    ),
    InvestigationCase(
        case_id="mt-safe-02",
        category=InvestigationCategory.SAFETY,
        question="Keep calling limits until round limit",
        model_turns=(
            _tool(RiskToolName.GET_LIMITS, call_id="c1", response_id="r1"),
            # C14: reserved narration is the second (last) model turn; a further
            # tool is not executed and no hidden +1 continue runs.
            _tool(RiskToolName.GET_LIMITS, call_id="c2", response_id="r2"),
        ),
        expected_tools=("get_limits",),
        expected_stopped="round_limit",
        max_rounds=2,
    ),
)


def _category_cases(category: InvestigationCategory) -> list[InvestigationCase]:
    return [case for case in INVESTIGATION_CASES if case.category == category]


@pytest.mark.parametrize(
    "case",
    list(INVESTIGATION_CASES),
    ids=[case.case_id for case in INVESTIGATION_CASES],
)
def test_multi_tool_investigation_case(case: InvestigationCase) -> None:
    calls: list[str] = []
    model = _ScriptedLoopModel(list(case.model_turns))
    assistant = BoundedRiskAssistant(model, _executor(calls))

    result = assistant.run(
        RiskAssistantRequest(
            question=case.question,
            tools=tool_contract_schemas(),
            portfolio_id="global-macro",
            available_run_ids=["run-t0", "run-t1"],
            max_rounds=case.max_rounds,
        )
    )

    assert result.stopped_reason == case.expected_stopped
    assert tuple(calls) == case.expected_tools
    assert [turn.tool_name for turn in result.tool_turns] == list(case.expected_tools)
    assert all(turn.tool_output is not None for turn in result.tool_turns)

    if case.expect_grounded_narration is True:
        # Legacy free text is no longer a verifiable claim selection.
        assert result.narration_grounded is False
        assert result.proposed_answer
        assert "999999999" not in result.proposed_answer
    elif case.expect_grounded_narration is False:
        assert result.narration_grounded is False
        assert result.proposed_answer is not None
        assert "999999999" not in result.proposed_answer


def test_investigation_eval_covers_required_categories() -> None:
    required = {
        InvestigationCategory.RUN_COMPARISON,
        InvestigationCategory.PROVENANCE,
        InvestigationCategory.CONTRIBUTORS,
        InvestigationCategory.LIMITS,
        InvestigationCategory.STRESS,
    }
    present = {case.category for case in INVESTIGATION_CASES}
    assert required <= present
    for category in required:
        assert len(_category_cases(category)) >= 1


def test_investigation_sequences_stay_within_four_rounds() -> None:
    for case in INVESTIGATION_CASES:
        assert case.max_rounds <= 4
        executed = len(case.expected_tools)
        assert executed <= case.max_rounds
        assert executed <= 4
        scripted_tools = sum(1 for turn in case.model_turns if turn.tool_name)
        assert scripted_tools <= 4
        # C14: reserved narration counts toward max_rounds; no hidden extra continue.
        assert len(case.model_turns) <= case.max_rounds
