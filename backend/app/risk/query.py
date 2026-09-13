from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.schemas import RiskQueryResponse
from app.domain.models import Portfolio
from app.risk.tool_contracts import C1_ARG_MODELS, CompareRiskRunsArgs, execute_allowlisted_tool


class RiskToolName(str, Enum):
    GET_PORTFOLIO_SUMMARY = "get_portfolio_summary"
    GET_VAR_ES = "get_var_es"
    GET_WORST_STRESS = "get_worst_stress"
    GET_LIMITS = "get_limits"
    GET_CONTRIBUTORS = "get_contributors"
    EXPLAIN_RISK_CHANGE = "explain_risk_change"
    SEARCH_INSTRUMENTS = "search_instruments"
    GET_MARKET_HISTORY = "get_market_history"
    GET_DATA_QUALITY = "get_data_quality"
    RUN_PORTFOLIO_RISK = "run_portfolio_risk"
    GET_RISK_RUN = "get_risk_run"
    COMPARE_RISK_RUNS = "compare_risk_runs"
    RUN_STRESS = "run_stress"
    GET_KEY_RATE_DV01 = "get_key_rate_dv01"
    GET_TOP_RISK_CONTRIBUTORS = "get_top_risk_contributors"
    GET_RUN_PROVENANCE = "get_run_provenance"


class RiskToolContract(BaseModel):
    name: RiskToolName
    description: str
    service_method: str
    required_inputs: list[str]
    returns: list[str]
    numeric_source: str
    http_path: str = ""
    provenance_fields: list[str] = Field(default_factory=list)


class RiskAssistantModelRequest(BaseModel):
    question: str
    tools: list[dict[str, Any]]
    instruction: str = (
        "Select at most one deterministic RiskForge tool. Do not calculate or invent "
        "VaR, Greeks, P&L, prices, stress losses, or limit values. Ask for clarification "
        "or refuse unsupported/advisory prompts instead of calling a numerical tool."
    )


class RiskAssistantModelResponse(BaseModel):
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
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


class RiskToolArgs(BaseModel):
    """Model-bindable tool arguments. Portfolio is bound by RiskForge, never the LLM."""

    model_config = ConfigDict(extra="forbid")


ExplainRiskChangeArgs = CompareRiskRunsArgs


class ToolCallValidation(BaseModel):
    allowed: bool
    tool_name: RiskToolName | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    refusal: str | None = None


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
    RiskToolName.EXPLAIN_RISK_CHANGE: RiskToolContract(
        name=RiskToolName.EXPLAIN_RISK_CHANGE,
        description=(
            "Explain why a risk metric changed between two COMPLETED RiskRuns. "
            "Requires t0_run_id and t1_run_id; never invent VaR or other numbers. "
            "Shares compare_runs with compare_risk_runs."
        ),
        service_method="compare_runs",
        required_inputs=["t0_run_id", "t1_run_id"],
        returns=["RiskChangeReport"],
        numeric_source="deterministic RiskRunWorker.compare_runs payload",
        http_path="POST /api/v1/risk/runs/compare",
        provenance_fields=[
            "t0_run_id",
            "t1_run_id",
            "metric",
            "unit",
            "sign_convention",
            "identity",
        ],
    ),
    RiskToolName.SEARCH_INSTRUMENTS: RiskToolContract(
        name=RiskToolName.SEARCH_INSTRUMENTS,
        description="Search the curated instrument catalog. Curated identity wins.",
        service_method="search_catalog",
        required_inputs=["query"],
        returns=["list[CatalogSearchHit]"],
        numeric_source="deterministic search_catalog metadata payload",
        http_path="GET /api/v1/instruments/search",
        provenance_fields=["instrument_id", "provider", "source_symbol"],
    ),
    RiskToolName.GET_MARKET_HISTORY: RiskToolContract(
        name=RiskToolName.GET_MARKET_HISTORY,
        description=(
            "Return normalized instrument price/percent levels and series lineage. "
            "Does not compute returns and is not Wave B historical-analytics."
        ),
        service_method="get_market_history",
        required_inputs=["instrument_id", "start", "end"],
        returns=["InstrumentHistoryOut"],
        numeric_source=(
            "deterministic GET /api/v1/market/history levels payload; "
            "not historical-analytics"
        ),
        http_path="GET /api/v1/market/history/{instrument_id}",
        provenance_fields=[
            "instrument_id",
            "source",
            "source_symbol",
            "content_hash",
            "normalization_version",
            "unit",
        ],
    ),
    RiskToolName.GET_DATA_QUALITY: RiskToolContract(
        name=RiskToolName.GET_DATA_QUALITY,
        description="Return series lineage and quality flags without history points.",
        service_method="validate_series",
        required_inputs=["instrument_id", "start", "end"],
        returns=["SeriesLineage"],
        numeric_source="deterministic GET /api/v1/instruments/{id}/quality payload",
        http_path="GET /api/v1/instruments/{instrument_id}/quality",
        provenance_fields=["content_hash", "unit", "currency", "frequency", "adjustment"],
    ),
    RiskToolName.RUN_PORTFOLIO_RISK: RiskToolContract(
        name=RiskToolName.RUN_PORTFOLIO_RISK,
        description=(
            "Enqueue a portfolio RiskRun (summary or var). "
            "Prefer run identity over a synchronous dump."
        ),
        service_method="submit",
        required_inputs=["portfolio", "run_type"],
        returns=["RiskRunView"],
        numeric_source="deterministic RiskRunWorker.submit payload",
        http_path="POST /api/v1/risk/runs",
        provenance_fields=[
            "id",
            "portfolio_id",
            "portfolio_version",
            "market_snapshot_id",
            "historical_dataset_id",
            "historical_dataset_version",
            "as_of",
            "methodology",
        ],
    ),
    RiskToolName.GET_RISK_RUN: RiskToolContract(
        name=RiskToolName.GET_RISK_RUN,
        description="Read a persisted RiskRun. Stale ids fail closed.",
        service_method="get",
        required_inputs=["run_id"],
        returns=["RiskRunView"],
        numeric_source="deterministic RiskRunWorker.get payload",
        http_path="GET /api/v1/risk/runs/{run_id}",
        provenance_fields=[
            "id",
            "market_snapshot_id",
            "historical_dataset_id",
            "as_of",
            "methodology",
        ],
    ),
    RiskToolName.COMPARE_RISK_RUNS: RiskToolContract(
        name=RiskToolName.COMPARE_RISK_RUNS,
        description=(
            "Compare two COMPLETED RiskRuns. Same compare_runs engine as "
            "explain_risk_change; no second kernel."
        ),
        service_method="compare_runs",
        required_inputs=["t0_run_id", "t1_run_id"],
        returns=["RiskChangeReport"],
        numeric_source="deterministic RiskRunWorker.compare_runs payload",
        http_path="POST /api/v1/risk/runs/compare",
        provenance_fields=[
            "t0_run_id",
            "t1_run_id",
            "metric",
            "unit",
            "sign_convention",
            "identity",
        ],
    ),
    RiskToolName.RUN_STRESS: RiskToolContract(
        name=RiskToolName.RUN_STRESS,
        description=(
            "Enqueue an allowlisted named stress RiskRun (DEFAULT_SCENARIOS, "
            "including eq_down_10 / equity-down). Not arbitrary shocks."
        ),
        service_method="submit",
        required_inputs=["portfolio", "scenario_id"],
        returns=["RiskRunView"],
        numeric_source="deterministic RiskRunWorker.submit stress payload",
        http_path="POST /api/v1/risk/runs",
        provenance_fields=["id", "run_type", "market_snapshot_id", "as_of", "methodology"],
    ),
    RiskToolName.GET_KEY_RATE_DV01: RiskToolContract(
        name=RiskToolName.GET_KEY_RATE_DV01,
        description=(
            "USD key-rate DV01 from the rates-macro showcase (2Y/5Y/10Y). "
            "Demo book only; not a second bump engine."
        ),
        service_method="build_rates_showcase",
        required_inputs=[],
        returns=["RatesShowcaseView"],
        numeric_source="deterministic GET /api/v1/market/rates-showcase payload",
        http_path="GET /api/v1/market/rates-showcase",
        provenance_fields=["portfolio_id", "market_snapshot_id", "unit"],
    ),
    RiskToolName.GET_TOP_RISK_CONTRIBUTORS: RiskToolContract(
        name=RiskToolName.GET_TOP_RISK_CONTRIBUTORS,
        description="Enqueue a contributors RiskRun (parametric component VaR).",
        service_method="submit",
        required_inputs=["portfolio"],
        returns=["RiskRunView"],
        numeric_source="deterministic RiskRunWorker.submit contributors payload",
        http_path="POST /api/v1/risk/runs",
        provenance_fields=["id", "run_type", "portfolio_id", "market_snapshot_id"],
    ),
    RiskToolName.GET_RUN_PROVENANCE: RiskToolContract(
        name=RiskToolName.GET_RUN_PROVENANCE,
        description="Return persisted RiskRun lineage. Never invents release_sha.",
        service_method="provenance_from_risk_run",
        required_inputs=["run_id"],
        returns=["RiskRunProvenance"],
        numeric_source="deterministic GET /api/v1/risk/runs/{id}/provenance payload",
        http_path="GET /api/v1/risk/runs/{run_id}/provenance",
        provenance_fields=[
            "risk_run_id",
            "portfolio_id",
            "market_snapshot_id",
            "as_of",
            "historical_dataset_id",
            "methodology",
        ],
    ),
}

TOOL_ARG_MODELS: dict[RiskToolName, type[BaseModel]] = {
    name: RiskToolArgs for name in TOOL_CONTRACTS
}
for _c1_name, _c1_model in C1_ARG_MODELS.items():
    TOOL_ARG_MODELS[RiskToolName(_c1_name)] = _c1_model

SAFE_UNGROUNDED_ANSWER = (
    "I cannot ignore deterministic tools or invent VaR, Greeks, P&L, prices, "
    "stress losses, or limit values. Ask a supported portfolio risk question: "
    "VaR/ES, limits, contributors, worst stress, portfolio summary, or why risk changed."
)

_INJECTION_MARKERS = (
    "ignore tools",
    "ignore the tools",
    "invent var",
    "invent a var",
    "disregard tools",
    "forget the tools",
    "ignore previous",
)


def tool_json_schemas() -> dict[str, dict[str, Any]]:
    """Pydantic JSON Schema for each allowlisted RiskToolName (TOOL_CONTRACTS keys only)."""
    return {
        name.value: TOOL_ARG_MODELS[name].model_json_schema()
        for name in TOOL_CONTRACTS
    }


def tool_contract_schemas() -> list[dict[str, Any]]:
    """Serializable deterministic tool contracts for the future LLM layer."""
    json_schemas = tool_json_schemas()
    return [
        {**contract.model_dump(mode="json"), "json_schema": json_schemas[contract.name.value]}
        for contract in TOOL_CONTRACTS.values()
    ]


def validate_tool_call(
    tool_name: str | RiskToolName | None,
    args: dict[str, Any] | None = None,
) -> ToolCallValidation:
    """Allowlist tool names to TOOL_CONTRACTS keys and validate args against JSON Schema."""
    if tool_name is None or tool_name == "":
        return ToolCallValidation(
            allowed=False,
            refusal="No allowlisted RiskForge tool was selected.",
        )
    raw = tool_name.value if isinstance(tool_name, RiskToolName) else str(tool_name)
    try:
        name = RiskToolName(raw)
    except ValueError:
        return ToolCallValidation(
            allowed=False,
            refusal="Unknown tool is not in the RiskForge allowlist.",
        )
    if name not in TOOL_CONTRACTS:
        return ToolCallValidation(
            allowed=False,
            refusal="Unknown tool is not in the RiskForge allowlist.",
        )
    try:
        parsed = TOOL_ARG_MODELS[name].model_validate(args or {})
    except ValidationError:
        return ToolCallValidation(
            allowed=False,
            refusal="Tool arguments failed JSON-schema validation.",
        )
    return ToolCallValidation(allowed=True, tool_name=name, args=parsed.model_dump())


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
        if _is_prompt_injection(q):
            return _clarification_plan("unsupported", SAFE_UNGROUNDED_ANSWER)
        if _is_risk_change_question(q):
            return RiskQueryPlan(
                intent="explain_risk_change",
                tool_name=RiskToolName.EXPLAIN_RISK_CHANGE,
                needs_clarification=True,
                clarification=(
                    "Provide two completed RiskRun identifiers to explain why the "
                    "risk metric changed. Do not invent VaR."
                ),
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
        if plan.tool_name is None or plan.needs_clarification:
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

        checked = validate_tool_call(plan.tool_name, {})
        if not checked.allowed or checked.tool_name is None:
            return RiskQueryResponse(
                intent="unsupported",
                answer=_safe_ungrounded_text(checked.refusal, fallback=SAFE_UNGROUNDED_ANSWER),
                data={
                    "tool_contract": None,
                    "tool_result": None,
                    "supported_tools": tool_contract_schemas(),
                },
                tool_name=None,
                requires_clarification=True,
            )
        contract = TOOL_CONTRACTS[checked.tool_name]
        payload = _execute_tool(checked.tool_name, portfolio, service)
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
        default_clarification = (
            "Please choose a deterministic risk view: VaR/ES, limits, contributors, "
            "worst stress, or portfolio summary."
        )
        if (
            model_response.refusal
            or model_response.requires_clarification
            or model_response.tool_name is None
        ):
            return RiskQueryResponse(
                intent=model_response.intent
                or ("unsupported" if model_response.refusal else "ambiguous"),
                answer=_safe_ungrounded_text(
                    model_response.refusal,
                    model_response.clarification,
                    fallback=default_clarification,
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

        checked = validate_tool_call(model_response.tool_name, model_response.tool_args)
        if not checked.allowed or checked.tool_name is None:
            return RiskQueryResponse(
                intent="unsupported",
                answer=_safe_ungrounded_text(
                    checked.refusal, fallback=SAFE_UNGROUNDED_ANSWER
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

        contract = TOOL_CONTRACTS[checked.tool_name]
        payload = _execute_tool(checked.tool_name, portfolio, service, args=checked.args)
        return RiskQueryResponse(
            intent=model_response.intent or _intent_for_tool(checked.tool_name),
            answer=_format_answer(checked.tool_name, payload),
            data={
                "tool_contract": contract.model_dump(mode="json"),
                "tool_result": payload,
                "model": model_data,
            },
            tool_name=checked.tool_name.value,
        )


def _execute_tool(
    tool_name: RiskToolName,
    portfolio: Portfolio,
    service,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = args or {}
    if tool_name.value in C1_ARG_MODELS:
        return execute_allowlisted_tool(tool_name.value, portfolio, service, args)
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
    if tool_name in (
        RiskToolName.EXPLAIN_RISK_CHANGE,
        RiskToolName.COMPARE_RISK_RUNS,
    ):
        return (
            f"Metric {payload.get('metric')} changed from {_fmt(payload.get('previous_risk'))} "
            f"to {_fmt(payload.get('current_risk'))} "
            f"(total {_fmt(payload.get('total_change'))}); "
            f"residual {_fmt(payload.get('residual'))}."
        )
    return _format_c1_answer(tool_name, payload)


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
    if tool_name == RiskToolName.EXPLAIN_RISK_CHANGE:
        return "explain_risk_change"
    return tool_name.value


def _dump(value) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _format_c1_answer(tool_name: RiskToolName, payload: dict[str, Any]) -> str:
    """Summarize C1 payloads without computing risk numbers."""
    if tool_name == RiskToolName.RUN_PORTFOLIO_RISK:
        return (
            f"Submitted RiskRun {payload.get('id')} "
            f"({payload.get('run_type')}) with status {payload.get('status')}."
        )
    if tool_name == RiskToolName.GET_RISK_RUN:
        return (
            f"RiskRun {payload.get('id')} status is {payload.get('status')} "
            f"for {payload.get('run_type')}."
        )
    if tool_name == RiskToolName.GET_MARKET_HISTORY:
        points = payload.get("points") or []
        return (
            f"History for {payload.get('instrument_id')} has {len(points)} "
            f"level observations (unit {payload.get('unit')})."
        )
    if tool_name == RiskToolName.GET_DATA_QUALITY:
        return f"Quality lineage for {payload.get('instrument_id')} from validate_series."
    if tool_name == RiskToolName.SEARCH_INSTRUMENTS:
        hits = payload.get("hits") or []
        return f"Catalog search returned {len(hits)} hits."
    if tool_name == RiskToolName.RUN_STRESS:
        return (
            f"Submitted stress RiskRun {payload.get('id')} "
            f"with status {payload.get('status')}."
        )
    if tool_name == RiskToolName.GET_KEY_RATE_DV01:
        rows = payload.get("key_rate_dv01") or []
        labels = ", ".join(str(row.get("tenor")) for row in rows) or "none"
        return (
            f"Rates showcase KR-DV01 tenors: {labels} "
            f"(snapshot {payload.get('market_snapshot_id')})."
        )
    if tool_name == RiskToolName.GET_TOP_RISK_CONTRIBUTORS:
        return (
            f"Submitted contributors RiskRun {payload.get('id')} "
            f"with status {payload.get('status')}."
        )
    if tool_name == RiskToolName.GET_RUN_PROVENANCE:
        return (
            f"Provenance for RiskRun {payload.get('risk_run_id')} "
            f"methodology {payload.get('methodology')}."
        )
    return f"Deterministic tool {tool_name.value} returned a service payload."


def _fmt(value: Any) -> str:
    return f"{float(value):,.0f}" if isinstance(value, int | float) else str(value)


def _mentions(question: str, *terms: str) -> bool:
    return any(term in question for term in terms)


def _is_risk_change_question(question: str) -> bool:
    if not _mentions(question, "why", "explain"):
        return False
    if not _mentions(question, "var", "risk", "es", "expected shortfall", "dv01", "vega"):
        return False
    return _mentions(question, "change", "increase", "decrease", "moved", "up", "down")


def _is_prompt_injection(question: str) -> bool:
    return any(marker in question for marker in _INJECTION_MARKERS)


def _contains_ungrounded_number(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _safe_ungrounded_text(*candidates: str | None, fallback: str) -> str:
    for text in candidates:
        if text and not _contains_ungrounded_number(text):
            return text
    if fallback and not _contains_ungrounded_number(fallback):
        return fallback
    return SAFE_UNGROUNDED_ANSWER


def _clarification_plan(intent: str, message: str) -> RiskQueryPlan:
    return RiskQueryPlan(
        intent=intent,
        needs_clarification=True,
        clarification=message,
    )
