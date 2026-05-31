from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel

from app.api.schemas import RiskQueryResponse
from app.domain.models import Portfolio


class RiskToolName(str, Enum):
    GET_PORTFOLIO_SUMMARY = "get_portfolio_summary"
    GET_VAR_ES = "get_var_es"
    GET_WORST_STRESS = "get_worst_stress"
    GET_LIMITS = "get_limits"
    GET_CONTRIBUTORS = "get_contributors"


class RiskToolContract(BaseModel):
    name: RiskToolName
    description: str
    service_method: str
    required_inputs: list[str]
    returns: list[str]
    numeric_source: str


class RiskAssistantModelRequest(BaseModel):
    question: str
    tools: list[dict[str, Any]]
    instruction: str = (
        "Select at most one deterministic RiskForge tool. Do not calculate or invent "
        "VaR, Greeks, P&L, prices, stress losses, or limit values. Ask for clarification "
        "or refuse unsupported/advisory prompts instead of calling a numerical tool."
    )


class RiskAssistantModelResponse(BaseModel):
    tool_name: RiskToolName | None = None
    intent: str | None = None
    requires_clarification: bool = False
    clarification: str | None = None
    refusal: str | None = None
    rationale: str | None = None
    proposed_answer: str | None = None


class RiskAssistantModel(Protocol):
    """Provider-agnostic model adapter for one RiskForge tool-selection turn."""

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        """Return one tool request, a clarification, or a refusal."""


class RiskQueryPlan(BaseModel):
    intent: str
    tool_name: RiskToolName | None = None
    needs_clarification: bool = False
    clarification: str | None = None


TOOL_CONTRACTS: dict[RiskToolName, RiskToolContract] = {
    RiskToolName.GET_PORTFOLIO_SUMMARY: RiskToolContract(
        name=RiskToolName.GET_PORTFOLIO_SUMMARY,
        description="Summarize portfolio market value and aggregate risk measures.",
        service_method="summary",
        required_inputs=["portfolio"],
        returns=["RiskSummary"],
        numeric_source="deterministic PortfolioService.summary payload",
    ),
    RiskToolName.GET_VAR_ES: RiskToolContract(
        name=RiskToolName.GET_VAR_ES,
        description="Return VaR and Expected Shortfall analytics.",
        service_method="var_report",
        required_inputs=["portfolio"],
        returns=["VaRReport"],
        numeric_source="deterministic PortfolioService.var_report payload",
    ),
    RiskToolName.GET_WORST_STRESS: RiskToolContract(
        name=RiskToolName.GET_WORST_STRESS,
        description="Identify the worst configured stress or threat scenario.",
        service_method="threat_evaluation",
        required_inputs=["portfolio"],
        returns=["ScenarioEvaluationReport"],
        numeric_source="deterministic PortfolioService.threat_evaluation payload",
    ),
    RiskToolName.GET_LIMITS: RiskToolContract(
        name=RiskToolName.GET_LIMITS,
        description="List current risk limits and breach status.",
        service_method="limits",
        required_inputs=["portfolio"],
        returns=["list[LimitResult]"],
        numeric_source="deterministic PortfolioService.limits payload",
    ),
    RiskToolName.GET_CONTRIBUTORS: RiskToolContract(
        name=RiskToolName.GET_CONTRIBUTORS,
        description="Rank top position-level risk contributors.",
        service_method="contributors",
        required_inputs=["portfolio"],
        returns=["list[Contributor]"],
        numeric_source="deterministic PortfolioService.contributors payload",
    ),
}


def tool_contract_schemas() -> list[dict[str, Any]]:
    """Serializable deterministic tool contracts for the future LLM layer."""
    return [
        contract.model_dump(mode="json")
        for contract in TOOL_CONTRACTS.values()
    ]


class DeterministicRiskAssistantModel:
    """Offline model adapter used for tests and local development."""

    def __init__(self, router: RiskQueryEngine | None = None) -> None:
        self.router = router or RiskQueryEngine()

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        plan = self.router.route(request.question)
        return RiskAssistantModelResponse(
            tool_name=plan.tool_name,
            intent=plan.intent,
            requires_clarification=plan.needs_clarification,
            clarification=plan.clarification,
            rationale="deterministic offline router",
        )


class RiskQueryEngine:
    """Deterministic query router. An LLM can later call the same service methods as tools."""

    def route(self, question: str) -> RiskQueryPlan:
        q = " ".join(question.lower().strip().split())
        if not q:
            return _clarification_plan(
                "unsupported",
                "Ask a supported portfolio risk question: VaR/ES, limits, contributors, "
                "worst stress, or portfolio summary.",
            )
        if _mentions(q, "worst", "largest") and _mentions(q, "stress", "scenario", "threat"):
            return RiskQueryPlan(
                intent="worst_scenario",
                tool_name=RiskToolName.GET_WORST_STRESS,
            )
        if _mentions(q, "contributor", "contributors", "dominate", "biggest risk", "top risk"):
            return RiskQueryPlan(
                intent="contributors",
                tool_name=RiskToolName.GET_CONTRIBUTORS,
            )
        if _mentions(q, "limit", "limits", "breach", "breaches"):
            return RiskQueryPlan(intent="limits", tool_name=RiskToolName.GET_LIMITS)
        if _mentions(q, "var", "expected shortfall", "es"):
            return RiskQueryPlan(intent="var", tool_name=RiskToolName.GET_VAR_ES)
        if _mentions(q, "summary", "summarize", "overview", "portfolio"):
            return RiskQueryPlan(
                intent="portfolio_summary",
                tool_name=RiskToolName.GET_PORTFOLIO_SUMMARY,
            )
        if _mentions(q, "risk", "exposure", "loss"):
            return _clarification_plan(
                "ambiguous",
                "Please choose a deterministic risk view: VaR/ES, limits, contributors, "
                "worst stress, or portfolio summary.",
            )
        return _clarification_plan(
            "unsupported",
            "I can only answer supported portfolio risk questions using deterministic "
            "RiskForge tools: VaR/ES, limits, contributors, worst stress, or portfolio summary.",
        )

    def answer(self, question: str, portfolio: Portfolio, service) -> RiskQueryResponse:
        plan = self.route(question)
        if plan.tool_name is None:
            return RiskQueryResponse(
                intent=plan.intent,
                answer=plan.clarification or "",
                data={
                    "tool_contract": None,
                    "tool_result": None,
                    "supported_tools": tool_contract_schemas(),
                },
                tool_name=None,
                requires_clarification=True,
            )

        contract = TOOL_CONTRACTS[plan.tool_name]
        payload = _execute_tool(plan.tool_name, portfolio, service)
        data = {
            "tool_contract": contract.model_dump(mode="json"),
            "tool_result": payload,
        }
        return RiskQueryResponse(
            intent=plan.intent,
            answer=_format_answer(plan.tool_name, payload),
            data=data,
            tool_name=plan.tool_name.value,
        )

    def answer_with_model(
        self,
        question: str,
        portfolio: Portfolio,
        service,
        model: RiskAssistantModel,
    ) -> RiskQueryResponse:
        request = RiskAssistantModelRequest(
            question=question,
            tools=tool_contract_schemas(),
        )
        model_response = model.complete(request)
        model_data = model_response.model_dump(mode="json")
        if (
            model_response.refusal
            or model_response.requires_clarification
            or model_response.tool_name is None
        ):
            return RiskQueryResponse(
                intent=model_response.intent
                or ("unsupported" if model_response.refusal else "ambiguous"),
                answer=model_response.refusal
                or model_response.clarification
                or (
                    "Please choose a deterministic risk view: VaR/ES, limits, contributors, "
                    "worst stress, or portfolio summary."
                ),
                data={
                    "tool_contract": None,
                    "tool_result": None,
                    "supported_tools": tool_contract_schemas(),
                    "model": model_data,
                },
                tool_name=None,
                requires_clarification=True,
            )

        contract = TOOL_CONTRACTS[model_response.tool_name]
        payload = _execute_tool(model_response.tool_name, portfolio, service)
        return RiskQueryResponse(
            intent=model_response.intent or _intent_for_tool(model_response.tool_name),
            answer=_format_answer(model_response.tool_name, payload),
            data={
                "tool_contract": contract.model_dump(mode="json"),
                "tool_result": payload,
                "model": model_data,
            },
            tool_name=model_response.tool_name.value,
        )


def _execute_tool(tool_name: RiskToolName, portfolio: Portfolio, service) -> dict[str, Any]:
    if tool_name == RiskToolName.GET_PORTFOLIO_SUMMARY:
        return _dump(service.summary(portfolio))
    if tool_name == RiskToolName.GET_VAR_ES:
        return _dump(service.var_report(portfolio))
    if tool_name == RiskToolName.GET_WORST_STRESS:
        return _dump(service.threat_evaluation(portfolio))
    if tool_name == RiskToolName.GET_LIMITS:
        return {"limits": [_dump(item) for item in service.limits(portfolio)]}
    if tool_name == RiskToolName.GET_CONTRIBUTORS:
        return {"contributors": [_dump(item) for item in service.contributors(portfolio)[:5]]}
    raise ValueError(f"unsupported risk tool: {tool_name}")


def _format_answer(tool_name: RiskToolName, payload: dict[str, Any]) -> str:
    if tool_name == RiskToolName.GET_PORTFOLIO_SUMMARY:
        return (
            f"Portfolio market value is {_fmt(payload.get('market_value'))}; "
            f"99% VaR is {_fmt(payload.get('var_99'))}; "
            f"99% Expected Shortfall is {_fmt(payload.get('expected_shortfall_99'))}."
        )
    if tool_name == RiskToolName.GET_VAR_ES:
        methods = payload.get("methods") or []
        parts = []
        for item in methods:
            label = item.get("method", "method")
            confidence = item.get("confidence")
            var_value = _fmt(item.get("var"))
            if confidence is None:
                parts.append(f"{label} VaR is {var_value}")
            else:
                parts.append(f"{label} {float(confidence) * 100:.0f}% VaR is {var_value}")
            if item.get("expected_shortfall") is not None:
                parts[-1] += f" and Expected Shortfall is {_fmt(item.get('expected_shortfall'))}"
        return "; ".join(parts) + "." if parts else "No VaR/ES methods returned."
    if tool_name == RiskToolName.GET_WORST_STRESS:
        scenario = payload.get("worst_scenario")
        loss = payload.get("worst_loss")
        if scenario is None:
            return "No stress scenarios returned."
        return f"Worst stress scenario is {scenario} with loss {_fmt(loss)}."
    if tool_name == RiskToolName.GET_LIMITS:
        limits = payload.get("limits") or []
        breaches = [item for item in limits if item.get("breached")]
        return f"{len(breaches)} limit breaches from {len(limits)} evaluated limits."
    if tool_name == RiskToolName.GET_CONTRIBUTORS:
        contributors = payload.get("contributors") or []
        if not contributors:
            return "No risk contributors returned."
        names = [
            f"{item.get('label', item.get('position_id'))} {float(item.get('contribution_pct', 0.0)):.1f}%"
            for item in contributors
        ]
        return "Top risk contributors: " + ", ".join(names) + "."
    raise ValueError(f"unsupported risk tool: {tool_name}")


def _intent_for_tool(tool_name: RiskToolName) -> str:
    if tool_name == RiskToolName.GET_PORTFOLIO_SUMMARY:
        return "portfolio_summary"
    if tool_name == RiskToolName.GET_VAR_ES:
        return "var"
    if tool_name == RiskToolName.GET_WORST_STRESS:
        return "worst_scenario"
    if tool_name == RiskToolName.GET_LIMITS:
        return "limits"
    if tool_name == RiskToolName.GET_CONTRIBUTORS:
        return "contributors"
    raise ValueError(f"unsupported risk tool: {tool_name}")


def _dump(value) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _fmt(value: Any) -> str:
    return f"{float(value):,.0f}" if isinstance(value, int | float) else str(value)


def _mentions(question: str, *terms: str) -> bool:
    return any(term in question for term in terms)


def _clarification_plan(intent: str, message: str) -> RiskQueryPlan:
    return RiskQueryPlan(
        intent=intent,
        needs_clarification=True,
        clarification=message,
    )
