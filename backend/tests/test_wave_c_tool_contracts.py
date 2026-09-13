"""Wave C G1 — allowlisted deterministic tool contracts mapped to existing services."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from tests.test_ai_query_orchestration import (
    _FixturePayload,
    _FixtureService,
    _ScriptedModel,
)

from app.api.instruments import MAX_HISTORY_RANGE_DAYS
from app.domain.models import RiskChangeMetric
from app.risk.query import (
    TOOL_CONTRACTS,
    RiskAssistantModelResponse,
    RiskQueryEngine,
    RiskToolName,
    tool_contract_schemas,
    tool_json_schemas,
    validate_tool_call,
)
from app.risk.stress import DEFAULT_SCENARIOS
from app.sample import SAMPLE_PORTFOLIO

C1_MINIMUM_TOOLS = {
    "search_instruments",
    "get_market_history",
    "get_data_quality",
    "run_portfolio_risk",
    "get_risk_run",
    "compare_risk_runs",
    "explain_risk_change",
    "run_stress",
    "get_key_rate_dv01",
    "get_top_risk_contributors",
}

RF019_KEPT_TOOLS = {
    "get_portfolio_summary",
    "get_var_es",
    "get_worst_stress",
    "get_limits",
    "get_contributors",
}

_QUERY_AND_TOOL_MODULES = (
    Path(__file__).resolve().parents[1] / "app" / "risk" / "query.py",
    Path(__file__).resolve().parents[1] / "app" / "risk" / "tool_contracts.py",
)


def test_c1_allowlist_includes_minimum_tools_and_rf019() -> None:
    names = {item["name"] for item in tool_contract_schemas()}
    schemas = tool_json_schemas()

    assert names >= C1_MINIMUM_TOOLS
    assert names >= RF019_KEPT_TOOLS
    assert set(schemas) == names == {tool.value for tool in RiskToolName}
    assert set(TOOL_CONTRACTS) == set(RiskToolName)
    for schema in schemas.values():
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False


def test_c1_unknown_tool_and_extra_keys_are_refused() -> None:
    unknown = validate_tool_call("invent_var", {})
    assert not unknown.allowed
    assert unknown.tool_name is None
    assert "allowlist" in (unknown.refusal or "").lower()

    extra = validate_tool_call("get_limits", {"invented_var": 999})
    assert not extra.allowed
    extra_history = validate_tool_call(
        "get_market_history",
        {
            "instrument_id": "equity:US:AAPL",
            "start": "2020-01-01",
            "end": "2020-01-31",
            "returns": True,
        },
    )
    assert not extra_history.allowed


def test_c1_explain_risk_change_metric_is_risk_change_metric_literal() -> None:
    schema = tool_json_schemas()["explain_risk_change"]
    metric = schema["properties"]["metric"]
    allowed = set(metric.get("enum") or [])
    assert allowed == set(RiskChangeMetric.__args__)

    ok = validate_tool_call(
        "explain_risk_change",
        {"t0_run_id": "run-t0", "t1_run_id": "run-t1", "metric": "expected_shortfall_99"},
    )
    assert ok.allowed
    refused = validate_tool_call(
        "explain_risk_change",
        {"t0_run_id": "run-t0", "t1_run_id": "run-t1", "metric": "not_a_metric"},
    )
    assert not refused.allowed
    compare_refused = validate_tool_call(
        "compare_risk_runs",
        {"t0_run_id": "run-t0", "t1_run_id": "run-t1", "metric": "fake_var"},
    )
    assert not compare_refused.allowed


def test_c1_get_market_history_is_not_historical_analytics() -> None:
    contract = TOOL_CONTRACTS[RiskToolName.GET_MARKET_HISTORY]
    http_path = contract.http_path.lower()
    assert "historical-analytics" not in http_path
    assert "historical_analytics" not in contract.service_method
    assert "historical_analytics" not in contract.numeric_source.lower()
    assert "/api/v1/market/history" in contract.http_path

    service = _HistoryGuardService()
    engine = RiskQueryEngine()
    model = _ScriptedModel(
        RiskAssistantModelResponse(
            tool_name=RiskToolName.GET_MARKET_HISTORY,
            tool_args={
                "instrument_id": "equity:US:AAPL",
                "start": "2024-01-01",
                "end": "2024-01-31",
            },
            intent="history",
        )
    )
    response = engine.answer_with_model(
        "Show AAPL history", SAMPLE_PORTFOLIO, service, model
    )
    assert "historical_analytics" not in service.calls
    assert response.tool_name == "get_market_history"
    assert response.data["tool_result"]["instrument_id"] == "equity:US:AAPL"
    assert "points" in response.data["tool_result"]


def test_c1_history_date_bounds_match_http_cap_and_inverted_range() -> None:
    from app.risk.tool_contracts import HISTORY_MAX_RANGE_DAYS

    assert HISTORY_MAX_RANGE_DAYS == MAX_HISTORY_RANGE_DAYS == 1826
    start = date(2018, 1, 1)
    over = start + timedelta(days=1827)
    inverted = validate_tool_call(
        "get_market_history",
        {
            "instrument_id": "equity:US:AAPL",
            "start": "2020-01-02",
            "end": "2020-01-01",
        },
    )
    assert not inverted.allowed
    oversized = validate_tool_call(
        "get_market_history",
        {
            "instrument_id": "equity:US:AAPL",
            "start": start.isoformat(),
            "end": over.isoformat(),
        },
    )
    assert not oversized.allowed
    ok = validate_tool_call(
        "get_market_history",
        {
            "instrument_id": "equity:US:AAPL",
            "start": "2024-01-01",
            "end": "2024-01-31",
        },
    )
    assert ok.allowed
    quality_wide = validate_tool_call(
        "get_data_quality",
        {
            "instrument_id": "equity:US:AAPL",
            "start": start.isoformat(),
            "end": over.isoformat(),
        },
    )
    assert quality_wide.allowed


def test_c1_search_instruments_uses_search_catalog_query_arg() -> None:
    schema = tool_json_schemas()["search_instruments"]
    assert "query" in schema["properties"]
    assert "q" not in schema["properties"]
    assert "query" in (schema.get("required") or [])
    contract = TOOL_CONTRACTS[RiskToolName.SEARCH_INSTRUMENTS]
    assert contract.service_method == "search_catalog"
    assert contract.http_path == "GET /api/v1/instruments/search"
    empty = validate_tool_call("search_instruments", {"query": ""})
    assert not empty.allowed
    extra = validate_tool_call("search_instruments", {"query": "AAPL", "url": "http://x"})
    assert not extra.allowed


def test_c1_compare_and_explain_share_compare_runs_engine() -> None:
    assert (
        TOOL_CONTRACTS[RiskToolName.COMPARE_RISK_RUNS].service_method
        == TOOL_CONTRACTS[RiskToolName.EXPLAIN_RISK_CHANGE].service_method
        == "compare_runs"
    )
    assert (
        TOOL_CONTRACTS[RiskToolName.COMPARE_RISK_RUNS].http_path
        == TOOL_CONTRACTS[RiskToolName.EXPLAIN_RISK_CHANGE].http_path
        == "POST /api/v1/risk/runs/compare"
    )

    service = _SharedCompareService()
    engine = RiskQueryEngine()
    args = {"t0_run_id": "run-t0", "t1_run_id": "run-t1", "metric": "var_99"}
    compare = engine.answer_with_model(
        "compare runs",
        SAMPLE_PORTFOLIO,
        service,
        _ScriptedModel(
            RiskAssistantModelResponse(
                tool_name=RiskToolName.COMPARE_RISK_RUNS,
                tool_args=args,
                intent="compare_risk_runs",
            )
        ),
    )
    explain = engine.answer_with_model(
        "explain change",
        SAMPLE_PORTFOLIO,
        service,
        _ScriptedModel(
            RiskAssistantModelResponse(
                tool_name=RiskToolName.EXPLAIN_RISK_CHANGE,
                tool_args=args,
                intent="explain_risk_change",
            )
        ),
    )
    assert service.calls == ["compare_runs", "compare_runs"]
    assert "second_kernel" not in service.calls
    assert compare.data["tool_result"]["residual"] == explain.data["tool_result"]["residual"] == 1.0


def test_c1_run_portfolio_risk_prefers_risk_run_identity() -> None:
    schema = tool_json_schemas()["run_portfolio_risk"]
    assert set(schema["properties"]["run_type"]["enum"]) == {"summary", "var"}
    contract = TOOL_CONTRACTS[RiskToolName.RUN_PORTFOLIO_RISK]
    assert contract.service_method == "submit"
    assert contract.http_path == "POST /api/v1/risk/runs"
    service = _RiskRunService()
    engine = RiskQueryEngine()
    response = engine.answer_with_model(
        "run var",
        SAMPLE_PORTFOLIO,
        service,
        _ScriptedModel(
            RiskAssistantModelResponse(
                tool_name=RiskToolName.RUN_PORTFOLIO_RISK,
                tool_args={"run_type": "var"},
                intent="run_portfolio_risk",
            )
        ),
    )
    assert service.calls == ["submit"]
    payload = response.data["tool_result"]
    assert payload["id"] == "run-1"
    assert payload["run_type"] == "var"
    assert payload["status"] == "QUEUED"


def test_c1_run_stress_allowlists_named_default_scenarios() -> None:
    schema = tool_json_schemas()["run_stress"]
    allowed = set(schema["properties"]["scenario_id"]["enum"])
    assert allowed == {item.id for item in DEFAULT_SCENARIOS}
    assert "eq_down_10" in allowed
    custom = validate_tool_call("run_stress", {"scenario_id": "custom_shock"})
    assert not custom.allowed
    ok = validate_tool_call("run_stress", {"scenario_id": "eq_down_10"})
    assert ok.allowed
    contract = TOOL_CONTRACTS[RiskToolName.RUN_STRESS]
    assert contract.service_method == "submit"
    assert "risk/runs" in contract.http_path


def test_c1_key_rate_dv01_maps_to_rates_showcase_not_new_bump_engine() -> None:
    contract = TOOL_CONTRACTS[RiskToolName.GET_KEY_RATE_DV01]
    assert contract.service_method == "build_rates_showcase"
    assert contract.http_path == "GET /api/v1/market/rates-showcase"
    schema = tool_json_schemas()["get_key_rate_dv01"]
    tenor_schema = (schema.get("properties") or {}).get("tenor") or {}
    tenors = set(tenor_schema.get("enum") or [])
    if not tenors:
        for option in tenor_schema.get("anyOf") or []:
            tenors.update(option.get("enum") or [])
    assert tenors == {"2Y", "5Y", "10Y"}
    service = _RatesShowcaseService()
    engine = RiskQueryEngine()
    response = engine.answer_with_model(
        "10Y KR-DV01",
        SAMPLE_PORTFOLIO,
        service,
        _ScriptedModel(
            RiskAssistantModelResponse(
                tool_name=RiskToolName.GET_KEY_RATE_DV01,
                tool_args={"tenor": "10Y"},
                intent="get_key_rate_dv01",
            )
        ),
    )
    assert service.calls == ["build_rates_showcase"]
    rows = response.data["tool_result"]["key_rate_dv01"]
    assert [row["tenor"] for row in rows] == ["10Y"]


def test_c1_no_quantlib_formula_in_query_or_tool_module() -> None:
    banned = (
        "QuantLib",
        "quantlib",
        "BlackScholes",
        "Actual365",
        "ql.",
    )
    for path in _QUERY_AND_TOOL_MODULES:
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{token} found in {path}"


class _HistoryGuardService(_FixtureService):
    def historical_analytics(self, request) -> None:
        self.calls.append("historical_analytics")
        raise AssertionError("get_market_history must not call historical-analytics")

    def get_market_history(self, instrument_id: str, start, end):
        self.calls.append("get_market_history")
        return {
            "instrument_id": instrument_id,
            "start": str(start),
            "end": str(end),
            "unit": "price",
            "points": [{"observation_date": "2024-01-02", "value": 100.0}],
            "content_hash": "fixture",
        }


class _SharedCompareService(_FixtureService):
    def compare_runs(self, t0_run_id: str, t1_run_id: str, metric: str = "var_99"):
        self.calls.append("compare_runs")
        return _FixturePayload(
            {
                "t0_run_id": t0_run_id,
                "t1_run_id": t1_run_id,
                "metric": metric,
                "previous_risk": 100.0,
                "current_risk": 140.0,
                "total_change": 40.0,
                "residual": 1.0,
                "explained_change": 39.0,
            }
        )

    def explain_risk_change(self, t0_run_id: str, t1_run_id: str, metric: str = "var_99"):
        self.calls.append("second_kernel")
        return super().explain_risk_change(t0_run_id, t1_run_id, metric)


class _RiskRunService(_FixtureService):
    def submit(
        self,
        *,
        portfolio,
        run_type: str = "summary",
        request=None,
        market_snapshot_id=None,
        **_kwargs,
    ):
        self.calls.append("submit")
        return {
            "id": "run-1",
            "portfolio_id": portfolio.id,
            "status": "QUEUED",
            "run_type": run_type,
            "market_snapshot_id": market_snapshot_id,
            "request": request or {},
        }

    def summary(self, portfolio):
        self.calls.append("summary")
        return super().summary(portfolio)


class _RatesShowcaseService(_FixtureService):
    def build_rates_showcase(self):
        self.calls.append("build_rates_showcase")
        return {
            "portfolio_id": "rates-macro",
            "market_snapshot_id": "demo-snap",
            "parallel_dv01": -12.0,
            "key_rate_dv01": [
                {"tenor": "2Y", "value": -1.0, "unit": "per_bp"},
                {"tenor": "5Y", "value": -3.0, "unit": "per_bp"},
                {"tenor": "10Y", "value": -8.0, "unit": "per_bp"},
            ],
        }
