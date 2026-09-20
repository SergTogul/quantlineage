"""get_position_greeks — grounded option/equity Greeks for Risk Query."""

from __future__ import annotations

from app.risk.query import RiskQueryEngine, RiskToolName, validate_tool_call
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService
from app.services.risk_factories import build_portfolio_service


def test_validate_get_position_greeks_allowlisted() -> None:
    checked = validate_tool_call("get_position_greeks", {"greek": "delta", "top_n": 3})
    assert checked.allowed is True
    assert checked.tool_name == RiskToolName.GET_POSITION_GREEKS
    assert checked.args["greek"] == "delta"
    assert checked.args["top_n"] == 3


def test_deterministic_router_maps_biggest_options_delta_to_greeks_tool() -> None:
    plan = RiskQueryEngine().route("Biggest options delta?")
    assert plan.needs_clarification is False
    assert plan.tool_name == RiskToolName.GET_POSITION_GREEKS
    assert plan.tool_args.get("greek") == "delta"


def test_answer_biggest_options_delta_returns_grounded_positions() -> None:
    service = build_portfolio_service()
    assert isinstance(service, PortfolioService)

    response = RiskQueryEngine().answer(
        "Biggest options delta?",
        SAMPLE_PORTFOLIO,
        service,
    )

    assert response.requires_clarification is False
    assert response.tool_name == "get_position_greeks"
    assert response.intent == "position_greeks"
    result = response.data["tool_result"]
    assert result["greek"] == "delta"
    assert result["positions"]
    assert "delta" in response.answer.lower()
    top = result["positions"][0]
    assert _fmt_in(response.answer, top["value"])


def test_answer_with_model_does_not_refuse_greeks_when_tool_exists() -> None:
    from app.risk.query import RiskAssistantModelResponse

    class _Scripted:
        def complete(self, request):  # noqa: ANN001
            del request
            return RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_POSITION_GREEKS,
                tool_args={"greek": "delta"},
                intent="position_greeks",
            )

    service = build_portfolio_service()
    response = RiskQueryEngine().answer_with_model(
        "Biggest options delta?",
        SAMPLE_PORTFOLIO,
        service,
        _Scripted(),
    )

    assert response.tool_name == "get_position_greeks"
    assert response.requires_clarification is False
    assert "not available" not in response.answer.lower()


def _fmt_in(answer: str, value: float) -> bool:
    from app.risk.query import _fmt

    return _fmt(value) in answer or f"{abs(value):.0f}" in answer or f"{value:.4g}" in answer
