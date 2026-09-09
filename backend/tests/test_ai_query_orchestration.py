from __future__ import annotations

from dataclasses import dataclass

from app.api.schemas import RiskQueryRequest
from app.domain.models import Portfolio
from app.main import app
from app.risk.query import (
    RiskAssistantModelRequest,
    RiskAssistantModelResponse,
    RiskQueryEngine,
    RiskToolName,
    tool_contract_schemas,
)
from app.sample import SAMPLE_PORTFOLIO


@dataclass
class _FixturePayload:
    values: dict

    def model_dump(self) -> dict:
        return dict(self.values)


class _FixtureService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def summary(self, portfolio: Portfolio) -> _FixturePayload:
        self.calls.append("summary")
        return _FixturePayload(
            {
                "portfolio_id": portfolio.id,
                "market_value": 1234567.89,
                "var_95": 111.0,
                "var_99": 222.0,
                "expected_shortfall_99": 333.0,
            }
        )

    def var_report(self, portfolio: Portfolio) -> _FixturePayload:
        self.calls.append("var_report")
        return _FixturePayload(
            {
                "portfolio_id": portfolio.id,
                "methods": [
                    {"method": "historical", "confidence": 0.99, "var": 444.0},
                    {"method": "parametric", "confidence": 0.99, "var": 555.0},
                ],
                "contributions": [],
            }
        )

    def threat_evaluation(self, portfolio: Portfolio) -> _FixturePayload:
        self.calls.append("threat_evaluation")
        return _FixturePayload(
            {
                "portfolio_id": portfolio.id,
                "worst_scenario": "fixture stress",
                "worst_loss": 666.0,
                "evaluations": [
                    {"scenario": "fixture stress", "loss": 666.0, "threat_level": "SEVERE"}
                ],
            }
        )

    def limits(self, portfolio: Portfolio) -> list[_FixturePayload]:
        self.calls.append("limits")
        return [
            _FixturePayload(
                {
                    "metric": "var_99",
                    "value": 777.0,
                    "limit": 700.0,
                    "utilization_pct": 111.0,
                    "breached": True,
                    "status": "BREACH",
                }
            )
        ]

    def contributors(self, portfolio: Portfolio) -> list[_FixturePayload]:
        self.calls.append("contributors")
        return [
            _FixturePayload(
                {
                    "position_id": "fixture-position",
                    "label": "Fixture position",
                    "risk_amount": 888.0,
                    "contribution_pct": 42.0,
                }
            )
        ]


class _ScriptedModel:
    def __init__(self, response: RiskAssistantModelResponse) -> None:
        self.response = response
        self.requests: list[RiskAssistantModelRequest] = []

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        self.requests.append(request)
        return self.response


def test_m11_tool_contracts_cover_core_questions() -> None:
    contracts = {item["name"]: item for item in tool_contract_schemas()}

    assert set(contracts) == {tool.value for tool in RiskToolName}
    assert contracts["get_portfolio_summary"]["service_method"] == "summary"
    assert contracts["get_var_es"]["service_method"] == "var_report"
    assert contracts["get_worst_stress"]["service_method"] == "threat_evaluation"
    assert contracts["get_limits"]["service_method"] == "limits"
    assert contracts["get_contributors"]["service_method"] == "contributors"
    assert all("deterministic" in item["numeric_source"] for item in contracts.values())


def test_m11_router_selects_supported_tools_deterministically() -> None:
    engine = RiskQueryEngine()

    cases = {
        "show the portfolio summary": RiskToolName.GET_PORTFOLIO_SUMMARY,
        "what is 99% var and expected shortfall?": RiskToolName.GET_VAR_ES,
        "what is our worst stress scenario?": RiskToolName.GET_WORST_STRESS,
        "which limit breaches do we have?": RiskToolName.GET_LIMITS,
        "show top risk contributors": RiskToolName.GET_CONTRIBUTORS,
    }

    for question, expected_tool in cases.items():
        plan = engine.route(question)
        assert plan.tool_name == expected_tool
        assert not plan.needs_clarification


def test_m11_numeric_answers_are_grounded_in_tool_payloads() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()

    response = engine.answer("What is 99% VaR and expected shortfall?", SAMPLE_PORTFOLIO, service)

    assert service.calls == ["var_report"]
    assert response.intent == "var"
    assert response.tool_name == "get_var_es"
    assert response.data["tool_result"]["methods"][0]["var"] == 444.0
    assert "444" in response.answer
    assert "555" in response.answer
    assert "333" not in response.answer


def test_m11_unsupported_question_refuses_without_running_risk_tool() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()

    response = engine.answer("Should we buy more NVDA tomorrow?", SAMPLE_PORTFOLIO, service)

    assert service.calls == []
    assert response.intent == "unsupported"
    assert response.tool_name is None
    assert response.requires_clarification
    assert response.data["tool_result"] is None
    assert "deterministic" in response.answer.lower()


def test_m11_ambiguous_risk_question_asks_for_clarification_without_numbers() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()

    response = engine.answer("What is our risk?", SAMPLE_PORTFOLIO, service)

    assert service.calls == []
    assert response.intent == "ambiguous"
    assert response.requires_clarification
    assert response.data["tool_result"] is None
    assert "VaR/ES" in response.answer


def test_m11_query_endpoint_exposes_tool_contract_metadata() -> None:
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        portfolio = client.get("/api/v1/portfolio").json()
        response = client.post(
            "/api/v1/risk/query",
            json=RiskQueryRequest(
                portfolio=Portfolio.model_validate(portfolio),
                question="show top risk contributors",
            ).model_dump(mode="json"),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "contributors"
    assert body["tool_name"] == "get_contributors"
    assert body["data"]["tool_contract"]["service_method"] == "contributors"
    assert body["data"]["tool_result"]["contributors"]


def test_m11_model_tool_loop_executes_selected_deterministic_tool() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_LIMITS,
            intent="limits",
            rationale="The user asked about breach status.",
        )
    )

    response = engine.answer_with_model(
        "Which limits are breached?", SAMPLE_PORTFOLIO, service, model
    )

    assert service.calls == ["limits"]
    assert len(model.requests) == 1
    assert model.requests[0].question == "Which limits are breached?"
    assert {tool["name"] for tool in model.requests[0].tools} == {
        tool.value for tool in RiskToolName
    }
    assert response.intent == "limits"
    assert response.tool_name == "get_limits"
    assert response.data["tool_result"]["limits"][0]["value"] == 777.0
    assert response.data["model"]["rationale"] == "The user asked about breach status."
    assert "1 limit breaches" in response.answer


def test_m11_model_answer_is_ignored_until_tool_payload_returns() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_VAR_ES,
            intent="var",
            proposed_answer="99% VaR is 999999999.",
        )
    )

    response = engine.answer_with_model(
        "What is 99% VaR?", SAMPLE_PORTFOLIO, service, model
    )

    assert service.calls == ["var_report"]
    assert "444" in response.answer
    assert "555" in response.answer
    assert "999999999" not in response.answer
    assert response.data["tool_result"]["methods"][0]["var"] == 444.0


def test_m11_model_clarification_does_not_execute_numerical_tool() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            intent="ambiguous",
            requires_clarification=True,
            clarification="Do you want VaR/ES, limits, contributors, or stress?",
        )
    )

    response = engine.answer_with_model("How risky are we?", SAMPLE_PORTFOLIO, service, model)

    assert service.calls == []
    assert response.intent == "ambiguous"
    assert response.tool_name is None
    assert response.requires_clarification
    assert response.data["tool_result"] is None
    assert "VaR/ES" in response.answer


def test_m11_model_refusal_does_not_execute_risk_tool() -> None:
    engine = RiskQueryEngine()
    service = _FixtureService()
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            intent="unsupported",
            refusal="I cannot provide trading advice or unsupported forecasts.",
        )
    )

    response = engine.answer_with_model(
        "Should we buy more NVDA tomorrow?", SAMPLE_PORTFOLIO, service, model
    )

    assert service.calls == []
    assert response.intent == "unsupported"
    assert response.tool_name is None
    assert response.requires_clarification
    assert response.data["tool_result"] is None
    assert "trading advice" in response.answer
