import math

from fastapi.testclient import TestClient

from app.domain.models import AttributionRequest, StressScenario
from app.main import app
from app.market.snapshot import shock_snapshot
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService

svc=PortfolioService(BuiltinPricingEngine(),HistoricalRiskEngine())
client=TestClient(app)


def test_market_snapshot_and_instrument_specific_shock():
    market=demo_market_snapshot(SAMPLE_PORTFOLIO)
    assert market.equity_spots["NVDA"] == 118.5
    assert market.fx_spots["EURUSD"] == 1.10
    shocked=shock_snapshot(market,StressScenario(name="NVDA only",equity_shocks={"NVDA":-0.2}))
    assert math.isclose(shocked.equity_spots["NVDA"],94.8)
    assert shocked.equity_spots["SPY"] == market.equity_spots["SPY"]


def test_extended_derivatives_price_and_have_risk():
    pricing=BuiltinPricingEngine()
    market=demo_market_snapshot(SAMPLE_PORTFOLIO)
    vals={p.id:pricing.value(p, market) for p in SAMPLE_PORTFOLIO.positions}
    assert vals["fut-es"].delta != 0
    assert vals["fxf-eurusd"].fx_delta != 0
    assert vals["fxo-eurusd"].vega != 0


def test_risk_factors_include_equity_rates_vol_and_fx():
    types={x.factor_type for x in svc.factors(SAMPLE_PORTFOLIO)}
    assert {"equity","rate","vol","fx"} <= types


def test_var_report_has_two_methods_and_component_sum():
    report=svc.var_report(SAMPLE_PORTFOLIO)
    assert {x.method for x in report.methods} == {"historical","parametric"}
    pvar=next(x.var for x in report.methods if x.method=="parametric")
    assert math.isclose(sum(x.component_var for x in report.contributions),pvar,rel_tol=1e-8,abs_tol=1e-6)


def test_reverse_stress_finds_equity_loss_threshold():
    result=svc.reverse_stress(SAMPLE_PORTFOLIO,0.01,"equity",0.8)
    assert result.converged
    assert 0 < result.required_shock <= 0.8
    assert result.achieved_loss_pct >= 0.01


def test_hierarchy_drills_to_trade_level():
    root=svc.hierarchy(SAMPLE_PORTFOLIO)
    assert root.level=="firm"
    portfolio=root.children[0]
    assert portfolio.level=="portfolio"
    desk=portfolio.children[0]; strategy=desk.children[0]
    assert desk.level=="desk" and strategy.level=="strategy"
    assert any(t.level=="trade" for b in strategy.children for t in b.children)


def test_attribution_is_zero_for_identical_state():
    report=svc.attribution(AttributionRequest(previous_portfolio=SAMPLE_PORTFOLIO,current_portfolio=SAMPLE_PORTFOLIO))
    assert abs(report.total_change) < 1e-9
    assert abs(report.residual) < 1e-9


def test_attribution_explains_position_change():
    current=SAMPLE_PORTFOLIO.model_copy(deep=True)
    current.positions[0].quantity += 100
    report=svc.attribution(AttributionRequest(previous_portfolio=SAMPLE_PORTFOLIO,current_portfolio=current))
    assert report.total_change != 0
    assert abs(report.residual) < 1e-6
    assert next(x for x in report.items if x.driver=="New trades").pnl != 0


def test_deterministic_query_routes_to_risk_tools():
    x=svc.query(SAMPLE_PORTFOLIO,"What is the worst stress scenario?")
    assert x.intent=="worst_scenario"
    y=svc.query(SAMPLE_PORTFOLIO,"Show top risk contributors")
    assert y.intent=="contributors"


def test_new_api_endpoints():
    portfolio=client.get('/portfolio').json()
    for endpoint in ['/risk/factors','/risk/var','/risk/hierarchy']:
        r=client.post(endpoint,json=portfolio); assert r.status_code==200, r.text
    rev=client.post('/risk/stress/reverse',json={"portfolio":portfolio,"target_loss_pct":0.01,"factor":"equity"})
    assert rev.status_code==200 and rev.json()['converged']
    q=client.post('/risk/query',json={"portfolio":portfolio,"question":"What is 99% VaR?"})
    assert q.status_code==200 and q.json()['intent']=='var'
    att=client.post('/risk/attribution',json={"previous_portfolio":portfolio,"current_portfolio":portfolio})
    assert att.status_code==200 and abs(att.json()['residual']) < 1e-8


def test_scenario_comparison_measures_hedge_improvement():
    hedge=SAMPLE_PORTFOLIO.model_copy(deep=True)
    # Reduce long SPY exposure; comparison should at least return aligned scenario results.
    hedge.positions[1].quantity = 0
    scenarios=[StressScenario(name="Crash",equity_shock=-0.2)]
    report=svc.compare_scenarios(SAMPLE_PORTFOLIO,hedge,scenarios)
    assert len(report.scenarios)==1 and report.scenarios[0].scenario=="Crash"
    assert report.scenarios[0].improvement != 0
    assert report.hedge_cost == report.hedged_market_value - report.base_market_value


def test_market_and_demo_attribution_api():
    portfolio=client.get('/portfolio').json()
    market=client.post('/market/snapshot',json=portfolio)
    demo=client.post('/risk/attribution/demo',json=portfolio)
    assert market.status_code==200 and 'equity_spots' in market.json()
    assert demo.status_code==200 and abs(demo.json()['total_change']) > 0
