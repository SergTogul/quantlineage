"""M3.7 strengthened hedge comparison tests.

Acceptance:
- hedge_cost = MV(hedged) − MV(base)
- base/hedged VaR 99 and ES 99 with improvement = base − hedged
- per-scenario P&L + loss diagnostics; loss_improvement reconciles
- factor exposure changes when hedge alters Greeks
- legacy scenario fields (base_pnl, hedged_pnl, improvement) preserved
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.models import HedgeComparisonReport, StressScenario, VaRMethodology
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.stress import ScenarioComparisonEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)

_TOL = 1e-9
_OBS = 80


@pytest.fixture
def svc():
    return PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=7, observations=_OBS),
    )


def _flat_spy_hedge():
    hedge = SAMPLE_PORTFOLIO.model_copy(deep=True)
    # Flatten long SPY equity (id typically eq-spy / second equity-ish position varies).
    for p in hedge.positions:
        if getattr(p, "symbol", None) == "SPY" and p.type == "equity":
            p.quantity = 0.0
            break
    else:
        # Fallback: zero second position as in legacy next_phase test.
        hedge.positions[1].quantity = 0
    return hedge


def test_compare_returns_hedge_report_with_metrics(svc):
    hedge = _flat_spy_hedge()
    scenarios = [StressScenario(name="Crash", equity_shock=-0.2)]
    report = svc.compare_scenarios(SAMPLE_PORTFOLIO, hedge, scenarios)
    assert isinstance(report, HedgeComparisonReport)
    assert len(report.scenarios) == 1
    row = report.scenarios[0]
    assert row.scenario == "Crash"
    assert row.improvement == pytest.approx(row.hedged_pnl - row.base_pnl, abs=_TOL)
    assert row.base_loss == pytest.approx(max(0.0, -row.base_pnl), abs=_TOL)
    assert row.hedged_loss == pytest.approx(max(0.0, -row.hedged_pnl), abs=_TOL)
    assert row.loss_improvement == pytest.approx(row.base_loss - row.hedged_loss, abs=_TOL)

    assert report.hedge_cost == pytest.approx(
        report.hedged_market_value - report.base_market_value, abs=_TOL
    )
    assert report.var_improvement == pytest.approx(
        report.base_var_99 - report.hedged_var_99, abs=_TOL
    )
    assert report.es_improvement == pytest.approx(
        report.base_expected_shortfall_99 - report.hedged_expected_shortfall_99, abs=_TOL
    )
    assert report.methodology == VaRMethodology.DELTA_GAMMA
    # Flattening SPY should change equity exposure.
    assert any(c.delta != 0.0 for c in report.factor_exposure_changes)


def test_identical_portfolios_zero_deltas(svc):
    scenarios = [StressScenario(name="Flat", equity_shock=-0.1)]
    report = svc.compare_scenarios(SAMPLE_PORTFOLIO, SAMPLE_PORTFOLIO, scenarios)
    assert report.hedge_cost == pytest.approx(0.0, abs=1e-6)
    assert report.var_improvement == pytest.approx(0.0, abs=1e-6)
    assert report.es_improvement == pytest.approx(0.0, abs=1e-6)
    assert report.factor_exposure_changes == []
    row = report.scenarios[0]
    assert row.improvement == pytest.approx(0.0, abs=1e-6)
    assert row.loss_improvement == pytest.approx(0.0, abs=1e-6)


def test_engine_deterministic():
    engine = ScenarioComparisonEngine(
        risk_engine=HistoricalRiskEngine(seed=3, observations=_OBS),
    )
    pricing = BuiltinPricingEngine()
    hedge = _flat_spy_hedge()
    scenarios = [StressScenario(name="VolUp", vol_shock=0.3)]
    a = engine.compare(SAMPLE_PORTFOLIO, hedge, pricing, scenarios, market=SAMPLE_MARKET)
    b = engine.compare(SAMPLE_PORTFOLIO, hedge, pricing, scenarios, market=SAMPLE_MARKET)
    assert a.model_dump() == b.model_dump()


def test_compare_api():
    client = TestClient(app)
    portfolio = client.get("/portfolio").json()
    hedge = client.get("/portfolio").json()
    for p in hedge["positions"]:
        if p.get("symbol") == "SPY" and p.get("type") == "equity":
            p["quantity"] = 0
            break
    body = {
        "portfolio": portfolio,
        "hedged_portfolio": hedge,
        "scenarios": [{"name": "Crash", "equity_shock": -0.2}],
        "methodology": "DELTA_GAMMA",
    }
    r = client.post("/risk/stress/compare", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "hedge_cost" in data
    assert "base_var_99" in data
    assert "hedged_var_99" in data
    assert "base_expected_shortfall_99" in data
    assert "scenarios" in data
    assert data["scenarios"][0]["scenario"] == "Crash"
    assert "loss_improvement" in data["scenarios"][0]
    assert "factor_exposure_changes" in data
