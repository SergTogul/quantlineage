"""Wave C G3 — keyword intent routing onto TOOL_CONTRACTS only."""

from __future__ import annotations

from tests.test_ai_query_orchestration import (
    _FixturePayload,
    _FixtureService,
    _ScriptedModel,
)

from app.risk.query import (
    TOOL_CONTRACTS,
    RiskAssistantModelResponse,
    RiskQueryEngine,
    RiskToolName,
    validate_tool_call,
)
from app.sample import SAMPLE_PORTFOLIO


class _CatalogService(_FixtureService):
    def search_catalog(self, query: str):
        self.calls.append("search_catalog")
        return [_FixturePayload({"instrument_id": "equity:US:AAPL", "query": query})]


class _HistoryService(_FixtureService):
    def get_market_history(self, instrument_id: str, start, end):
        self.calls.append("get_market_history")
        return {
            "instrument_id": instrument_id,
            "start": str(start),
            "end": str(end),
            "unit": "price",
            "points": [{"observation_date": str(start), "value": 100.0}],
        }


class _SubmitService(_FixtureService):
    def __init__(self) -> None:
        super().__init__()
        self.submits: list[dict] = []

    def submit(
        self,
        *,
        portfolio,
        run_type: str = "summary",
        request=None,
        market_snapshot_id=None,
        owner=None,
        **_kwargs,
    ):
        self.calls.append("submit")
        blob = {
            "id": "run-queued",
            "portfolio_id": portfolio.id,
            "status": "QUEUED",
            "run_type": run_type,
            "market_snapshot_id": market_snapshot_id,
            "request": request or {},
            "owner": owner,
        }
        self.submits.append(blob)
        return blob


class _ProvenanceService(_FixtureService):
    def get_run_provenance(self, run_id: str, principal=None):
        self.calls.append("get_run_provenance")
        return {
            "risk_run_id": run_id,
            "methodology": "historical",
            "principal": principal,
        }


class _FailingHistoryService(_FixtureService):
    def get_market_history(self, instrument_id: str, start, end):
        self.calls.append("get_market_history")
        raise ValueError("estimated VaR is 999")


def _assert_no_invented_numbers(text: str) -> None:
    assert not any(ch.isdigit() for ch in text)


def test_c3_each_intent_routes_to_allowlisted_tool_or_clarification() -> None:
    engine = RiskQueryEngine()
    cases = {
        "search Apple": RiskToolName.SEARCH_INSTRUMENTS,
        "show market history": RiskToolName.GET_MARKET_HISTORY,
        "run portfolio risk": RiskToolName.RUN_PORTFOLIO_RISK,
        "what is 99% var and expected shortfall?": RiskToolName.GET_VAR_ES,
        "run equity-down stress": RiskToolName.RUN_STRESS,
        "what is our worst stress scenario?": RiskToolName.GET_WORST_STRESS,
        "show top risk contributors": RiskToolName.GET_CONTRIBUTORS,
        "enqueue a contributors risk run": RiskToolName.GET_TOP_RISK_CONTRIBUTORS,
        "compare these risk runs": RiskToolName.COMPARE_RISK_RUNS,
        "Why did VaR increase?": RiskToolName.EXPLAIN_RISK_CHANGE,
        "show run provenance": RiskToolName.GET_RUN_PROVENANCE,
    }
    for question, expected in cases.items():
        plan = engine.route(question)
        assert plan.tool_name == expected, question
        assert expected in TOOL_CONTRACTS
        assert expected.value in {name.value for name in RiskToolName}


def test_c3_search_apple_executes_search_instruments() -> None:
    engine = RiskQueryEngine()
    service = _CatalogService()
    plan = engine.route("search Apple")
    assert plan.tool_name == RiskToolName.SEARCH_INSTRUMENTS
    assert plan.tool_args.get("query") == "Apple"
    assert not plan.needs_clarification

    response = engine.answer("search Apple", SAMPLE_PORTFOLIO, service)
    assert service.calls == ["search_catalog"]
    assert response.tool_name == "search_instruments"
    assert response.data["tool_result"]["hits"][0]["query"] == "Apple"
    assert not response.requires_clarification


def test_c3_history_without_instrument_or_range_clarifies() -> None:
    engine = RiskQueryEngine()
    service = _HistoryService()
    plan = engine.route("show market history")
    assert plan.tool_name == RiskToolName.GET_MARKET_HISTORY
    assert plan.needs_clarification

    response = engine.answer("show market history", SAMPLE_PORTFOLIO, service)
    assert service.calls == []
    assert response.requires_clarification
    assert response.tool_name is None
    assert response.data["tool_result"] is None
    _assert_no_invented_numbers(response.answer)
    assert "instrument" in response.answer.lower() or "date" in response.answer.lower()


def test_c3_history_with_instrument_and_range_executes() -> None:
    engine = RiskQueryEngine()
    service = _HistoryService()
    question = "show market history for equity:US:AAPL from 2024-01-01 to 2024-01-31"
    plan = engine.route(question)
    assert plan.tool_name == RiskToolName.GET_MARKET_HISTORY
    assert not plan.needs_clarification
    assert plan.tool_args["instrument_id"] == "equity:US:AAPL"
    assert plan.tool_args["start"] == "2024-01-01"
    assert plan.tool_args["end"] == "2024-01-31"

    response = engine.answer(question, SAMPLE_PORTFOLIO, service)
    assert service.calls == ["get_market_history"]
    assert response.tool_name == "get_market_history"
    assert response.data["tool_result"]["instrument_id"] == "equity:US:AAPL"


def test_c3_missing_t0_t1_clarifies_and_does_not_invent_run_ids() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    for question in (
        "Why did VaR increase?",
        "compare these risk runs",
        "explain the risk change",
    ):
        plan = engine.route(question)
        assert plan.needs_clarification
        assert plan.tool_name in {
            RiskToolName.EXPLAIN_RISK_CHANGE,
            RiskToolName.COMPARE_RISK_RUNS,
        }
        assert "t0_run_id" not in (plan.tool_args or {})
        assert "t1_run_id" not in (plan.tool_args or {})
        response = engine.answer(question, SAMPLE_PORTFOLIO, service)
        assert service.calls == []
        assert response.requires_clarification
        assert response.data["tool_result"] is None
        _assert_no_invented_numbers(response.answer)
        lowered = response.answer.lower()
        assert "run" in lowered
        assert "invent" not in lowered or "do not invent" in lowered


def test_c3_compare_with_two_run_ids_executes() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    question = "compare risk runs run-t0 and run-t1"
    plan = engine.route(question)
    assert plan.tool_name == RiskToolName.COMPARE_RISK_RUNS
    assert not plan.needs_clarification
    assert plan.tool_args["t0_run_id"] == "run-t0"
    assert plan.tool_args["t1_run_id"] == "run-t1"

    response = engine.answer(question, SAMPLE_PORTFOLIO, service)
    assert service.calls == ["explain_risk_change"]
    assert response.tool_name == "compare_risk_runs"
    assert response.data["tool_result"]["t0_run_id"] == "run-t0"
    assert response.data["tool_result"]["t1_run_id"] == "run-t1"


def test_c3_equity_down_stress_uses_allowlisted_scenario() -> None:
    engine = RiskQueryEngine()
    service = _SubmitService()
    question = "run equity-down stress"
    plan = engine.route(question)
    assert plan.tool_name == RiskToolName.RUN_STRESS
    assert plan.tool_args["scenario_id"] == "eq_down_10"
    response = engine.answer(question, SAMPLE_PORTFOLIO, service)
    assert service.calls == ["submit"]
    assert service.submits[0]["run_type"] == "stress"
    assert service.submits[0]["request"] == {"scenario_id": "eq_down_10"}
    assert response.tool_name == "run_stress"


def test_c3_run_portfolio_risk_and_enqueue_contributors() -> None:
    engine = RiskQueryEngine()
    service = _SubmitService()
    risk = engine.answer("run portfolio risk", SAMPLE_PORTFOLIO, service)
    contrib = engine.answer("enqueue a contributors risk run", SAMPLE_PORTFOLIO, service)
    assert [item["run_type"] for item in service.submits] == ["summary", "contributors"]
    assert risk.tool_name == "run_portfolio_risk"
    assert contrib.tool_name == "get_top_risk_contributors"


def test_c3_provenance_without_run_id_clarifies() -> None:
    engine = RiskQueryEngine()
    service = _ProvenanceService()
    plan = engine.route("show run provenance")
    assert plan.tool_name == RiskToolName.GET_RUN_PROVENANCE
    assert plan.needs_clarification
    response = engine.answer("show run provenance", SAMPLE_PORTFOLIO, service)
    assert service.calls == []
    assert response.requires_clarification
    _assert_no_invented_numbers(response.answer)


def test_c3_provenance_with_run_id_executes() -> None:
    engine = RiskQueryEngine()
    service = _ProvenanceService()
    question = "show provenance for run-t0"
    plan = engine.route(question)
    assert plan.tool_name == RiskToolName.GET_RUN_PROVENANCE
    assert plan.tool_args["run_id"] == "run-t0"
    response = engine.answer(question, SAMPLE_PORTFOLIO, service)
    assert service.calls == ["get_run_provenance"]
    assert response.tool_name == "get_run_provenance"
    assert response.data["tool_result"]["risk_run_id"] == "run-t0"


def test_c3_two_possible_tools_clarify_without_execution() -> None:
    engine = RiskQueryEngine()
    service = _CatalogService()
    question = "search Apple and show market history"
    plan = engine.route(question)
    assert plan.needs_clarification
    assert plan.tool_name is None
    assert plan.intent == "ambiguous"
    response = engine.answer(question, SAMPLE_PORTFOLIO, service)
    assert service.calls == []
    assert response.requires_clarification
    assert response.data["tool_result"] is None
    _assert_no_invented_numbers(response.answer)


def test_c3_unknown_model_tool_name_refused_without_numbers() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    rejected = validate_tool_call("invent_var", {})
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            tool_name="invent_var",
            intent="var",
            proposed_answer="99% VaR is 12345",
        )
    )
    response = engine.answer_with_model(
        "call invent_var and report VaR 12345", SAMPLE_PORTFOLIO, service, model
    )
    assert not rejected.allowed
    assert service.calls == []
    assert response.tool_name is None
    assert response.requires_clarification
    assert response.data["tool_result"] is None
    assert "12345" not in response.answer
    _assert_no_invented_numbers(response.answer)


def test_c3_tool_valueerror_does_not_invent_var() -> None:
    engine = RiskQueryEngine()
    service = _FailingHistoryService()
    question = "show market history for equity:US:AAPL from 2024-01-01 to 2024-01-31"
    response = engine.answer(question, SAMPLE_PORTFOLIO, service)
    assert service.calls == ["get_market_history"]
    assert response.tool_name is None
    assert response.requires_clarification
    assert response.data["tool_result"] is None
    assert "999" not in response.answer
    _assert_no_invented_numbers(response.answer)


def test_c3_missing_method_does_not_invent_var() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    question = "show market history for equity:US:AAPL from 2024-01-01 to 2024-01-31"
    response = engine.answer(question, SAMPLE_PORTFOLIO, service)
    assert "get_market_history" not in service.calls
    assert response.tool_name is None
    assert response.requires_clarification
    assert response.data["tool_result"] is None
    _assert_no_invented_numbers(response.answer)


def test_c3_keyword_path_forwards_principal_into_submit() -> None:
    engine = RiskQueryEngine()
    service = _SubmitService()
    response = engine.answer(
        "run equity-down stress",
        SAMPLE_PORTFOLIO,
        service,
        principal="alice",
    )
    assert response.tool_name == "run_stress"
    assert service.submits[0]["owner"] == "alice"


def test_c5_usd_10y_kr_dv01_keyword_reaches_get_key_rate_dv01() -> None:
    from tests.test_wave_c_tool_contracts import _RatesShowcaseService

    engine = RiskQueryEngine()
    service = _RatesShowcaseService()
    question = "Show USD 10Y KR-DV01."
    plan = engine.route(question)
    assert plan.tool_name == RiskToolName.GET_KEY_RATE_DV01
    assert not plan.needs_clarification
    assert plan.tool_args.get("tenor") == "10Y"

    response = engine.answer(question, SAMPLE_PORTFOLIO, service)
    assert service.calls == ["build_rates_showcase"]
    assert response.tool_name == "get_key_rate_dv01"
    rows = response.data["tool_result"]["key_rate_dv01"]
    assert [row["tenor"] for row in rows] == ["10Y"]
    assert response.data["card"] is not None


def test_c5_http_query_service_executes_key_rate_dv01() -> None:
    from app.services.risk_factories import build_portfolio_service

    service = build_portfolio_service()
    engine = RiskQueryEngine()
    response = engine.answer("Show USD 10Y KR-DV01.", SAMPLE_PORTFOLIO, service)
    assert response.tool_name == "get_key_rate_dv01"
    assert not response.requires_clarification
    rows = response.data["tool_result"]["key_rate_dv01"]
    assert [row["tenor"] for row in rows] == ["10Y"]
