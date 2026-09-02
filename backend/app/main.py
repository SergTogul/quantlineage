from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.domain.models import AttributionRequest, CustomStressRequest, Portfolio, ReverseStressRequest, RiskQueryRequest, ScenarioComparisonRequest
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.risk.stress import THREAT_SCENARIOS
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService

app = FastAPI(title="RiskForge API", version="0.3.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
service = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())

@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/portfolio",response_model=Portfolio)
def portfolio(): return SAMPLE_PORTFOLIO
@app.post("/market/snapshot")
def market_snapshot(portfolio: Portfolio): return service.market_snapshot(portfolio)
@app.post("/risk/summary")
def risk_summary(portfolio: Portfolio): return service.summary(portfolio)
@app.post("/risk/factors")
def risk_factors(portfolio: Portfolio): return service.factors(portfolio)
@app.post("/risk/var")
def risk_var(portfolio: Portfolio): return service.var_report(portfolio)
@app.post("/risk/hierarchy")
def risk_hierarchy(portfolio: Portfolio): return service.hierarchy(portfolio)
@app.post("/risk/attribution")
def risk_attribution(request: AttributionRequest): return service.attribution(request)
@app.post("/risk/attribution/demo")
def risk_attribution_demo(portfolio: Portfolio): return service.demo_attribution(portfolio)
@app.post("/risk/query")
def risk_query(request: RiskQueryRequest): return service.query(request.portfolio,request.question)
@app.post("/risk/stress")
def risk_stress(portfolio: Portfolio): return service.stresses(portfolio)
@app.get("/risk/stress/scenarios")
def risk_stress_scenarios(): return THREAT_SCENARIOS
@app.post("/risk/stress/custom")
def risk_stress_custom(request: CustomStressRequest): return service.stresses(request.portfolio,request.scenarios)
@app.post("/risk/stress/evaluate")
def risk_stress_evaluate(portfolio: Portfolio): return service.threat_evaluation(portfolio)
@app.post("/risk/stress/evaluate/custom")
def risk_stress_evaluate_custom(request: CustomStressRequest): return service.threat_evaluation(request.portfolio,request.scenarios)
@app.post("/risk/stress/reverse")
def risk_stress_reverse(request: ReverseStressRequest): return service.reverse_stress(request.portfolio,request.target_loss_pct,request.factor,request.max_shock)
@app.post("/risk/stress/compare")
def risk_stress_compare(request: ScenarioComparisonRequest): return service.compare_scenarios(request.portfolio,request.hedged_portfolio,request.scenarios)
@app.post("/risk/contributors")
def risk_contributors(portfolio: Portfolio): return service.contributors(portfolio)
@app.post("/risk/limits")
def risk_limits(portfolio: Portfolio): return service.limits(portfolio)
