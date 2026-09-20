from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.schemas import RiskQueryAssistantMetadata, RiskQueryResponse
from app.domain.models import Portfolio
from app.risk.tool_contracts import (
    C1_ARG_MODELS,
    TOOL_ARG_MAX_CHARS,
    CompareRiskRunsArgs,
    execute_allowlisted_tool,
)
from app.services.risk_run_service import RiskRunNotFound


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
    GET_POSITION_GREEKS = "get_position_greeks"


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
    portfolio_id: str | None = None
    available_run_ids: list[str] = Field(default_factory=list)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    instruction: str = (
        "Select at most one deterministic QuantLineage tool. Do not calculate or invent "
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
    tool_call_id: str | None = None
    provider_response_id: str | None = None


class RiskAssistantModel(Protocol):
    """Provider-agnostic model adapter for one QuantLineage tool-selection turn."""

    def complete(self, request: RiskAssistantModelRequest) -> RiskAssistantModelResponse:
        """Return one tool request, a clarification, or a refusal."""


AssistantMode = Literal[
    "model-narrated",
    "model-routed",
    "deterministic",
    "preflight-refused",
    "fallback",
]


@dataclass(frozen=True, slots=True)
class AssistantMetadataContext:
    """Configured provider label for optional query response metadata."""

    provider: Literal["deterministic", "openai"]
    model: str | None = None


def build_assistant_metadata(
    context: AssistantMetadataContext,
    *,
    mode: AssistantMode,
    fallback: bool,
) -> dict[str, Any]:
    """Return a safe ``data.assistant`` payload (no secrets or model internals)."""
    return RiskQueryAssistantMetadata(
        provider=context.provider,
        model=context.model,
        mode=mode,
        fallback=fallback,
    ).model_dump(mode="json")


def _normalized_question(question: str) -> str:
    return " ".join(question.strip().split()).lower()


def _ungrounded_assistant_response(
    *,
    context: AssistantMetadataContext,
    mode: AssistantMode,
    fallback: bool,
    answer: str,
) -> RiskQueryResponse:
    """Clarification/refusal with truthful assistant metadata and no tool result."""
    return RiskQueryResponse(
        intent="unsupported",
        answer=answer,
        data={
            "tool_contract": None,
            "tool_result": None,
            "supported_tools": tool_contract_schemas(),
            "assistant": build_assistant_metadata(
                context, mode=mode, fallback=fallback
            ),
        },
        tool_name=None,
        requires_clarification=True,
    )


class RiskQueryPlan(BaseModel):
    intent: str
    tool_name: RiskToolName | None = None
    needs_clarification: bool = False
    clarification: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)


class RiskToolArgs(BaseModel):
    """Model-bindable tool arguments. Portfolio is bound by QuantLineage, never the LLM."""

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
        description=(
            "Rank top position-level risk contributors (component VaR / risk share). "
            "Not for option Greeks such as delta, gamma, vega, or theta."
        ),
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
        service_method="get_data_quality",
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
        service_method="get_run_provenance",
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
    RiskToolName.GET_POSITION_GREEKS: RiskToolContract(
        name=RiskToolName.GET_POSITION_GREEKS,
        description=(
            "Rank positions by a valuation Greek from PricingEngine "
            "(delta, gamma, vega, dv01, or fx_delta). Use options_only or "
            "instrument_types to restrict families. Not component VaR contributors."
        ),
        service_method="position_greeks",
        required_inputs=["portfolio"],
        returns=["PositionGreeksReport"],
        numeric_source="deterministic PortfolioService.position_greeks from Valuation",
        provenance_fields=[
            "portfolio_id",
            "market_snapshot_id",
            "greek",
            "unit",
            "convention",
            "pricing_engine",
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

_SECRET_REFUSAL_ANSWER = (
    "I cannot disclose API keys, tokens, passwords, or other secrets."
)

_FAKE_TOOL_REFUSAL_ANSWER = (
    "Unknown tool is not in the QuantLineage allowlist."
)

_GREEKS_UNSUPPORTED_ANSWER = (
    "Theta and rho are not available on valuation payloads. "
    "Ask for delta, gamma, vega, dv01, or fx_delta position Greeks instead."
)

_TOOL_FAILURE_ANSWER = (
    "The selected deterministic tool could not be executed. "
    "I cannot invent VaR, Expected Shortfall, or Greeks."
)

MISSING_ON_PAYLOAD = "not on this payload"

_CARD_IDENTITY_KEYS = (
    "metric",
    "value",
    "unit",
    "sign_convention",
    "as_of",
    "methodology",
    "market_snapshot_id",
    "historical_dataset_id",
    "historical_dataset_version",
)

_PROVENANCE_KEYS = (
    "metric",
    "value",
    "unit",
    "sign_convention",
    "risk_run_id",
    "id",
    "as_of",
    "methodology",
    "market_snapshot_id",
    "historical_dataset_id",
    "historical_dataset_version",
)

_RISK_CHANGE_CARD_KEYS = (
    "t0_run_id",
    "t1_run_id",
    "metric",
    "unit",
    "sign_convention",
    "previous_risk",
    "current_risk",
    "total_change",
    "portfolio_trade_change",
    "market_change",
    "explained_change",
    "residual",
    "residual_name",
    "disclosed_changes",
    "identity",
    "factor_contributors",
    "hierarchy_contributors",
    "items",
)

_NUMERIC_TOOLS = frozenset(
    {
        RiskToolName.GET_PORTFOLIO_SUMMARY,
        RiskToolName.GET_VAR_ES,
        RiskToolName.GET_WORST_STRESS,
        RiskToolName.GET_LIMITS,
        RiskToolName.GET_CONTRIBUTORS,
        RiskToolName.EXPLAIN_RISK_CHANGE,
        RiskToolName.COMPARE_RISK_RUNS,
        RiskToolName.RUN_PORTFOLIO_RISK,
        RiskToolName.GET_RISK_RUN,
        RiskToolName.RUN_STRESS,
        RiskToolName.GET_KEY_RATE_DV01,
        RiskToolName.GET_TOP_RISK_CONTRIBUTORS,
        RiskToolName.GET_RUN_PROVENANCE,
        RiskToolName.GET_POSITION_GREEKS,
    }
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

_FAKE_TOOL_MARKERS = (
    "estimate_var",
    "invent_var",
    "shell_exec",
    "call shell",
    "run shell",
    "hidden tool",
    "shell tool",
)

_SECRET_REQUEST_MARKERS = (
    "api key",
    "api-key",
    "apikey",
    "secret key",
    "password",
    "credential",
    "bearer token",
    "private key",
)

_SECRET_ENV_NAMES = (
    "FRED_API_KEY",
    "QUANTLINEAGE_API_TOKEN",
    "QUANTLINEAGE_API_TOKENS",
    "QUANTLINEAGE_MCP_AUTHORIZATION",
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
            refusal="No allowlisted QuantLineage tool was selected.",
        )
    raw = tool_name.value if isinstance(tool_name, RiskToolName) else str(tool_name)
    try:
        name = RiskToolName(raw)
    except ValueError:
        return ToolCallValidation(
            allowed=False,
            refusal="Unknown tool is not in the QuantLineage allowlist.",
        )
    if name not in TOOL_CONTRACTS:
        return ToolCallValidation(
            allowed=False,
            refusal="Unknown tool is not in the QuantLineage allowlist.",
        )
    if _tool_args_oversized(args):
        return ToolCallValidation(
            allowed=False,
            refusal="Tool arguments failed JSON-schema validation.",
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
            tool_args=dict(plan.tool_args),
            intent=plan.intent,
            requires_clarification=plan.needs_clarification,
            clarification=plan.clarification,
            rationale="deterministic offline router",
        )


class RiskQueryEngine:
    """Deterministic query router. An LLM can later call the same service methods as tools."""

    def route(self, question: str) -> RiskQueryPlan:
        original = " ".join(question.strip().split())
        q = original.lower()
        if not q:
            return _clarification_plan(
                "unsupported",
                "Ask a supported portfolio risk question: VaR/ES, limits, contributors, "
                "worst stress, portfolio summary, instrument search, history, stress, "
                "run comparison, or provenance.",
            )
        if _is_prompt_injection(q):
            return _clarification_plan("unsupported", SAFE_UNGROUNDED_ANSWER)
        if _is_fake_tool_request(q):
            return _clarification_plan("unsupported", _FAKE_TOOL_REFUSAL_ANSWER)
        if _is_secret_request(q):
            return _clarification_plan("unsupported", _SECRET_REFUSAL_ANSWER)
        if _is_greeks_question(q):
            greek = _infer_position_greek(q)
            if greek is None:
                return _clarification_plan("unsupported", _GREEKS_UNSUPPORTED_ANSWER)
            return RiskQueryPlan(
                intent="position_greeks",
                tool_name=RiskToolName.GET_POSITION_GREEKS,
                tool_args=_position_greeks_tool_args(q, greek),
            )
        if _is_advisory(q):
            return _clarification_plan(
                "unsupported",
                "I can only answer supported portfolio risk questions using deterministic "
                "QuantLineage tools: VaR/ES, limits, contributors, worst stress, or portfolio summary.",
            )
        collision = _ambiguous_tool_pair(q)
        if collision:
            return _clarification_plan("ambiguous", collision)
        if _is_risk_change_question(q):
            return _plan_for_two_run_ids(
                intent="explain_risk_change",
                tool_name=RiskToolName.EXPLAIN_RISK_CHANGE,
                question=original,
                missing=(
                    "Provide two completed RiskRun identifiers to explain why the "
                    "risk metric changed. Do not invent VaR."
                ),
            )
        if _is_compare_runs_question(q):
            return _plan_for_two_run_ids(
                intent="run_comparison",
                tool_name=RiskToolName.COMPARE_RISK_RUNS,
                question=original,
                missing=(
                    "Provide two completed RiskRun identifiers to compare. "
                    "Do not invent VaR."
                ),
            )
        if _is_provenance_question(q):
            run_ids = _extract_run_ids(original)
            if not run_ids:
                return _clarification_plan(
                    "provenance",
                    "Provide a completed RiskRun identifier for provenance. "
                    "Do not invent lineage.",
                    tool_name=RiskToolName.GET_RUN_PROVENANCE,
                )
            return RiskQueryPlan(
                intent="provenance",
                tool_name=RiskToolName.GET_RUN_PROVENANCE,
                tool_args={"run_id": run_ids[0]},
            )
        if _is_key_rate_dv01_question(q):
            args: dict[str, Any] = {}
            tenor = _extract_showcase_tenor(original)
            if tenor:
                args["tenor"] = tenor
            return RiskQueryPlan(
                intent="get_key_rate_dv01",
                tool_name=RiskToolName.GET_KEY_RATE_DV01,
                tool_args=args,
            )
        if _is_data_quality_question(q):
            instrument_id = _extract_instrument_id(original, extra_stopwords=_QUALITY_STOPWORDS)
            dates = _extract_iso_dates(original)
            if not instrument_id or len(dates) < 2:
                return _clarification_plan(
                    "quality",
                    "Provide an instrument id and a start and end date range. "
                    "Do not invent quality scores.",
                    tool_name=RiskToolName.GET_DATA_QUALITY,
                )
            return RiskQueryPlan(
                intent="quality",
                tool_name=RiskToolName.GET_DATA_QUALITY,
                tool_args={
                    "instrument_id": instrument_id,
                    "start": dates[0],
                    "end": dates[1],
                },
            )
        if _is_instrument_discovery(q):
            query = _extract_search_query(original)
            if not query:
                return _clarification_plan(
                    "instrument_discovery",
                    "Provide a catalog search query.",
                    tool_name=RiskToolName.SEARCH_INSTRUMENTS,
                )
            return RiskQueryPlan(
                intent="instrument_discovery",
                tool_name=RiskToolName.SEARCH_INSTRUMENTS,
                tool_args={"query": query},
            )
        if _is_history_question(q):
            instrument_id = _extract_instrument_id(original)
            dates = _extract_iso_dates(original)
            if not instrument_id or len(dates) < 2:
                return _clarification_plan(
                    "history",
                    "Provide an instrument id and a start and end date range. "
                    "Do not invent prices.",
                    tool_name=RiskToolName.GET_MARKET_HISTORY,
                )
            return RiskQueryPlan(
                intent="history",
                tool_name=RiskToolName.GET_MARKET_HISTORY,
                tool_args={
                    "instrument_id": instrument_id,
                    "start": dates[0],
                    "end": dates[1],
                },
            )
        if _mentions(q, "worst", "largest") and _mentions(q, "stress", "scenario", "threat"):
            return RiskQueryPlan(
                intent="worst_scenario",
                tool_name=RiskToolName.GET_WORST_STRESS,
            )
        scenario_id = _named_stress_scenario(q)
        if scenario_id or (_is_enqueue(q) and _mentions(q, "stress")):
            if not scenario_id:
                return _clarification_plan(
                    "stress",
                    "Choose an allowlisted stress scenario. Do not invent losses.",
                    tool_name=RiskToolName.RUN_STRESS,
                )
            return RiskQueryPlan(
                intent="stress",
                tool_name=RiskToolName.RUN_STRESS,
                tool_args={"scenario_id": scenario_id},
            )
        if _mentions(q, "contributor", "contributors", "dominate", "biggest risk", "top risk"):
            if _is_enqueue(q):
                return RiskQueryPlan(
                    intent="contributors",
                    tool_name=RiskToolName.GET_TOP_RISK_CONTRIBUTORS,
                )
            return RiskQueryPlan(
                intent="contributors",
                tool_name=RiskToolName.GET_CONTRIBUTORS,
            )
        if _mentions(q, "limit", "limits", "breach", "breaches"):
            return RiskQueryPlan(intent="limits", tool_name=RiskToolName.GET_LIMITS)
        if _is_enqueue(q) and _mentions(q, "portfolio risk", "risk run", "riskrun"):
            run_type = "var" if _mentions(q, "var") else "summary"
            return RiskQueryPlan(
                intent="portfolio_risk",
                tool_name=RiskToolName.RUN_PORTFOLIO_RISK,
                tool_args={"run_type": run_type},
            )
        if _mentions(q, "var", "expected shortfall") or re.search(r"\bes\b", q):
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
            "QuantLineage tools: VaR/ES, limits, contributors, worst stress, or portfolio summary.",
        )

    def answer(
        self,
        question: str,
        portfolio: Portfolio,
        service,
        *,
        principal: str | None = None,
    ) -> RiskQueryResponse:
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

        checked = validate_tool_call(plan.tool_name, plan.tool_args)
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
        return self._grounded_tool_response(
            intent=plan.intent,
            tool_name=checked.tool_name,
            portfolio=portfolio,
            service=service,
            args=checked.args,
            principal=principal,
        )

    def answer_with_model(
        self,
        question: str,
        portfolio: Portfolio,
        service,
        model: RiskAssistantModel,
        *,
        principal: str | None = None,
        assistant_context: AssistantMetadataContext | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> RiskQueryResponse:
        context = assistant_context or AssistantMetadataContext(
            provider="openai",
            model=None,
        )
        if _is_secret_request(_normalized_question(question)):
            return _ungrounded_assistant_response(
                context=context,
                mode="preflight-refused",
                fallback=False,
                answer=_SECRET_REFUSAL_ANSWER,
            )
        request = RiskAssistantModelRequest(
            question=question,
            tools=tool_contract_schemas(),
            conversation_history=list(conversation_history or []),
        )
        try:
            model_response = model.complete(request)
        except Exception as exc:
            from app.ai.errors import (
                OpenAIConfigurationError,
                OpenAIModelParseError,
                OpenAITransientProviderError,
            )

            if isinstance(exc, OpenAIConfigurationError):
                message = str(exc).strip() or "AI assistant configuration is invalid."
                return _ungrounded_assistant_response(
                    context=context,
                    mode="fallback",
                    fallback=True,
                    answer=message,
                )
            if not isinstance(exc, (OpenAITransientProviderError, OpenAIModelParseError)):
                raise
            fallback_response = self.answer(
                question, portfolio, service, principal=principal
            )
            data = dict(fallback_response.data)
            data["assistant"] = build_assistant_metadata(
                context,
                mode="fallback",
                fallback=True,
            )
            return fallback_response.model_copy(update={"data": data})
        assistant_meta = build_assistant_metadata(
            context,
            mode="model-routed",
            fallback=False,
        )
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
                    "assistant": assistant_meta,
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
                    "assistant": assistant_meta,
                },
                tool_name=None,
                requires_clarification=True,
            )

        return self._grounded_tool_response(
            intent=model_response.intent or _intent_for_tool(checked.tool_name),
            tool_name=checked.tool_name,
            portfolio=portfolio,
            service=service,
            args=checked.args,
            principal=principal,
            extra_data={"assistant": assistant_meta},
        )

    def answer_with_bounded_assistant(
        self,
        question: str,
        portfolio: Portfolio,
        service,
        model,
        *,
        max_rounds: int,
        max_tool_calls: int = 1,
        principal: str | None = None,
        assistant_context: AssistantMetadataContext | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> RiskQueryResponse:
        """Run the T21 bounded tool loop, then format a grounded HTTP response."""
        from app.ai.assistant import BoundedRiskAssistant, RiskAssistantRequest
        from app.ai.errors import (
            OpenAIConfigurationError,
            OpenAIModelParseError,
            OpenAITransientProviderError,
        )
        from app.ai.narration import format_tool_turns_deterministically

        context = assistant_context or AssistantMetadataContext(
            provider="openai",
            model=None,
        )
        if _is_secret_request(_normalized_question(question)):
            return _ungrounded_assistant_response(
                context=context,
                mode="preflight-refused",
                fallback=False,
                answer=_SECRET_REFUSAL_ANSWER,
            )

        executed: list[str] = []
        executed_turns: list[dict[str, Any]] = []

        def _execute(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
            name = RiskToolName(tool_name)
            payload = _execute_tool(
                name,
                portfolio,
                service,
                args=tool_args,
                principal=principal,
            )
            executed.append(tool_name)
            executed_turns.append(
                _investigation_turn_payload(
                    tool_name=tool_name,
                    tool_args=dict(tool_args or {}),
                    result=payload,
                    error=None,
                )
            )
            return payload

        assistant = BoundedRiskAssistant(model, _execute)
        request = RiskAssistantRequest(
            question=question,
            tools=tool_contract_schemas(),
            portfolio_id=getattr(portfolio, "id", None),
            max_rounds=max_rounds,
            max_tool_calls=max_tool_calls,
            conversation_history=list(conversation_history or []),
        )
        try:
            result = assistant.run(request)
        except OpenAIConfigurationError as exc:
            message = str(exc).strip() or "AI assistant configuration is invalid."
            return _ungrounded_assistant_response(
                context=context,
                mode="fallback",
                fallback=True,
                answer=message,
            )
        except (OpenAITransientProviderError, OpenAIModelParseError):
            if executed:
                return self._partial_bounded_response(
                    executed_tools=executed,
                    assistant_meta=build_assistant_metadata(
                        context,
                        mode="fallback",
                        fallback=True,
                    ),
                    executed_turns=executed_turns,
                )
            fallback_response = self.answer(
                question, portfolio, service, principal=principal
            )
            data = dict(fallback_response.data)
            data["assistant"] = build_assistant_metadata(
                context,
                mode="fallback",
                fallback=True,
            )
            return fallback_response.model_copy(update={"data": data})

        assistant_mode: AssistantMode = (
            "model-narrated" if result.narration_grounded else "model-routed"
        )
        assistant_meta = build_assistant_metadata(
            context,
            mode=assistant_mode,
            fallback=False,
        )
        investigation = _investigation_from_result(result)
        extra = {"assistant": assistant_meta, "investigation": investigation}

        if result.requires_clarification and not any(
            turn.tool_output for turn in result.tool_turns
        ):
            default_clarification = (
                "Please choose a deterministic risk view: VaR/ES, limits, contributors, "
                "worst stress, or portfolio summary."
            )
            return RiskQueryResponse(
                intent=result.intent
                or ("unsupported" if result.refusal else "ambiguous"),
                answer=_safe_ungrounded_text(
                    result.refusal,
                    result.clarification,
                    fallback=default_clarification,
                ),
                data={
                    "tool_contract": None,
                    "tool_result": None,
                    "supported_tools": tool_contract_schemas(),
                    **extra,
                },
                tool_name=None,
                requires_clarification=True,
            )

        last_success = next(
            (
                turn
                for turn in reversed(result.tool_turns)
                if isinstance(turn.tool_output, dict)
            ),
            None,
        )
        answer = result.proposed_answer or format_tool_turns_deterministically(
            result.tool_turns
        )
        if last_success is None:
            return RiskQueryResponse(
                intent=result.intent or "unsupported",
                answer=_safe_ungrounded_text(
                    answer,
                    result.refusal,
                    result.clarification,
                    fallback=SAFE_UNGROUNDED_ANSWER,
                ),
                data={
                    "tool_contract": None,
                    "tool_result": None,
                    "supported_tools": tool_contract_schemas(),
                    **extra,
                },
                tool_name=None,
                requires_clarification=True,
            )

        tool_name = RiskToolName(last_success.tool_name)
        payload = last_success.tool_output or {}
        card = _grounded_card(tool_name, payload)
        provenance = _grounded_provenance(card)
        if not answer:
            answer = _format_answer(tool_name, payload, card=card)
        return RiskQueryResponse(
            intent=result.intent or _intent_for_tool(tool_name),
            answer=answer,
            data={
                "tool_contract": TOOL_CONTRACTS[tool_name].model_dump(mode="json"),
                "tool_result": payload,
                "card": card,
                "provenance": provenance,
                **extra,
            },
            tool_name=tool_name.value,
        )

    def _partial_bounded_response(
        self,
        *,
        executed_tools: list[str],
        assistant_meta: dict[str, Any],
        executed_turns: list[dict[str, Any]] | None = None,
    ) -> RiskQueryResponse:
        """Stop after tools already ran; never replay a fallback router."""
        from app.api.schemas.transport import RiskQueryInvestigation

        investigation = RiskQueryInvestigation.model_validate(
            {
                "rounds_used": len(executed_tools),
                "stopped_reason": "round_limit",
                "tool_names": list(executed_tools),
                "narration_grounded": None,
                "truncated": True,
                "turns": executed_turns or [],
            }
        ).model_dump(mode="json")
        return RiskQueryResponse(
            intent="unsupported",
            answer=(
                "The investigation stopped after a provider error. "
                "Already-executed tools were not replayed."
            ),
            data={
                "tool_contract": None,
                "tool_result": None,
                "supported_tools": tool_contract_schemas(),
                "assistant": assistant_meta,
                "investigation": investigation,
            },
            tool_name=executed_tools[-1] if executed_tools else None,
            requires_clarification=True,
        )

    def _grounded_tool_response(
        self,
        *,
        intent: str,
        tool_name: RiskToolName,
        portfolio: Portfolio,
        service,
        args: dict[str, Any],
        principal: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> RiskQueryResponse:
        contract = TOOL_CONTRACTS[tool_name]
        try:
            payload = _execute_tool(
                tool_name, portfolio, service, args=args, principal=principal
            )
        except (ValueError, AttributeError, TypeError, RiskRunNotFound):
            return RiskQueryResponse(
                intent=intent,
                answer=_TOOL_FAILURE_ANSWER,
                data={
                    "tool_contract": None,
                    "tool_result": None,
                    "supported_tools": tool_contract_schemas(),
                    **(extra_data or {}),
                },
                tool_name=None,
                requires_clarification=True,
            )
        card = _grounded_card(tool_name, payload)
        provenance = _grounded_provenance(card)
        data = {
            "tool_contract": contract.model_dump(mode="json"),
            "tool_result": payload,
            "card": card,
            "provenance": provenance,
            **(extra_data or {}),
        }
        return RiskQueryResponse(
            intent=intent,
            answer=_format_answer(tool_name, payload, card=card),
            data=data,
            tool_name=tool_name.value,
        )


def _investigation_turn_payload(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    result: dict[str, Any] | None,
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    """Client-safe executed turn (no provider ids, prompts, or raw exceptions)."""
    from app.ai.narration import build_grounding_manifest

    manifest: list[dict[str, Any]] = []
    provenance: dict[str, Any] = {}
    if result is not None:
        manifest = [
            claim.model_dump(mode="json")
            for claim in build_grounding_manifest(tool_name, result)
        ]
        try:
            name = RiskToolName(str(tool_name))
        except ValueError:
            name = None
        if name is not None:
            provenance = _grounded_provenance(_grounded_card(name, result))
    return {
        "tool_name": tool_name,
        "tool_args": dict(tool_args or {}),
        "status": "error" if error else "success",
        "result": result,
        "error": error,
        "grounding_manifest": manifest,
        "provenance": provenance,
    }


def _investigation_from_result(result: Any) -> dict[str, Any]:
    """Build a client-safe investigation payload (no provider ids or CoT)."""
    from app.api.schemas.transport import RiskQueryInvestigation

    turns: list[dict[str, Any]] = []
    for turn in result.tool_turns:
        result_payload = turn.tool_output if isinstance(turn.tool_output, dict) else None
        error = None
        if turn.safe_error:
            error = dict(turn.safe_error)
        elif turn.tool_error:
            error = {
                "code": "unknown_error",
                "retryable": False,
                "message": turn.tool_error,
            }
        turns.append(
            _investigation_turn_payload(
                tool_name=turn.tool_name,
                tool_args=dict(turn.tool_args or {}),
                result=result_payload,
                error=error,
            )
        )
    payload = {
        "rounds_used": result.rounds_used,
        "stopped_reason": result.stopped_reason,
        "tool_names": [turn.tool_name for turn in result.tool_turns],
        "narration_grounded": result.narration_grounded,
        "turns": turns,
    }
    return RiskQueryInvestigation.model_validate(payload).model_dump(mode="json")


def _execute_tool(
    tool_name: RiskToolName,
    portfolio: Portfolio,
    service,
    args: dict[str, Any] | None = None,
    *,
    principal: str | None = None,
) -> dict[str, Any]:
    return execute_allowlisted_tool(
        tool_name.value,
        portfolio,
        service,
        args or {},
        principal=principal,
    )


def _nested_result_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("results") or []:
        if isinstance(item, dict) and isinstance(item.get("payload"), dict):
            rows.append(item["payload"])
    return rows


def _payload_field(payload: dict[str, Any], key: str) -> Any:
    if key in payload and payload[key] is not None:
        return payload[key]
    for nested in _nested_result_payloads(payload):
        if key in nested and nested[key] is not None:
            return nested[key]
    request = payload.get("request")
    if isinstance(request, dict) and key in request and request[key] is not None:
        return request[key]
    return None


def _payload_run_id(payload: dict[str, Any]) -> Any:
    for key in ("risk_run_id", "id", "run_id"):
        value = _payload_field(payload, key)
        if value is not None:
            return value
    return None


def _copy_present(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    card: dict[str, Any] = {}
    for key in keys:
        value = _payload_field(payload, key)
        if value is not None:
            card[key] = value
    return card


def _fill_missing_identity(card: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        if key not in card:
            card[key] = MISSING_ON_PAYLOAD
    return card


def _grounded_card(tool_name: RiskToolName, payload: dict[str, Any]) -> dict[str, Any]:
    """Copy display/provenance fields from the tool payload. Never compute risk."""
    if tool_name in (RiskToolName.EXPLAIN_RISK_CHANGE, RiskToolName.COMPARE_RISK_RUNS):
        card = _copy_present(payload, _RISK_CHANGE_CARD_KEYS)
        run_id = _payload_run_id(payload)
        if run_id is not None:
            card.setdefault("risk_run_id", run_id)
        return _fill_missing_identity(
            card,
            (
                "residual",
                "unit",
                "sign_convention",
                "risk_run_id",
                "as_of",
                "methodology",
                "market_snapshot_id",
                "historical_dataset_id",
            ),
        )

    card = _copy_present(payload, _CARD_IDENTITY_KEYS)
    run_id = _payload_run_id(payload)
    if run_id is not None:
        card["risk_run_id"] = run_id
        if payload.get("id") is not None:
            card.setdefault("id", payload["id"])
    if tool_name in _NUMERIC_TOOLS:
        _fill_missing_identity(
            card,
            (
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
            ),
        )
    return card


def _grounded_provenance(card: dict[str, Any]) -> dict[str, Any]:
    return {key: card[key] for key in _PROVENANCE_KEYS if key in card}


def _format_card_value(value: Any) -> str:
    if value == MISSING_ON_PAYLOAD:
        return MISSING_ON_PAYLOAD
    if isinstance(value, int | float) and not isinstance(value, bool):
        return _fmt(value)
    return str(value)


def _format_card_text(card: dict[str, Any]) -> str:
    labels = (
        ("metric", "metric"),
        ("value", "value"),
        ("unit", "unit"),
        ("sign_convention", "sign"),
        ("risk_run_id", "run"),
        ("as_of", "as_of"),
        ("methodology", "methodology"),
        ("market_snapshot_id", "market_snapshot_id"),
        ("historical_dataset_id", "historical_dataset_id"),
        ("historical_dataset_version", "historical_dataset_version"),
    )
    present_parts: list[str] = []
    missing = False
    for key, label in labels:
        if key not in card or isinstance(card[key], (dict, list)):
            continue
        if card[key] == MISSING_ON_PAYLOAD:
            missing = True
            continue
        present_parts.append(f"{label} {_format_card_value(card[key])}")
    if present_parts:
        if missing:
            present_parts.append(MISSING_ON_PAYLOAD)
        return "; ".join(present_parts)
    if missing:
        return MISSING_ON_PAYLOAD
    return ""


def _card_has_present_identity(card: dict[str, Any] | None) -> bool:
    if not card:
        return False
    for key in (
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
    ):
        value = card.get(key)
        if value is None or value == MISSING_ON_PAYLOAD:
            continue
        if isinstance(value, (dict, list)):
            continue
        return True
    return False


def _label_payload(payload: dict[str, Any], key: str, label: str) -> str:
    if key in payload and payload[key] is not None:
        return f"{label} {_format_card_value(payload[key])}"
    return f"{label} {MISSING_ON_PAYLOAD}"


def _format_risk_change_answer(payload: dict[str, Any]) -> str:
    parts = [
        _label_payload(payload, "metric", "Metric"),
        _label_payload(payload, "t0_run_id", "T0"),
        _label_payload(payload, "t1_run_id", "T1"),
    ]
    if "previous_risk" in payload or "current_risk" in payload:
        parts.append(
            "changed from "
            f"{_format_card_value(payload.get('previous_risk'))} to "
            f"{_format_card_value(payload.get('current_risk'))}"
        )
    parts.extend(
        [
            _label_payload(payload, "total_change", "total"),
            _label_payload(payload, "portfolio_trade_change", "portfolio/trade"),
            _label_payload(payload, "market_change", "market"),
            _label_payload(payload, "residual", "residual"),
        ]
    )
    contributor_names: list[str] = []
    for item in payload.get("factor_contributors") or []:
        if isinstance(item, dict):
            contributor_names.append(str(item.get("factor") or item.get("factor_id") or item))
    for item in payload.get("hierarchy_contributors") or []:
        if isinstance(item, dict):
            contributor_names.append(str(item.get("name") or item.get("path") or item))
    if contributor_names:
        parts.append("contributors " + ", ".join(contributor_names))
    elif "factor_contributors" in payload or "hierarchy_contributors" in payload:
        parts.append("contributors none")
    else:
        parts.append(f"contributors {MISSING_ON_PAYLOAD}")
    if "disclosed_changes" in payload:
        changes = payload.get("disclosed_changes") or []
        parts.append(
            "disclosed changes " + ", ".join(str(item) for item in changes)
            if changes
            else "disclosed changes none"
        )
    else:
        parts.append(f"disclosed changes {MISSING_ON_PAYLOAD}")
    parts.append(_label_payload(payload, "unit", "unit"))
    parts.append(_label_payload(payload, "sign_convention", "sign"))
    identity = payload.get("identity")
    if isinstance(identity, dict):
        changed = identity.get("changed_fields") or []
        if changed:
            parts.append("identity " + ", ".join(str(item) for item in changed))
    return "; ".join(parts) + "."


def _join_grounding(
    text: str,
    card: dict[str, Any] | None,
    *,
    require_present_identity: bool = False,
) -> str:
    if require_present_identity and not _card_has_present_identity(card):
        return text
    extra = _format_card_text(card or {})
    if not extra:
        return text
    base = text.rstrip()
    if not base.endswith("."):
        base += "."
    return f"{base} {extra}."


def _format_answer(
    tool_name: RiskToolName,
    payload: dict[str, Any],
    card: dict[str, Any] | None = None,
) -> str:
    if tool_name == RiskToolName.GET_PORTFOLIO_SUMMARY:
        text = (
            f"Portfolio market value is {_fmt(payload.get('market_value'))}; "
            f"99% VaR is {_fmt(payload.get('var_99'))}; "
            f"99% Expected Shortfall is {_fmt(payload.get('expected_shortfall_99'))}."
        )
        return _join_grounding(text, card, require_present_identity=True)
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
        text = "; ".join(parts) + "." if parts else "No VaR/ES methods returned."
        return _join_grounding(text, card)
    if tool_name == RiskToolName.GET_WORST_STRESS:
        scenario = payload.get("worst_scenario")
        loss = payload.get("worst_loss")
        if scenario is None:
            text = "No stress scenarios returned."
        else:
            text = f"Worst stress scenario is {scenario} with loss {_fmt(loss)}."
        return _join_grounding(text, card, require_present_identity=True)
    if tool_name == RiskToolName.GET_LIMITS:
        limits = payload.get("limits") or []
        breaches = [item for item in limits if item.get("breached")]
        text = f"{len(breaches)} limit breaches from {len(limits)} evaluated limits."
        return _join_grounding(text, card, require_present_identity=True)
    if tool_name == RiskToolName.GET_CONTRIBUTORS:
        contributors = payload.get("contributors") or []
        if not contributors:
            text = "No risk contributors returned."
        else:
            names = [
                f"{item.get('label', item.get('position_id'))} {float(item.get('contribution_pct', 0.0)):.1f}%"
                for item in contributors
            ]
            text = "Top risk contributors: " + ", ".join(names) + "."
        return _join_grounding(text, card, require_present_identity=True)
    if tool_name == RiskToolName.GET_POSITION_GREEKS:
        greek = payload.get("greek") or "delta"
        positions = payload.get("positions") or []
        if not positions:
            text = f"No position {greek} values returned."
        else:
            names = [
                f"{item.get('label', item.get('position_id'))} {_fmt(item.get('value'))}"
                for item in positions
            ]
            text = f"Top position {greek}: " + ", ".join(names) + "."
        return _join_grounding(text, card, require_present_identity=True)
    if tool_name in (
        RiskToolName.EXPLAIN_RISK_CHANGE,
        RiskToolName.COMPARE_RISK_RUNS,
    ):
        return _join_grounding(_format_risk_change_answer(payload), card)
    return _join_grounding(_format_c1_answer(tool_name, payload), card)


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
    if tool_name == RiskToolName.GET_POSITION_GREEKS:
        return "position_greeks"
    if tool_name == RiskToolName.EXPLAIN_RISK_CHANGE:
        return "explain_risk_change"
    if tool_name == RiskToolName.SEARCH_INSTRUMENTS:
        return "instrument_discovery"
    if tool_name == RiskToolName.GET_MARKET_HISTORY:
        return "history"
    if tool_name == RiskToolName.GET_DATA_QUALITY:
        return "quality"
    if tool_name == RiskToolName.RUN_PORTFOLIO_RISK:
        return "portfolio_risk"
    if tool_name == RiskToolName.COMPARE_RISK_RUNS:
        return "run_comparison"
    if tool_name == RiskToolName.RUN_STRESS:
        return "stress"
    if tool_name == RiskToolName.GET_TOP_RISK_CONTRIBUTORS:
        return "contributors"
    if tool_name == RiskToolName.GET_RUN_PROVENANCE:
        return "provenance"
    return tool_name.value


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


_RUN_ID_RE = re.compile(
    r"\b(run[-_][a-zA-Z0-9-]+|"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
    re.I,
)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_CATALOG_ID_RE = re.compile(r"\b[a-z][a-z0-9]*:[a-z]{2}:[a-z0-9._-]+\b", re.I)
_STRESS_ALIASES: tuple[tuple[str, str], ...] = (
    ("eq_down_vol_up", "eq_down_vol_up"),
    ("combined_crisis", "combined_crisis"),
    ("combined crisis", "combined_crisis"),
    ("eq_down_10", "eq_down_10"),
    ("equity-down", "eq_down_10"),
    ("equity down", "eq_down_10"),
    ("rates_up_100", "rates_up_100"),
    ("rates up", "rates_up_100"),
    ("vol_up_25", "vol_up_25"),
    ("vol up", "vol_up_25"),
)
_HISTORY_STOPWORDS = {
    "show",
    "get",
    "fetch",
    "the",
    "a",
    "an",
    "for",
    "from",
    "to",
    "and",
    "of",
    "with",
    "between",
    "market",
    "history",
    "historical",
    "price",
    "prices",
    "series",
    "range",
    "please",
    "instrument",
    "instruments",
    "start",
    "end",
    "date",
    "dates",
}

_QUALITY_STOPWORDS = _HISTORY_STOPWORDS | {
    "data",
    "quality",
    "inspect",
    "book",
    "catalog",
    "coverage",
    "flags",
    "score",
    "scores",
    "lineage",
}


def _is_advisory(question: str) -> bool:
    return _mentions(
        question,
        "should we",
        "should i",
        "recommend",
        "investment advice",
        "trading advice",
        "go to cash",
    )


def _is_instrument_discovery(question: str) -> bool:
    return bool(re.search(r"\bsearch\b", question)) or _mentions(
        question, "find instrument", "look up", "lookup"
    )


def _is_history_question(question: str) -> bool:
    return bool(re.search(r"\bhistory\b", question)) or _mentions(
        question, "price series", "historical prices"
    )


def _is_data_quality_question(question: str) -> bool:
    return _mentions(
        question,
        "data quality",
        "inspect quality",
        "series quality",
        "quality flags",
    )


def _is_compare_runs_question(question: str) -> bool:
    if not _mentions(question, "compare"):
        return False
    return _mentions(question, "runs", "risk run", "riskrun") or bool(
        re.search(r"\brun\b", question)
    )


def _is_provenance_question(question: str) -> bool:
    return _mentions(question, "provenance", "lineage")


def _is_key_rate_dv01_question(question: str) -> bool:
    return _mentions(
        question,
        "kr-dv01",
        "kr dv01",
        "kr_dv01",
        "key-rate dv01",
        "key rate dv01",
        "key_rate_dv01",
    )


def _extract_showcase_tenor(question: str) -> str | None:
    upper = question.upper()
    for tenor in ("10Y", "5Y", "2Y"):
        if tenor in upper:
            return tenor
    return None


def _is_enqueue(question: str) -> bool:
    return _mentions(question, "enqueue", "submit") or bool(re.search(r"\brun\b", question))


def _named_stress_scenario(question: str) -> str | None:
    for alias, scenario_id in _STRESS_ALIASES:
        if alias in question:
            return scenario_id
    return None


def _ambiguous_tool_pair(question: str) -> str | None:
    if _is_instrument_discovery(question) and _is_history_question(question):
        return (
            "Please choose one deterministic tool: instrument search or market history."
        )
    if _is_instrument_discovery(question) and _is_data_quality_question(question):
        return (
            "Please choose one deterministic tool: instrument search or data quality."
        )
    if _is_compare_runs_question(question) and _is_risk_change_question(question):
        return (
            "Please choose one deterministic tool: run comparison or "
            "risk-change explanation."
        )
    return None


def _extract_run_ids(question: str) -> list[str]:
    seen: list[str] = []
    for match in _RUN_ID_RE.findall(question):
        if match not in seen:
            seen.append(match)
    return seen


def _extract_iso_dates(question: str) -> list[str]:
    seen: list[str] = []
    for match in _ISO_DATE_RE.findall(question):
        if match not in seen:
            seen.append(match)
    return seen


def _extract_instrument_id(
    question: str, *, extra_stopwords: set[str] | None = None
) -> str | None:
    catalog = _CATALOG_ID_RE.findall(question)
    if catalog:
        return catalog[0]
    dates = set(_extract_iso_dates(question))
    stopwords = _HISTORY_STOPWORDS if extra_stopwords is None else extra_stopwords
    for token in re.findall(r"[a-z0-9:._-]+", question, flags=re.I):
        lowered = token.lower()
        if lowered in stopwords or token in dates:
            continue
        if _RUN_ID_RE.fullmatch(token):
            continue
        if token.isalpha() and 2 <= len(token) <= 6:
            return token.upper()
        if ":" in token:
            return token
    return None


def _extract_search_query(question: str) -> str | None:
    original = question.strip()
    lowered = original.lower()
    prefixes = (
        "search instruments for",
        "search instrument",
        "search for",
        "find instrument",
        "look up",
        "lookup",
        "search",
    )
    rest = None
    for prefix in prefixes:
        if lowered.startswith(prefix) or f" {prefix} " in f" {lowered} ":
            idx = lowered.find(prefix)
            rest = original[idx + len(prefix) :].strip(" ?.")
            break
    if rest is None:
        return None
    rest = re.sub(r"^(instruments?|catalog|for)\s+", "", rest, flags=re.I)
    rest = re.split(r"\band\b", rest, maxsplit=1, flags=re.I)[0].strip(" ?.")
    return rest or None


def _plan_for_two_run_ids(
    *,
    intent: str,
    tool_name: RiskToolName,
    question: str,
    missing: str,
) -> RiskQueryPlan:
    run_ids = _extract_run_ids(question)
    if len(run_ids) < 2:
        return _clarification_plan(intent, missing, tool_name=tool_name)
    return RiskQueryPlan(
        intent=intent,
        tool_name=tool_name,
        tool_args={"t0_run_id": run_ids[0], "t1_run_id": run_ids[1]},
    )


def _is_risk_change_question(question: str) -> bool:
    if not _mentions(question, "why", "explain"):
        return False
    if not _mentions(question, "var", "risk", "es", "expected shortfall", "dv01", "vega"):
        return False
    return _mentions(question, "change", "increase", "decrease", "moved", "up", "down")


def _is_prompt_injection(question: str) -> bool:
    return any(marker in question for marker in _INJECTION_MARKERS)


def _is_fake_tool_request(question: str) -> bool:
    return any(marker in question for marker in _FAKE_TOOL_MARKERS)


def _is_secret_request(question: str) -> bool:
    return any(marker in question for marker in _SECRET_REQUEST_MARKERS)


def _is_greeks_question(question: str) -> bool:
    """True when the user asks for position Greeks (delta/gamma/vega/…)."""
    if _mentions(question, "greeks", "greek"):
        return True
    if not re.search(r"\b(delta|gamma|vega|theta|rho)\b", question, re.I):
        return False
    # Keep explain-risk-change paths that mention a greek metric name.
    return not _is_risk_change_question(question)


def _infer_position_greek(question: str) -> str | None:
    """Map NL Greek asks onto Valuation fields. Theta/rho are not on Valuation."""
    if re.search(r"\btheta\b", question, re.I) or re.search(r"\brho\b", question, re.I):
        return None
    if re.search(r"\bgamma\b", question, re.I):
        return "gamma"
    if re.search(r"\bvega\b", question, re.I):
        return "vega"
    if re.search(r"\bdv01\b", question, re.I):
        return "dv01"
    if re.search(r"\bfx[_\s-]?delta\b", question, re.I):
        return "fx_delta"
    return "delta"


def _position_greeks_tool_args(question: str, greek: str) -> dict[str, Any]:
    args: dict[str, Any] = {"greek": greek}
    if re.search(r"\boptions?\b", question, re.I):
        args["options_only"] = True
    return args


def _tool_args_oversized(args: dict[str, Any] | None) -> bool:
    if not args:
        return False
    stack: list[Any] = [args]
    while stack:
        current = stack.pop()
        if isinstance(current, str) and len(current) > TOOL_ARG_MAX_CHARS:
            return True
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list | tuple):
            stack.extend(current)
    return False


def _contains_secret_leak(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in _SECRET_REQUEST_MARKERS):
        return True
    for env_name in _SECRET_ENV_NAMES:
        value = os.environ.get(env_name)
        if value and value in text:
            return True
    return False


def _contains_ungrounded_number(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _safe_ungrounded_text(*candidates: str | None, fallback: str) -> str:
    for text in candidates:
        if (
            text
            and not _contains_ungrounded_number(text)
            and not _contains_secret_leak(text)
        ):
            return text
    if (
        fallback
        and not _contains_ungrounded_number(fallback)
        and not _contains_secret_leak(fallback)
    ):
        return fallback
    return SAFE_UNGROUNDED_ANSWER


def _clarification_plan(
    intent: str,
    message: str,
    tool_name: RiskToolName | None = None,
) -> RiskQueryPlan:
    return RiskQueryPlan(
        intent=intent,
        tool_name=tool_name,
        needs_clarification=True,
        clarification=message,
    )
