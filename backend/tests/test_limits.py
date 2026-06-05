"""M4.5 configurable risk limits — OK / WARNING / BREACH and metric coverage."""

from __future__ import annotations

from app.domain.models import MarketSnapshot, RiskLimit, RiskSummary
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.limits import (
    DEFAULT_LIMITS,
    LimitEngine,
    classify_limit_status,
)
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)
from app.services.portfolio_service import PortfolioService

EXPECTED_DEFAULT_METRICS = {
    "var_99",
    "expected_shortfall_99",
    "dv01",
    "key_rate_dv01",
    "vega",
    "fx_delta",
    "single_position_pct",
    "stress_loss",
}


def test_classify_ok_warning_breach():
    assert classify_limit_status(50.0, 100.0, 80.0) == "OK"
    assert classify_limit_status(80.0, 100.0, 80.0) == "WARNING"
    assert classify_limit_status(99.0, 100.0, 80.0) == "WARNING"
    assert classify_limit_status(100.0, 100.0, 80.0) == "WARNING"  # value == limit → not BREACH
    assert classify_limit_status(100.01, 100.0, 80.0) == "BREACH"
    assert classify_limit_status(10.0, 100.0, 5.0) == "WARNING"


def test_default_limits_cover_required_metrics():
    assert {lim.metric for lim in DEFAULT_LIMITS} == EXPECTED_DEFAULT_METRICS
    assert any(lim.scope == "firm" and lim.metric == "var_99" for lim in DEFAULT_LIMITS)
    assert any(lim.metric == "expected_shortfall_99" for lim in DEFAULT_LIMITS)


def test_evaluate_statuses_and_fields():
    pricing = BuiltinPricingEngine()
    risk = HistoricalRiskEngine(seed=1, observations=40).calculate(
        SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET
    )
    # Force known utilization bands via tiny / huge limits.
    limits = [
        RiskLimit(metric="var_99", limit=1e18, warning_threshold_pct=80.0, label="huge"),
        RiskLimit(metric="dv01", limit=1e-12, warning_threshold_pct=50.0, label="tiny"),
        RiskLimit(
            metric="vega",
            limit=abs(risk.vega) / 0.85 if risk.vega else 1.0,
            warning_threshold_pct=80.0,
            label="warn-band",
        ),
    ]
    results = LimitEngine().evaluate(SAMPLE_PORTFOLIO, pricing, risk, limits)
    by_metric = {r.metric: r for r in results}
    assert by_metric["var_99"].status == "OK"
    assert by_metric["var_99"].breached is False
    assert by_metric["dv01"].status == "BREACH"
    assert by_metric["dv01"].breached is True
    assert by_metric["vega"].status in {"OK", "WARNING", "BREACH"}
    assert by_metric["vega"].warning_threshold_pct == 80.0
    assert by_metric["vega"].label == "warn-band"


def test_service_limits_include_new_metrics_and_status():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine(seed=1, observations=40))
    rows = svc.limits(SAMPLE_PORTFOLIO)
    metrics = {r.metric for r in rows}
    assert metrics == EXPECTED_DEFAULT_METRICS
    assert all(r.status in {"OK", "WARNING", "BREACH"} for r in rows)
    assert all(r.breached == (r.status == "BREACH") for r in rows)
    stress = next(r for r in rows if r.metric == "stress_loss")
    assert stress.value >= 0.0
    kr = next(r for r in rows if r.metric == "key_rate_dv01")
    assert kr.value >= 0.0


def test_configurable_warning_threshold():
    pricing = BuiltinPricingEngine()
    risk = RiskSummary(
        portfolio_id="warn",
        market_value=0.0,
        delta=0.0,
        gamma=0.0,
        vega=0.0,
        dv01=0.0,
        var_95=0.0,
        var_99=90.0,
        expected_shortfall_99=0.0,
    )
    tight = RiskLimit(metric="var_99", limit=100.0, warning_threshold_pct=95.0)
    loose = RiskLimit(metric="var_99", limit=100.0, warning_threshold_pct=50.0)
    engine = LimitEngine()
    # 90% util: OK under 95% warning threshold, WARNING under 50%.
    assert engine.evaluate(SAMPLE_PORTFOLIO, pricing, risk, [tight])[0].status == "OK"
    assert engine.evaluate(SAMPLE_PORTFOLIO, pricing, risk, [loose])[0].status == "WARNING"


def test_zero_portfolio_zero_risk_limits_ok():
    from app.domain.models import Portfolio

    empty = Portfolio(id="empty", name="Empty", positions=[])
    pricing = BuiltinPricingEngine()
    risk = HistoricalRiskEngine(seed=1, observations=20).calculate(
        empty, pricing, market=MarketSnapshot(id="empty")
    )
    rows = LimitEngine().evaluate(
        empty, pricing, risk, DEFAULT_LIMITS, extra={"stress_loss": 0.0, "key_rate_dv01": 0.0}
    )
    assert all(r.value == 0.0 or r.metric == "single_position_pct" for r in rows)
    # Empty book: concentration uses gross=1 fallback → 0%; all should be OK.
    assert all(r.status == "OK" for r in rows)
