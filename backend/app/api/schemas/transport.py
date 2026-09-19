"""HTTP request/response bodies (R0.9.1 / RF-010).

Domain entities stay in ``app.domain.models``. This module owns API wire
shapes so versioned schemas can change without editing domain types.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.api.scenario_wire import ScenarioWire
from app.domain.models import (
    AsOf,
    AsOfLabel,
    FiniteFloat,
    FiniteInputMixin,
    HierarchyRef,
    LimitMetric,
    MarketSnapshot,
    Portfolio,
    RiskLimit,
    RiskRun,
    RiskRunCalculationConfig,
    RiskRunStatus,
    StressScenario,
    VaRMethodology,
    as_of_wire,
)


class CustomStressRequest(FiniteInputMixin):
    portfolio: Portfolio
    scenarios: list[StressScenario]


class ReverseStressRequest(FiniteInputMixin):
    portfolio: Portfolio
    target_loss_pct: FiniteFloat = Field(gt=0)
    factor: Literal["equity", "rates", "vol", "fx"] = "equity"
    max_shock: FiniteFloat = Field(default=0.80, gt=0)


class MultiFactorReverseStressRequest(FiniteInputMixin):
    """Constrained multi-factor reverse stress (M3.6)."""

    portfolio: Portfolio
    target_loss_pct: FiniteFloat = Field(gt=0)
    factors: list[Literal["equity", "rates", "vol", "fx"]] | None = None
    weights: dict[str, FiniteFloat] | None = None
    max_shocks: dict[str, FiniteFloat] | None = None
    max_shock: FiniteFloat = Field(default=0.80, gt=0)


class ScenarioComparisonRequest(FiniteInputMixin):
    portfolio: Portfolio
    hedged_portfolio: Portfolio
    scenarios: list[StressScenario]
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA


class LimitDrilldownRequest(FiniteInputMixin):
    """Drill into limit utilization at a hierarchy node (M4.6).

    When ``metric`` is set, that metric is returned even if not breached
    (unless ``breaches_only`` is true). When omitted, items follow
    ``breaches_only`` against evaluated limits at the node.
    """

    portfolio: Portfolio
    metric: LimitMetric | None = None
    hierarchy: HierarchyRef | None = None
    limits: list[RiskLimit] | None = None
    top_n: int = Field(default=5, ge=1, le=100)
    breaches_only: bool = True


class RiskQueryRequest(FiniteInputMixin):
    portfolio: Portfolio
    question: str


class RiskQueryAssistantMetadata(BaseModel):
    """Optional provider state for risk-query responses (no secrets or prompts)."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["deterministic", "openai"]
    model: str | None = None
    mode: Literal["model-routed", "deterministic", "fallback"]
    fallback: bool


class RiskQueryResponse(BaseModel):
    intent: str
    answer: str
    data: dict[str, Any]
    tool_name: str | None = None
    requires_clarification: bool = False

    @field_validator("data")
    @classmethod
    def _validate_assistant_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        assistant = value.get("assistant")
        if assistant is not None:
            RiskQueryAssistantMetadata.model_validate(assistant)
        return value


class RiskRunRequestBody(BaseModel):
    """Shared typed calculation knobs for RiskRun ``request`` blobs (R0.8.4).

    Unknown keys are rejected. Per-``run_type`` aliases below share this shape;
    ``summary`` / ``var`` / ``dashboard`` use methodology; interactive HEAVY UI
    types add typed fields (scenarios, reverse knobs, attribution books, …).
    """

    model_config = ConfigDict(extra="forbid")

    methodology: VaRMethodology | None = None
    historical_dataset_id: str | None = Field(default=None, min_length=1)
    historical_dataset_version: str | None = Field(default=None, min_length=1)
    as_of: AsOf | None = None
    calculation_config: RiskRunCalculationConfig | None = None

    @field_serializer("as_of")
    def _ser_as_of(self, value: date | AsOfLabel | None) -> str | None:
        if value is None:
            return None
        return as_of_wire(value)


class SummaryRiskRunRequest(RiskRunRequestBody):
    """Typed request body for ``run_type=summary``."""


class VarRiskRunRequest(RiskRunRequestBody):
    """Typed request body for ``run_type=var``."""


class DashboardRiskRunRequest(RiskRunRequestBody):
    """Typed request body for ``run_type=dashboard``."""


class GenericRiskRunRequest(RiskRunRequestBody):
    """Typed envelope for supported run types that ignore most request knobs."""


class StressRunRequest(RiskRunRequestBody):
    """``run_type=stress`` — optional allowlisted ``DEFAULT_SCENARIOS`` id.

    Omitted ``scenario_id`` keeps the existing full default library. Unknown ids
    fail at execute time against that library (no custom shocks).
    """

    scenario_id: str | None = None


def _coerce_scenario_wires(value: Any) -> list[Any]:
    """Validate formal Scenario wire dicts."""
    if not isinstance(value, list):
        raise ValueError("scenarios must be a list")
    return [ScenarioWire.model_validate(item) for item in value]


class StressEvaluateRiskRunRequest(RiskRunRequestBody):
    """``run_type=stress_evaluate`` — formal Scenario wire list (UI evaluate)."""

    scenarios: list[Any] = Field(min_length=1)

    @field_validator("scenarios", mode="before")
    @classmethod
    def _scenarios_wire(cls, value: Any) -> list[Any]:
        return _coerce_scenario_wires(value)


class ReverseStressRiskRunRequest(RiskRunRequestBody):
    """``run_type=reverse_stress`` — single-factor reverse stress knobs."""

    target_loss_pct: FiniteFloat = Field(gt=0)
    factor: Literal["equity", "rates", "vol", "fx"] = "equity"
    max_shock: FiniteFloat = Field(default=0.80, gt=0)


class ReverseStressMultiRiskRunRequest(RiskRunRequestBody):
    """``run_type=reverse_stress_multi`` — multi-factor reverse stress knobs."""

    target_loss_pct: FiniteFloat = Field(gt=0)
    factors: list[Literal["equity", "rates", "vol", "fx"]] | None = None
    weights: dict[str, FiniteFloat] | None = None
    max_shocks: dict[str, FiniteFloat] | None = None
    max_shock: FiniteFloat = Field(default=0.80, gt=0)


class StressCompareRiskRunRequest(RiskRunRequestBody):
    """``run_type=stress_compare`` — hedge compare with formal Scenario wires."""

    hedged_portfolio: Portfolio
    scenarios: list[Any] = Field(min_length=1)

    @field_validator("scenarios", mode="before")
    @classmethod
    def _scenarios_wire(cls, value: Any) -> list[Any]:
        return _coerce_scenario_wires(value)


class QueryRiskRunRequest(RiskRunRequestBody):
    """``run_type=query`` — NL risk query question."""

    question: str = Field(min_length=1)


class AttributionRiskRunRequest(RiskRunRequestBody):
    """``run_type=attribution`` — P&L explain previous/current books."""

    previous_portfolio: Portfolio
    current_portfolio: Portfolio
    previous_market: MarketSnapshot | None = None
    current_market: MarketSnapshot | None = None
    dt_years: FiniteFloat = 0.0


class ChangeAttributionRiskRunRequest(RiskRunRequestBody):
    """``run_type=change_attribution`` — risk-metric change waterfall."""

    previous_portfolio: Portfolio
    current_portfolio: Portfolio
    previous_market: MarketSnapshot | None = None
    current_market: MarketSnapshot | None = None
    metric: Literal["var_99", "var_95", "expected_shortfall_99"] = "var_99"


class EsRiskRunRequest(RiskRunRequestBody):
    """``run_type=es`` — Expected Shortfall contributions (methodology on base)."""


class VarCompareRiskRunRequest(RiskRunRequestBody):
    """``run_type=var_compare`` — side-by-side VaR methodologies."""

    observations: int | None = Field(default=None, ge=1, le=5000)


class AttributionDemoRiskRunRequest(RiskRunRequestBody):
    """``run_type=attribution_demo`` — illustrative market-move attribution."""


RISK_RUN_REQUEST_SCHEMAS: Mapping[str, type[RiskRunRequestBody]] = MappingProxyType(
    {
        "summary": SummaryRiskRunRequest,
        "var": VarRiskRunRequest,
        "dashboard": DashboardRiskRunRequest,
        "stress": StressRunRequest,
        "factors": GenericRiskRunRequest,
        "limits": GenericRiskRunRequest,
        "hierarchy": GenericRiskRunRequest,
        "contributors": GenericRiskRunRequest,
        "stress_evaluate": StressEvaluateRiskRunRequest,
        "reverse_stress": ReverseStressRiskRunRequest,
        "reverse_stress_multi": ReverseStressMultiRiskRunRequest,
        "stress_compare": StressCompareRiskRunRequest,
        "query": QueryRiskRunRequest,
        "attribution": AttributionRiskRunRequest,
        "attribution_demo": AttributionDemoRiskRunRequest,
        "change_attribution": ChangeAttributionRiskRunRequest,
        "es": EsRiskRunRequest,
        "var_compare": VarCompareRiskRunRequest,
    }
)


def parse_risk_run_request(
    run_type: str,
    request: Mapping[str, Any] | RiskRunRequestBody | None = None,
) -> RiskRunRequestBody:
    """Validate a RiskRun request blob for ``run_type`` (extra='forbid').

    Unsupported ``run_type`` values are left to the worker (400); when a schema
    exists, free-form dicts are rejected.
    """
    if isinstance(request, RiskRunRequestBody):
        typed = request
        schema = RISK_RUN_REQUEST_SCHEMAS.get((run_type or "summary").strip())
        if schema is not None and type(typed) is not schema and not isinstance(typed, schema):
            typed = schema.model_validate(typed.model_dump(mode="python"))
        return typed
    schema = RISK_RUN_REQUEST_SCHEMAS.get((run_type or "summary").strip())
    if schema is None:
        # Unknown run_type: still forbid free-form via the shared body when the
        # caller asked to parse; worker rejects the type separately.
        schema = RiskRunRequestBody
    raw: Mapping[str, Any] = {} if request is None else request
    return schema.model_validate(dict(raw))


def dump_risk_run_request(body: RiskRunRequestBody) -> dict[str, Any]:
    """JSON-compatible request dict for persistence / worker execution."""
    return body.model_dump(mode="json", exclude_none=True)


class RiskRunCompareRequest(FiniteInputMixin):
    """POST /risk/runs/compare — flagship two-RiskRun explain (Stage 10.2)."""

    model_config = ConfigDict(extra="forbid")

    t0_run_id: str = Field(min_length=1)
    t1_run_id: str = Field(min_length=1)
    metric: Literal[
        "var_99",
        "var_95",
        "expected_shortfall_99",
        "dv01",
        "vega",
        "stress",
    ] = "var_99"


class RiskRunCreateRequest(FiniteInputMixin):
    """POST /risk/runs body (M5.4). Mounted under ``/risk`` until M7.2 ``/api/v1``."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "portfolio": {
                        "id": "demo",
                        "name": "Demo",
                        "positions": [
                            {
                                "type": "equity",
                                "id": "eq-1",
                                "symbol": "AAPL",
                                "quantity": 10,
                                "price": 100.0,
                            }
                        ],
                    },
                    "run_type": "summary",
                    "request": {"methodology": "DELTA_GAMMA"},
                    "market_snapshot_id": None,
                }
            ]
        },
    )

    portfolio: Portfolio
    run_type: str = Field(default="summary", min_length=1)
    request: dict[str, Any] = Field(default_factory=dict)
    market_snapshot_id: str | None = None

    @model_validator(mode="after")
    def _validate_typed_request(self) -> RiskRunCreateRequest:
        typed = parse_risk_run_request(self.run_type, self.request)
        self.request = dump_risk_run_request(typed)
        return self


class RiskRunProvenance(BaseModel):
    """Stable calculation-lineage payload for one RiskRun (Stage 10.5).

    Fields are copied from the persisted run. ``release_sha`` is omitted when
    unknown (None) rather than faked. No secrets.
    """

    model_config = ConfigDict(extra="forbid")

    risk_run_id: str
    portfolio_id: str
    portfolio_version: int | None = None
    market_snapshot_id: str | None = None
    as_of: str | None = None
    historical_dataset_id: str | None = None
    historical_dataset_version: str | None = None
    data_source_label: str | None = None
    pricing_engine_version: str | None = None
    methodology: str | None = None
    scenario_set: list[str] = Field(default_factory=list)
    scenario_set_version: str | None = None
    calculation_config: RiskRunCalculationConfig | None = None
    duration_seconds: float | None = None
    status: RiskRunStatus
    release_sha: str | None = None

    @classmethod
    def from_risk_run(
        cls,
        run: RiskRun,
        *,
        duration_seconds: float | None = None,
    ) -> RiskRunProvenance:
        from app.api.provenance import provenance_from_risk_run

        return cls.model_validate(
            provenance_from_risk_run(run, duration_seconds=duration_seconds)
        )


class CurveNodeView(BaseModel):
    """One showcase curve pillar (display; zeros come from the snapshot)."""

    model_config = ConfigDict(extra="forbid")

    tenor: str
    years: float
    zero_rate: float


class RatesCurveView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    currency: str
    curve_type: str
    nodes: list[CurveNodeView] = Field(default_factory=list)
    limitations: str


class KeyRateDv01View(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenor: str
    factor: str
    value: float
    unit: str
    method: str


class RatesShowcaseView(BaseModel):
    """GET /market/rates-showcase — curve nodes + KR-DV01 from SensitivityEngine."""

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str
    market_snapshot_id: str
    conventions: dict[str, str]
    discount_curve: RatesCurveView
    projection_curve: RatesCurveView | None = None
    parallel_dv01: float
    key_rate_dv01: list[KeyRateDv01View] = Field(default_factory=list)


class RiskRunResultView(BaseModel):
    """Named result payload attached to a risk run."""

    model_config = ConfigDict(extra="forbid")

    result_type: str
    payload: dict[str, Any]


class RiskRunView(BaseModel):
    """API view of a risk run (wire shape for M5.3/M5.4).

    Maps from domain ``RiskRun``:
    - ``error_message`` ← ``error``
    - ``finished_at`` ← ``completed_at``
    - ``duration_seconds`` ← ``duration``
    - ``results`` ← ``result_refs`` (+ optional payloads from persistence)
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "portfolio_id": "demo",
                    "portfolio_version": 1,
                    "market_snapshot_id": None,
                    "status": "QUEUED",
                    "run_type": "summary",
                    "request": {"methodology": "DELTA_GAMMA"},
                    "pricing_engine_version": None,
                    "methodology": None,
                    "scenario_set": [],
                    "historical_dataset_id": None,
                    "historical_dataset_version": None,
                    "as_of": None,
                    "calculation_config": None,
                    "error_message": None,
                    "created_at": "2026-09-02T17:00:00+00:00",
                    "started_at": None,
                    "finished_at": None,
                    "duration_seconds": None,
                    "results": [],
                }
            ]
        },
    )

    id: str
    portfolio_id: str
    portfolio_version: int | None = None
    market_snapshot_id: str | None = None
    status: RiskRunStatus
    run_type: str
    request: dict[str, Any] = Field(default_factory=dict)
    pricing_engine_version: str | None = None
    methodology: VaRMethodology | None = None
    scenario_set: list[str] = Field(default_factory=list)
    historical_dataset_id: str | None = None
    historical_dataset_version: str | None = None
    as_of: str | None = None
    calculation_config: RiskRunCalculationConfig | None = None
    error_message: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    results: list[RiskRunResultView] = Field(default_factory=list)
    provenance: RiskRunProvenance | None = None

    @classmethod
    def from_risk_run(
        cls,
        run: RiskRun,
        *,
        payloads: dict[str, dict[str, Any]] | None = None,
    ) -> RiskRunView:
        """Build wire view from domain DTO; attach payloads when provided."""
        payload_map = payloads or {}
        results: list[RiskRunResultView] = []
        if payload_map:
            for result_type, payload in payload_map.items():
                results.append(RiskRunResultView(result_type=result_type, payload=payload))
        else:
            for ref in run.result_refs:
                results.append(
                    RiskRunResultView(
                        result_type=ref.result_type,
                        payload={},
                    )
                )
        return cls(
            id=run.id,
            portfolio_id=run.portfolio_id,
            portfolio_version=run.portfolio_version,
            market_snapshot_id=run.market_snapshot_id,
            status=run.status,
            run_type=run.run_type,
            request=dict(run.request),
            pricing_engine_version=run.pricing_engine_version,
            methodology=run.methodology,
            scenario_set=list(run.scenario_set),
            historical_dataset_id=run.historical_dataset_id,
            historical_dataset_version=run.historical_dataset_version,
            as_of=as_of_wire(run.as_of) if run.as_of is not None else None,
            calculation_config=run.calculation_config,
            error_message=run.error,
            created_at=run.created_at.isoformat() if run.created_at else None,
            started_at=run.started_at.isoformat() if run.started_at else None,
            finished_at=run.completed_at.isoformat() if run.completed_at else None,
            duration_seconds=run.duration,
            results=results,
            provenance=RiskRunProvenance.from_risk_run(run),
        )
