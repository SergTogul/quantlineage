from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.limits import DEFAULT_LIMITS
from app.risk.stress import DEFAULT_SCENARIOS, StressEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)
from app.services.portfolio_service import PortfolioService


def test_risk_is_deterministic():
    pricing = BuiltinPricingEngine()
    engine = HistoricalRiskEngine(seed=1)
    a = engine.calculate(SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET)
    b = engine.calculate(SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET)
    assert a == b


def test_var_ordering_and_es():
    r = HistoricalRiskEngine().calculate(
        SAMPLE_PORTFOLIO, BuiltinPricingEngine(), market=SAMPLE_MARKET
    )
    assert r["var_99"] >= r["var_95"] >= 0
    assert r["expected_shortfall_99"] >= r["var_99"]


def test_stress_returns_position_breakdown():
    results = StressEngine().run(SAMPLE_PORTFOLIO, BuiltinPricingEngine(), DEFAULT_SCENARIOS[:1])
    assert len(results) == 1
    assert len(results[0].by_position) == len(SAMPLE_PORTFOLIO.positions)
    assert abs(results[0].pnl - sum(results[0].by_position.values())) < 1e-8


def test_contributors_sum_to_100():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    items = svc.contributors(SAMPLE_PORTFOLIO)
    assert abs(sum(x.contribution_pct for x in items) - 100) < 1e-9


def test_contributors_use_distinct_trade_labels():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    items = svc.contributors(SAMPLE_PORTFOLIO)
    labels = [x.label for x in items]
    assert "SPY equity" in labels
    assert "SPY future" in labels
    assert "SPY put" in labels
    assert "EURUSD fwd" in labels
    assert "EURUSD call" in labels
    assert len(labels) == len(set(labels))


def test_limits_return_expected_metrics():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    rows = svc.limits(SAMPLE_PORTFOLIO)
    metrics = {x.metric for x in rows}
    assert metrics == {lim.metric for lim in DEFAULT_LIMITS}
    assert metrics == {
        "var_99",
        "expected_shortfall_99",
        "dv01",
        "key_rate_dv01",
        "vega",
        "fx_delta",
        "single_position_pct",
        "stress_loss",
    }
    assert all(x.status in {"OK", "WARNING", "BREACH"} for x in rows)
    assert all(x.breached == (x.status == "BREACH") for x in rows)


def test_threat_evaluation_ranks_worst_loss_first():
    from app.risk.stress import THREAT_SCENARIOS
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    report = svc.threat_evaluation(SAMPLE_PORTFOLIO, THREAT_SCENARIOS)
    losses = [x.loss for x in report.evaluations]
    assert losses == sorted(losses, reverse=True)
    assert report.worst_loss == losses[0]
    assert report.worst_scenario == report.evaluations[0].scenario


def test_threat_evaluation_has_governance_and_contributors():
    from app.risk.stress import THREAT_SCENARIOS
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    report = svc.threat_evaluation(SAMPLE_PORTFOLIO, THREAT_SCENARIOS[:1])
    item = report.evaluations[0]
    assert item.max_loss_pct is not None
    assert item.threat_level in {"LOW", "MODERATE", "HIGH", "SEVERE"}
    assert abs(item.stressed_market_value - (item.base_market_value + item.pnl)) < 1e-8
    assert all(x.pnl < 0 for x in item.top_loss_contributors)


def test_custom_scenario_evaluation_uses_supplied_threshold():
    from app.domain.models import StressScenario
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    scenario = StressScenario(name="Test Crash", equity_shock=-0.50, max_loss_pct=0.000001)
    report = svc.threat_evaluation(SAMPLE_PORTFOLIO, [scenario])
    assert report.evaluations[0].breached is True
