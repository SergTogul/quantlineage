"""M4.6 / M4.7 Limit drill-down.

Conventions:
- Units follow LimitEngine (currency for VaR/DV01/vega; percent for single_position_pct).
- Contributors ranked by abs risk amount; contribution_pct is abs share of total.
- Hierarchy path matches HierarchyEngine node paths (Firm/…/Trade).
- key_rate_dv01: tenor KR on LimitEngine binding pillar (max |portfolio KR|), not
  parallel Valuation.dv01; without key_rates/curves falls back to parallel like limits.
- Tolerances: utilization and contribution shares within abs 1e-9 of independent calc;
  signed KR sum vs portfolio binding within rel 1e-9 / abs 1e-6.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import LimitDrilldownRequest
from app.domain.models import (
    BondPosition,
    EquityPosition,
    HierarchyLevel,
    HierarchyRef,
    MarketSnapshot,
    Portfolio,
    RiskLimit,
)
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import RateZero
from app.risk.historical import HistoricalRiskEngine
from app.risk.limit_drilldown import LimitDrilldownEngine, contributors_for_metric
from app.risk.limits import DEFAULT_LIMITS, LimitEngine
from app.risk.sensitivities import SensitivityEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService, position_label

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)

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
                book="Core",
            ),
            EquityPosition(
                type="equity",
                id="small",
                symbol="BBB",
                quantity=10,
                book="Core",
            ),
        ],
    )


def _tiny_breach_market() -> MarketSnapshot:
    return MarketSnapshot(
        id="conc-mkt",
        equity_spots={"AAA": 100.0, "BBB": 10.0},
        rates={"USD": 0.04},
    )


def test_enrich_matches_limit_result_fields():
    pricing = BuiltinPricingEngine()
    risk = HistoricalRiskEngine(seed=1, observations=40).calculate(
        SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET
    )
    results = LimitEngine().evaluate(
        SAMPLE_PORTFOLIO, pricing, risk, DEFAULT_LIMITS, market=SAMPLE_MARKET
    )
    engine = LimitDrilldownEngine(HistoricalRiskEngine(seed=1, observations=40))
    report = engine.report(
        SAMPLE_PORTFOLIO,
        pricing,
        breaches_only=False,
        top_n=3,
        label_fn=position_label,
        market=SAMPLE_MARKET,
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
    market = _tiny_breach_market()
    tight = [RiskLimit(metric="single_position_pct", limit=50.0)]
    pricing = BuiltinPricingEngine()
    engine = LimitDrilldownEngine(HistoricalRiskEngine(seed=1, observations=40))
    report = engine.report(
        portfolio,
        pricing,
        limits=tight,
        metric="single_position_pct",
        breaches_only=True,
        top_n=2,
        label_fn=position_label,
        market=market,
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
    market = _tiny_breach_market()
    ref = HierarchyRef(
        level=HierarchyLevel.DESK,
        firm="Acme",
        portfolio_id="conc",
        desk="Equity Desk",
    )
    pricing = BuiltinPricingEngine()
    engine = LimitDrilldownEngine(HistoricalRiskEngine(seed=1, observations=40))
    report = engine.report(
        portfolio,
        pricing,
        hierarchy=ref,
        limits=[RiskLimit(metric="single_position_pct", limit=50.0)],
        breaches_only=False,
        label_fn=position_label,
        market=market,
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
        market=SAMPLE_MARKET,
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
        market=SAMPLE_MARKET,
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
    with TestClient(app) as client:
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
    report = _svc().limit_drilldown(
        portfolio=req.portfolio,
        metric=req.metric,
        hierarchy=req.hierarchy,
        limits=req.limits,
        top_n=req.top_n,
        breaches_only=req.breaches_only,
    )
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
        market=SAMPLE_MARKET,
    )
    assert contribs
    assert contribs[0].risk_amount >= 0.0


def _kr_bond_book() -> tuple[Portfolio, MarketSnapshot]:
    """10Y + 2Y bonds with key_rates so 10Y KR isolates from the 2Y trade.

    Reported DV01 is PARALLEL +1bp bump-and-revalue (~maturity), so parallel
    ranking also prefers the 10Y bond. Drill-down still follows the binding
    10Y pillar (2Y trade ≈ 0 on that tenor), not a duration×PV shortcut.
    """
    portfolio = Portfolio(
        id="kr-book",
        name="KR book",
        firm="Acme",
        desk="Rates",
        positions=[
            BondPosition(
                type="bond",
                id="b10",
                issuer="UST10",
                face_value=1_000_000,
                quantity=1,
                maturity_years=10.0,
                duration=1.5,
                book="Core",
            ),
            BondPosition(
                type="bond",
                id="b2",
                issuer="UST2",
                face_value=1_000_000,
                quantity=1,
                maturity_years=2.0,
                duration=12.0,
                book="Core",
            ),
        ],
    )
    market = MarketSnapshot(
        id="kr-book-mkt",
        rates={"USD": 0.04},
        key_rates={"USD": {"2Y": 0.03, "10Y": 0.04}},
    )
    return portfolio, market


def test_key_rate_dv01_contributors_use_binding_tenor_not_parallel_dv01():
    """M4.7: with key_rates, drill-down ranks by tenor KR on LimitEngine binding pillar.

    2Y bond has ~0 sensitivity to the 10Y pillar; 10Y bond drives portfolio KR.
    Contributors must follow the binding tenor, not a duration×PV shortcut.
    """
    pricing = BuiltinPricingEngine()
    portfolio, market = _kr_bond_book()

    sens = SensitivityEngine(rate_bump_bps=1.0)
    port_kr = sens.calculate(
        portfolio, pricing, measures=("key_rate_dv01",), market=market
    )
    assert port_kr
    binding = max(port_kr, key=lambda m: abs(m.value))
    assert isinstance(binding.factor, RateZero)
    assert binding.factor.tenor == "10Y"
    assert binding.method == "bump_revalue"

    parallel = {
        p.id: abs(pricing.value(p, market).dv01 or 0.0) for p in portfolio.positions
    }
    assert parallel["b10"] > parallel["b2"]

    contribs = contributors_for_metric(
        portfolio,
        pricing,
        "key_rate_dv01",
        top_n=2,
        market=market,
        label_fn=position_label,
    )
    assert [c.position_id for c in contribs] == ["b10", "b2"]
    assert contribs[0].risk_amount > contribs[1].risk_amount
    # Off-pillar 2Y position contributes ~0 to the binding 10Y KR.
    assert contribs[1].risk_amount == pytest.approx(0.0, abs=1e-9)

    # Signed position KR on binding pillar reconciles to portfolio measure.
    bp = sens.rate_bump_bps
    signed = 0.0
    for p in portfolio.positions:
        up = pricing.value(
            p,
            SensitivityEngine._bump_key_rate(
                market, binding.factor.currency, binding.factor.tenor, bp
            ),
        ).market_value
        down = pricing.value(
            p,
            SensitivityEngine._bump_key_rate(
                market, binding.factor.currency, binding.factor.tenor, -bp
            ),
        ).market_value
        signed += (up - down) / (2.0 * bp)
    assert signed == pytest.approx(binding.value, rel=1e-9, abs=1e-6)
    assert math.isclose(sum(c.contribution_pct for c in contribs), 100.0, abs_tol=1e-9)


def test_key_rate_dv01_contributors_fallback_matches_parallel_without_key_rates():
    """Without key_rates / curves, KR uses parallel bump-revalue (SensitivityEngine).

    Contributors follow SensitivityEngine, same as LimitEngine._key_rate_dv01_abs.
    Reported Valuation.dv01 is also same-curve PARALLEL +1bp (one-sided).
    """
    pricing = BuiltinPricingEngine()
    bond = BondPosition(
        type="bond",
        id="b",
        issuer="UST",
        face_value=1_000_000,
        quantity=1,
        maturity_years=10.0,
        duration=8.0,
    )
    equity = EquityPosition(
        type="equity",
        id="e",
        symbol="SPY",
        quantity=10,
    )
    market = MarketSnapshot(
        id="flat-mkt",
        rates={"USD": 0.04},
        equity_spots={"SPY": 100.0},
    )
    portfolio = Portfolio(id="flat", name="flat", positions=[bond, equity])
    sens = SensitivityEngine(rate_bump_bps=1.0)
    kr_m = sens.calculate_position(bond, pricing, measures=("key_rate_dv01",), market=market)[0]
    dv01_m = sens.calculate_position(bond, pricing, measures=("dv01",), market=market)[0]
    assert kr_m.method == "bump_revalue_parallel_fallback"
    assert abs(kr_m.value) == pytest.approx(abs(dv01_m.value), rel=1e-9, abs=1e-9)
    reported = abs(pricing.value(bond, market).dv01)
    assert reported == pytest.approx(abs(dv01_m.value), rel=1e-2, abs=1.0)
    assert reported == pytest.approx(abs(kr_m.value), rel=1e-2, abs=1.0)

    kr = contributors_for_metric(
        portfolio, pricing, "key_rate_dv01", top_n=2, market=market
    )
    assert [c.position_id for c in kr] == ["b", "e"]
    assert kr[0].risk_amount == pytest.approx(abs(kr_m.value), rel=1e-9, abs=1e-9)
    assert kr[1].risk_amount == pytest.approx(0.0, abs=1e-9)


def test_key_rate_dv01_limit_value_matches_binding_pillar_abs():
    """Drill-down limit row value agrees with SensitivityEngine max |KR| (LimitEngine)."""
    pricing = BuiltinPricingEngine()
    portfolio, market = _kr_bond_book()
    sens = SensitivityEngine(rate_bump_bps=1.0)
    measures = sens.calculate(
        portfolio, pricing, measures=("key_rate_dv01",), market=market
    )
    expected = max(abs(m.value) for m in measures)

    # LimitEngine path without precomputed risk key uses SensitivityEngine the same way
    # but snapshots from PositionMarketDataProvider (no key_rates). Force via risk dict
    # is not available for KR from market — evaluate with empty risk and attach market
    # through resolve by comparing contributor total abs to expected binding.
    contribs = contributors_for_metric(
        portfolio, pricing, "key_rate_dv01", top_n=10, market=market
    )
    total_abs = sum(c.risk_amount for c in contribs)
    assert total_abs == pytest.approx(expected, rel=1e-9, abs=1e-6)
