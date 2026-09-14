"""Wave C G1 — allowlisted tool argument schemas mapped to existing services.

No MCP. No pricing-library or VaR/stress/DV01 formulas. Numeric tools prefer
RiskRun identity. ``compare_risk_runs`` and ``explain_risk_change`` share
``compare_runs``. ``get_market_history`` is instrument levels, not Wave B
historical-analytics.
"""

from __future__ import annotations

import inspect
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models import RiskChangeMetric

# Must match ``app.api.instruments.MAX_HISTORY_RANGE_DAYS`` (HTTP 400 oversize).
HISTORY_MAX_RANGE_DAYS = 1826
# Single-field cap so huge blobs fail ``validate_tool_call`` (C6).
TOOL_ARG_MAX_CHARS = 4096

AllowlistedStressScenario = Literal[
    "eq_down_10",
    "rates_up_100",
    "vol_up_25",
    "eq_down_vol_up",
    "combined_crisis",
]

ShowcaseTenor = Literal["2Y", "5Y", "10Y"]


class SearchInstrumentsArgs(BaseModel):
    """Maps to ``search_catalog(query)`` / ``GET /api/v1/instruments/search``."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=TOOL_ARG_MAX_CHARS)


class GetMarketHistoryArgs(BaseModel):
    """Instrument level history. Not Wave B ``POST /risk/historical-analytics``."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(min_length=1, max_length=TOOL_ARG_MAX_CHARS)
    start: date
    end: date

    @model_validator(mode="after")
    def _http_date_bounds(self) -> GetMarketHistoryArgs:
        if self.start > self.end:
            raise ValueError("start must be on or before end")
        if (self.end - self.start).days > HISTORY_MAX_RANGE_DAYS:
            raise ValueError(f"Date range exceeds {HISTORY_MAX_RANGE_DAYS} days")
        return self


class GetDataQualityArgs(BaseModel):
    """Same date parse as history, without the 1826-day cap."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(min_length=1, max_length=TOOL_ARG_MAX_CHARS)
    start: date
    end: date

    @model_validator(mode="after")
    def _order(self) -> GetDataQualityArgs:
        if self.start > self.end:
            raise ValueError("start must be on or before end")
        return self


class RunPortfolioRiskArgs(BaseModel):
    """Enqueue a RiskRun (``summary`` / ``var``). Portfolio is bound by QuantLineage."""

    model_config = ConfigDict(extra="forbid")

    run_type: Literal["summary", "var"] = "summary"
    market_snapshot_id: str | None = Field(default=None, max_length=TOOL_ARG_MAX_CHARS)


class GetRiskRunArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=TOOL_ARG_MAX_CHARS)


class CompareRiskRunsArgs(BaseModel):
    """Shared args for ``compare_risk_runs`` and ``explain_risk_change``."""

    model_config = ConfigDict(extra="forbid")

    t0_run_id: str = Field(min_length=1, max_length=TOOL_ARG_MAX_CHARS)
    t1_run_id: str = Field(min_length=1, max_length=TOOL_ARG_MAX_CHARS)
    metric: RiskChangeMetric = "var_99"


class RunStressArgs(BaseModel):
    """Allowlisted named DEFAULT_SCENARIOS only — no arbitrary shocks."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: AllowlistedStressScenario = "eq_down_10"
    market_snapshot_id: str | None = Field(default=None, max_length=TOOL_ARG_MAX_CHARS)


class GetKeyRateDv01Args(BaseModel):
    """Demo rates-showcase KR-DV01; optional tenor filter (C7: 10Y)."""

    model_config = ConfigDict(extra="forbid")

    tenor: ShowcaseTenor | None = None


class GetTopRiskContributorsArgs(BaseModel):
    """Prefer RiskRun ``run_type=contributors``. Ranking math is unchanged.

    Truncation is not a tool arg: the contributors RiskRun request blob cannot
    carry ``top_n`` (RF-019 still slices the sync dump to 5).
    """

    model_config = ConfigDict(extra="forbid")


class GetRunProvenanceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=TOOL_ARG_MAX_CHARS)


C1_ARG_MODELS: dict[str, type[BaseModel]] = {
    "search_instruments": SearchInstrumentsArgs,
    "get_market_history": GetMarketHistoryArgs,
    "get_data_quality": GetDataQualityArgs,
    "run_portfolio_risk": RunPortfolioRiskArgs,
    "get_risk_run": GetRiskRunArgs,
    "compare_risk_runs": CompareRiskRunsArgs,
    "explain_risk_change": CompareRiskRunsArgs,
    "run_stress": RunStressArgs,
    "get_key_rate_dv01": GetKeyRateDv01Args,
    "get_top_risk_contributors": GetTopRiskContributorsArgs,
    "get_run_provenance": GetRunProvenanceArgs,
}


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(value, dict):
        return dict(value)
    return dict(value)


def _compare_runs_fn(service: Any):
    compare = getattr(service, "compare_runs", None)
    if callable(compare):
        return compare
    return service.explain_risk_change


def _require_submit(service: Any):
    submit = getattr(service, "submit", None)
    if not callable(submit):
        raise ValueError("RiskRun submit is not configured")
    return submit


def _supported_kwargs(fn: Any, **kwargs: Any) -> dict[str, Any]:
    """Pass only kwargs the callable declares (C2 principal plumbing)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    if any(item.kind == inspect.Parameter.VAR_KEYWORD for item in params.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in params}


def _call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    return fn(*args, **_supported_kwargs(fn, **kwargs))


def execute_allowlisted_tool(
    tool_name: str,
    portfolio: Any,
    service: Any,
    args: dict[str, Any] | None = None,
    *,
    principal: str | None = None,
) -> dict[str, Any]:
    """Dispatch allowlisted tools to existing service methods. No risk arithmetic here."""
    args = args or {}
    if tool_name == "search_instruments":
        search = getattr(service, "search_catalog", None)
        if callable(search):
            result = search(args["query"])
        else:
            from app.market.catalog.service import search_catalog

            result = search_catalog(args["query"])
        if hasattr(result, "hits"):
            hits = result.hits
        elif isinstance(result, dict) and "hits" in result:
            hits = result["hits"]
        else:
            hits = result
        return {"hits": [_dump(item) for item in hits]}
    if tool_name == "get_market_history":
        fetch = getattr(service, "get_market_history", None)
        if not callable(fetch):
            raise ValueError("market history service is not configured")
        return _dump(fetch(args["instrument_id"], args["start"], args["end"]))
    if tool_name == "get_data_quality":
        fetch = getattr(service, "get_data_quality", None)
        if not callable(fetch):
            raise ValueError("data quality service is not configured")
        return _dump(fetch(args["instrument_id"], args["start"], args["end"]))
    if tool_name == "run_portfolio_risk":
        submit = _require_submit(service)
        return _dump(
            _call(
                submit,
                portfolio=portfolio,
                run_type=args.get("run_type", "summary"),
                request={},
                market_snapshot_id=args.get("market_snapshot_id"),
                owner=principal,
            )
        )
    if tool_name == "get_risk_run":
        getter = getattr(service, "get", None)
        if not callable(getter):
            raise ValueError("RiskRun get is not configured")
        return _dump(_call(getter, args["run_id"], principal=principal))
    if tool_name in {"compare_risk_runs", "explain_risk_change"}:
        compare = _compare_runs_fn(service)
        return _dump(
            _call(
                compare,
                args["t0_run_id"],
                args["t1_run_id"],
                metric=args.get("metric", "var_99"),
                principal=principal,
            )
        )
    if tool_name == "run_stress":
        submit = _require_submit(service)
        return _dump(
            _call(
                submit,
                portfolio=portfolio,
                run_type="stress",
                request={"scenario_id": args["scenario_id"]},
                market_snapshot_id=args.get("market_snapshot_id"),
                owner=principal,
            )
        )
    if tool_name == "get_key_rate_dv01":
        showcase = getattr(service, "build_rates_showcase", None)
        if not callable(showcase):
            raise ValueError("rates showcase is not configured")
        payload = _dump(showcase())
        tenor = args.get("tenor")
        if tenor:
            rows = [
                row
                for row in payload.get("key_rate_dv01") or []
                if row.get("tenor") == tenor
            ]
            payload = {**payload, "key_rate_dv01": rows}
        return payload
    if tool_name == "get_top_risk_contributors":
        submit = _require_submit(service)
        return _dump(
            _call(
                submit,
                portfolio=portfolio,
                run_type="contributors",
                request={},
                owner=principal,
            )
        )
    if tool_name == "get_run_provenance":
        fetch = getattr(service, "get_run_provenance", None)
        if not callable(fetch):
            raise ValueError("run provenance service is not configured")
        return _dump(_call(fetch, args["run_id"], principal=principal))
    if tool_name == "get_portfolio_summary":
        return _dump(service.summary(portfolio))
    if tool_name == "get_var_es":
        return _dump(service.var_report(portfolio))
    if tool_name == "get_worst_stress":
        return _dump(service.threat_evaluation(portfolio))
    if tool_name == "get_limits":
        return {"limits": [_dump(item) for item in service.limits(portfolio)]}
    if tool_name == "get_contributors":
        return {"contributors": [_dump(item) for item in service.contributors(portfolio)[:5]]}
    raise ValueError(f"unsupported risk tool: {tool_name}")
