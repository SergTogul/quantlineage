"""M4.6 Limit drill-down.

Conventions:
- Units follow LimitEngine (currency for VaR/DV01/vega; percent for single_position_pct).
- Contributors ranked by abs risk amount; contribution_pct is abs share of total.
- Hierarchy path matches HierarchyEngine node paths (Firm/…/Trade).
- Tolerances: utilization and contribution shares within abs 1e-9 of independent calc.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.domain.models import (
    EquityPosition,
    HierarchyLevel,
    HierarchyRef,
    LimitDrilldownRequest,
    Portfolio,
    RiskLimit,
)
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.limit_drilldown import LimitDrilldownEngine, contributors_for_metric
from app.risk.limits import DEFAULT_LIMITS, LimitEngine
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService, position_label


def _svc() -> PortfolioService:
    return PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine(seed=1, observations=40))


def _tiny_breach_portfolio() -> Portfolio:
    """Concentrated book that breaches single_position_pct at a low limit."""
    return Portfolio(
        id="conc",
        name="Concentrated",
        firm="Acme",
        desk="Equity Desk",
        strategy="Momentum",
        positions=[
            EquityPosition(
                type="equity",
                id="big",
                symbol="AAA",
                quantity=1000,
                price=100.0,
                book="Core",
            ),
            EquityPosition(
                type="equity",
                id="small",
                symbol="BBB",
                quantity=10,
                price=10.0,
                book="Core",
            ),
        ],
    )


def test_enrich_matches_limit_result_fields():
    pricing = BuiltinPricingEngine()
    risk = HistoricalRiskEngine(seed=1, observations=40).calculate(SAMPLE_PORTFOLIO, pricing)
    results = LimitEngine().evaluate(SAMPLE_PORTFOLIO, pricing, risk, DEFAULT_LIMITS)
    engine = LimitDrilldownEngine(HistoricalRiskEngine(seed=1, observations=40))
    report = engine.report(
        SAMPLE_PORTFOLIO,
        pricing,
        breaches_only=False,
        top_n=3,
        label_fn=position_label,
    )
    by_metric = {item.metric: item for item in report.items}
    for lim in results:
        row = by_metric[lim.metric]
        assert row.value == lim.value
        assert row.limit == lim.limit
        assert math.isclose(row.utilization_pct, lim.utilization_pct, abs_tol=1e-9)
        assert row.breached is lim.breached
        assert row.status == lim.status
        assert row.hierarchy_level == "portfolio"
        assert row.hierarchy_node == f"{SAMPLE_PORTFOLIO.firm}/{SAMPLE_PORTFOLIO.id}"
        assert len(row.contributors) <= 3
        assert len(row.contributors) >= 1


def test_breach_drilldown_shows_utilization_and_contributors():
    portfolio = _tiny_breach_portfolio()
    tight = [RiskLimit(metric="single_position_pct", limit=50.0)]
    report = _svc().limit_drilldown(
        portfolio=portfolio,
        limits=tight,
        metric="single_position_pct",
        breaches_only=True,
        top_n=2,
    )
    assert len(report.items) == 1
    item = report.items[0]
    assert item.breached is True
    assert item.metric == "single_position_pct"
    assert item.utilization_pct > 100.0
    assert item.contributors[0].position_id == "big"
    assert item.contributors[0].contribution_pct > item.contributors[1].contribution_pct
    assert math.isclose(
        sum(c.contribution_pct for c in item.contributors),
        100.0,
        abs_tol=1e-9,
    )


def test_hierarchy_scoped_path():
    portfolio = _tiny_breach_portfolio()
    ref = HierarchyRef(
        level=HierarchyLevel.DESK,
        firm="Acme",
        portfolio_id="conc",
        desk="Equity Desk",
    )
    report = _svc().limit_drilldown(
        portfolio=portfolio,
        hierarchy=ref,
        limits=[RiskLimit(metric="single_position_pct", limit=50.0)],
        breaches_only=False,
    )
    assert report.hierarchy_level == "desk"
    assert report.hierarchy_node == "Acme/conc/Equity Desk"
    assert report.items
    assert all(i.hierarchy_node == report.hierarchy_node for i in report.items)


def test_var_contributors_sum_to_100_when_untruncated():
    pricing = BuiltinPricingEngine()
    contribs = contributors_for_metric(
        SAMPLE_PORTFOLIO,
        pricing,
        "var_99",
        top_n=len(SAMPLE_PORTFOLIO.positions),
        label_fn=position_label,
    )
    assert len(contribs) == len(SAMPLE_PORTFOLIO.positions)
    assert math.isclose(sum(c.contribution_pct for c in contribs), 100.0, abs_tol=1e-9)


def test_dv01_contributors_rank_by_abs_greek():
    pricing = BuiltinPricingEngine()
    contribs = contributors_for_metric(
        SAMPLE_PORTFOLIO,
        pricing,
        "dv01",
        top_n=3,
        label_fn=position_label,
    )
    assert contribs
    amounts = [abs(c.risk_amount) for c in contribs]
    assert amounts == sorted(amounts, reverse=True)


def test_breaches_only_filters_ok_rows():
    report = _svc().limit_drilldown(portfolio=SAMPLE_PORTFOLIO, breaches_only=True)
    assert report.items
    assert all(i.breached for i in report.items)
    assert {i.metric for i in report.items} <= {lim.metric for lim in DEFAULT_LIMITS}
    report_all = _svc().limit_drilldown(portfolio=SAMPLE_PORTFOLIO, breaches_only=False)
    assert {i.metric for i in report_all.items} == {lim.metric for lim in DEFAULT_LIMITS}


def test_metric_absent_from_limits_raises():
    with pytest.raises(ValueError, match="not present"):
        _svc().limit_drilldown(
            portfolio=SAMPLE_PORTFOLIO,
            metric="var_95",
            breaches_only=False,
        )


def test_api_limits_drilldown():
    client = TestClient(app)
    portfolio = client.get("/portfolio").json()
    payload = {
        "portfolio": portfolio,
        "breaches_only": False,
        "top_n": 2,
        "metric": "var_99",
    }
    response = client.post("/risk/limits/drilldown", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_id"] == portfolio["id"]
    assert body["hierarchy_level"] == "portfolio"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["metric"] == "var_99"
    assert "hierarchy_node" in item
    assert "utilization_pct" in item
    assert len(item["contributors"]) <= 2


def test_api_request_model_roundtrip():
    req = LimitDrilldownRequest(
        portfolio=SAMPLE_PORTFOLIO,
        metric="vega",
        breaches_only=False,
        top_n=1,
    )
    report = _svc().limit_drilldown(req)
    assert len(report.items) == 1
    assert report.items[0].metric == "vega"
    assert len(report.items[0].contributors) == 1


def test_stress_loss_contributors_nonempty():
    pricing = BuiltinPricingEngine()
    contribs = contributors_for_metric(
        SAMPLE_PORTFOLIO,
        pricing,
        "stress_loss",
        top_n=5,
        label_fn=position_label,
    )
    assert contribs
    assert contribs[0].risk_amount >= 0.0
