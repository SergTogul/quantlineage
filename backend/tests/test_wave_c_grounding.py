"""Wave C G4 — grounded explanation cards copied from tool payloads only."""

from __future__ import annotations

from tests.test_ai_query_orchestration import (
    _FixturePayload,
    _FixtureService,
    _ScriptedModel,
)

from app.risk.query import (
    RiskAssistantModelResponse,
    RiskQueryEngine,
    RiskToolName,
)
from app.sample import SAMPLE_PORTFOLIO

MISSING = "not on this payload"

_FULL_CHANGE = {
    "t0_run_id": "run-t0",
    "t1_run_id": "run-t1",
    "metric": "var_99",
    "unit": "currency loss",
    "sign_convention": "positive total_change means more loss-risk",
    "previous_risk": 100.0,
    "current_risk": 140.0,
    "total_change": 40.0,
    "portfolio_trade_change": 22.0,
    "market_change": 11.0,
    "explained_change": 33.0,
    "residual": 9.0,
    "residual_name": "residual / interactions",
    "disclosed_changes": ["calculation_config"],
    "identity": {
        "changed_fields": ["calculation_config"],
        "t0": {
            "run_id": "run-t0",
            "as_of": "2024-01-02",
            "methodology": "DELTA_GAMMA",
            "market_snapshot_id": "snap-t0",
            "historical_dataset_id": "hist-ds",
            "historical_dataset_version": "v1",
        },
        "t1": {
            "run_id": "run-t1",
            "as_of": "2024-01-03",
            "methodology": "DELTA_GAMMA",
            "market_snapshot_id": "snap-t1",
            "historical_dataset_id": "hist-ds",
            "historical_dataset_version": "v1",
        },
    },
    "factor_contributors": [
        {
            "factor_id": "EquitySpot:SPY",
            "factor": "SPY",
            "delta_risk": 11.0,
        }
    ],
    "hierarchy_contributors": [
        {"level": "trade", "name": "EQ1", "path": "EQ1", "delta_risk": 22.0}
    ],
}


class _IdentityVarService(_FixtureService):
    def var_report(self, portfolio):
        self.calls.append("var_report")
        return _FixturePayload(
            {
                "portfolio_id": portfolio.id,
                "metric": "var_99",
                "value": 444.0,
                "unit": "USD",
                "sign_convention": "loss",
                "risk_run_id": "run-grounded",
                "as_of": "2024-06-15",
                "methodology": "DELTA_GAMMA",
                "market_snapshot_id": "snap-grounded",
                "historical_dataset_id": "hist-grounded",
                "historical_dataset_version": "v9",
                "methods": [
                    {"method": "historical", "confidence": 0.99, "var": 444.0},
                    {"method": "parametric", "confidence": 0.99, "var": 555.0},
                ],
                "contributions": [],
            }
        )


class _ExplainService(_FixtureService):
    def __init__(self, payload: dict) -> None:
        super().__init__()
        self.payload = payload

    def explain_risk_change(self, t0_run_id: str, t1_run_id: str, metric: str = "var_99"):
        self.calls.append("explain_risk_change")
        return _FixturePayload({**self.payload, "t0_run_id": t0_run_id, "t1_run_id": t1_run_id, "metric": metric})

    def compare_runs(self, t0_run_id: str, t1_run_id: str, metric: str = "var_99", principal=None):
        self.calls.append("compare_runs")
        return _FixturePayload({**self.payload, "t0_run_id": t0_run_id, "t1_run_id": t1_run_id, "metric": metric})


class _RiskRunService(_FixtureService):
    def get(self, run_id: str, *, principal=None):
        self.calls.append("get")
        return {
            "id": run_id,
            "status": "COMPLETED",
            "run_type": "var",
            "market_snapshot_id": "snap-run",
            "historical_dataset_id": "hist-run",
            "historical_dataset_version": "v2",
            "as_of": "2024-02-01",
            "methodology": "HISTORICAL",
            "results": [
                {
                    "result_type": "var",
                    "payload": {
                        "metric": "var_99",
                        "value": 444.0,
                        "unit": "USD",
                        "sign_convention": "loss",
                    },
                }
            ],
        }


def _answer_explain(
    service,
    t0="run-t0",
    t1="run-t1",
    tool_name: RiskToolName = RiskToolName.EXPLAIN_RISK_CHANGE,
):
    engine = RiskQueryEngine()
    intent = (
        "run_comparison"
        if tool_name == RiskToolName.COMPARE_RISK_RUNS
        else "explain_risk_change"
    )
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            tool_name=tool_name,
            tool_args={"t0_run_id": t0, "t1_run_id": t1, "metric": "var_99"},
            intent=intent,
        )
    )
    return engine.answer_with_model(
        "Why did VaR increase?", SAMPLE_PORTFOLIO, service, model
    )


def _assert_copied(container: dict, payload: dict, *keys: str) -> None:
    for key in keys:
        assert key in container, f"expected {key} on grounded card"
        assert container[key] == payload[key]


def test_c4_numeric_answers_copy_metric_value_unit_sign_run_asof_methodology_dataset() -> None:
    engine = RiskQueryEngine()
    service = _IdentityVarService()
    response = engine.answer(
        "What is 99% VaR and expected shortfall?", SAMPLE_PORTFOLIO, service
    )
    payload = response.data["tool_result"]
    card = response.data["card"]
    provenance = response.data["provenance"]
    _assert_copied(
        card,
        payload,
        "metric",
        "value",
        "unit",
        "sign_convention",
        "risk_run_id",
        "as_of",
        "methodology",
        "market_snapshot_id",
        "historical_dataset_id",
        "historical_dataset_version",
    )
    _assert_copied(
        provenance,
        payload,
        "risk_run_id",
        "as_of",
        "methodology",
        "market_snapshot_id",
        "historical_dataset_id",
        "historical_dataset_version",
        "unit",
        "sign_convention",
    )
    answer = response.answer
    assert "444" in answer
    assert "555" in answer
    assert "var_99" in answer
    assert "USD" in answer
    assert "loss" in answer
    assert "run-grounded" in answer
    assert "2024-06-15" in answer
    assert "DELTA_GAMMA" in answer
    assert "snap-grounded" in answer
    assert "hist-grounded" in answer
    assert "v9" in answer


def test_c4_missing_identity_fields_are_not_invented() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    response = engine.answer(
        "What is 99% VaR and expected shortfall?", SAMPLE_PORTFOLIO, service
    )
    payload = response.data["tool_result"]
    card = response.data["card"]
    provenance = response.data["provenance"]
    for blob in (card, provenance):
        for key in (
            "risk_run_id",
            "as_of",
            "unit",
            "sign_convention",
            "market_snapshot_id",
            "historical_dataset_id",
        ):
            if key in blob:
                assert blob[key] == MISSING
            assert blob.get(key) not in {"run-invented", "2026-09-13", "USD"}
    assert "risk_run_id" not in payload
    assert "as_of" not in payload
    assert "444" in response.answer
    assert "555" in response.answer
    lowered = response.answer.lower()
    assert "not on this payload" in lowered
    assert "run-invented" not in response.answer
    assert "2026-09-13" not in response.answer


def test_c4_explain_risk_change_lists_waterfall_from_fixture_only() -> None:
    service = _ExplainService(_FULL_CHANGE)
    response = _answer_explain(service)
    payload = response.data["tool_result"]
    card = response.data["card"]
    answer = response.answer.lower()
    # C1 maps explain_risk_change and compare_risk_runs onto compare_runs.
    assert service.calls == ["compare_runs"]
    _assert_copied(
        card,
        payload,
        "t0_run_id",
        "t1_run_id",
        "metric",
        "unit",
        "sign_convention",
        "total_change",
        "portfolio_trade_change",
        "market_change",
        "residual",
        "disclosed_changes",
        "identity",
        "factor_contributors",
        "hierarchy_contributors",
    )
    assert "run-t0" in response.answer
    assert "run-t1" in response.answer
    assert "40" in response.answer
    assert "22" in response.answer
    assert "11" in response.answer
    assert "9" in response.answer
    assert "spy" in answer
    assert "calculation_config" in answer
    assert "currency loss" in answer
    # Stored residual is 9, not total-explained (7) or total-trade-market (7).
    assert " 7" not in f" {response.answer} "
    assert card["residual"] == 9.0

    compare = _answer_explain(service, tool_name=RiskToolName.COMPARE_RISK_RUNS)
    assert service.calls == ["compare_runs", "compare_runs"]
    assert compare.data["card"]["residual"] == 9.0
    assert "40" in compare.answer
    assert " 7" not in f" {compare.answer} "


def test_c4_missing_residual_and_unit_are_not_estimated() -> None:
    payload = {
        "t0_run_id": "run-t0",
        "t1_run_id": "run-t1",
        "metric": "var_99",
        "previous_risk": 100.0,
        "current_risk": 140.0,
        "total_change": 40.0,
        "explained_change": 12.0,
    }
    service = _ExplainService(payload)
    response = _answer_explain(service)
    card = response.data["card"]
    assert card.get("residual") in {None, MISSING} or "residual" not in card
    assert card.get("unit") in {None, MISSING} or "unit" not in card
    assert "28" not in response.answer
    assert "USD" not in response.answer
    assert "currency" not in response.answer.lower()
    lowered = response.answer.lower()
    assert "residual" in lowered
    assert "not on this payload" in lowered
    assert "40" in response.answer


def test_c4_get_risk_run_card_copies_run_identity() -> None:
    engine = RiskQueryEngine()
    service = _RiskRunService()
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_RISK_RUN,
            tool_args={"run_id": "run-abc"},
            intent="risk_run",
        )
    )
    response = engine.answer_with_model(
        "show risk run run-abc", SAMPLE_PORTFOLIO, service, model
    )
    payload = response.data["tool_result"]
    card = response.data["card"]
    provenance = response.data["provenance"]
    assert payload["id"] == "run-abc"
    assert card.get("risk_run_id") == "run-abc" or card.get("id") == "run-abc"
    assert provenance.get("risk_run_id") == "run-abc" or provenance.get("id") == "run-abc"
    assert "2024-02-01" in response.answer
    assert "HISTORICAL" in response.answer
    assert "snap-run" in response.answer
    assert "hist-run" in response.answer
    assert "444" in response.answer
    assert "USD" in response.answer


def test_c4_ungrounded_paths_remain_digit_free() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    response = engine.answer("Should we buy more NVDA tomorrow?", SAMPLE_PORTFOLIO, service)
    assert service.calls == []
    assert "card" not in response.data
    assert not any(ch.isdigit() for ch in response.answer)
