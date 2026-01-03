from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.api.deps import (
    get_baseline_stress_scenarios,
    get_default_portfolio,
    get_default_stress_scenarios,
)
from app.api.risk_runs import router as risk_runs_router
from app.domain.models import (
    AttributionRequest,
    CustomStressRequest,
    LimitDrilldownRequest,
    MultiFactorReverseStressRequest,
    Portfolio,
    ReverseStressRequest,
    RiskChangeAttributionRequest,
    RiskQueryRequest,
    ScenarioComparisonRequest,
    StressScenario,
    VaRMethodology,
    WhatIfRequest,
)
from app.persistence.wiring import build_persistence_wiring
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.services.portfolio_service import PortfolioService
from app.services.risk_run_worker import RiskRunWorker

service = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
# Default in-memory worker; lifespan may replace with SQLAlchemy-backed worker
# when RISKFORGE_DATABASE_URL is set (M5.6).
risk_run_worker = RiskRunWorker(service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire optional SQLAlchemy persistence; else sample / memory backends.

    When ``RISKFORGE_DATABASE_URL`` is set, seeds portfolio + market snapshot +
    scenario / limit definitions and exposes SQLAlchemy via session factory.
    When unset, in-memory repos (pre-seeded) live on ``app.state`` for Depends.
    """
    wiring = build_persistence_wiring()
    app.state.persistence_enabled = wiring.enabled
    app.state.session_factory = wiring.session_factory
    app.state.default_portfolio_id = wiring.default_portfolio_id
    app.state.default_market_snapshot_id = wiring.default_market_snapshot_id
    app.state.market_snapshot_repo = wiring.market_snapshot_repo
    app.state.scenario_definition_repo = wiring.scenario_definition_repo
    app.state.limit_definition_repo = wiring.limit_definition_repo

    if wiring.enabled and wiring.session_factory is not None:
        worker = RiskRunWorker(service, session_factory=wiring.session_factory)
    else:
        worker = risk_run_worker
        worker.ensure_running()

    app.state.risk_run_worker = worker
    yield
    worker.shutdown(wait=False)


app = FastAPI(title="RiskForge API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# M5.4 async runs under /risk until M7.2 moves routes to /api/v1.
app.include_router(risk_runs_router, prefix="/risk")
# Forward-compatible alias (same handlers); prefer /api/v1 after M7.2.
app.include_router(risk_runs_router, prefix="/api/v1/risk")

@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/portfolio",response_model=Portfolio)
def portfolio(portfolio: Portfolio = Depends(get_default_portfolio)):
    """Demo portfolio: SQLAlchemy when RISKFORGE_DATABASE_URL set, else SAMPLE."""
    return portfolio
@app.post("/market/snapshot")
def market_snapshot(portfolio: Portfolio): return service.market_snapshot(portfolio)
@app.post("/risk/summary")
def risk_summary(
    portfolio: Portfolio,
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
):
    return service.summary(portfolio, methodology=methodology)
@app.post("/risk/factors")
def risk_factors(portfolio: Portfolio): return service.factors(portfolio)
@app.post("/risk/var")
def risk_var(
    portfolio: Portfolio,
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
):
    return service.var_report(portfolio, methodology=methodology)
@app.post("/risk/es")
def risk_es(
    portfolio: Portfolio,
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
):
    """Historical Expected Shortfall contributions by position / book / desk / strategy / factor (M2.5)."""
    return service.es_contributions(portfolio, methodology=methodology)
@app.post("/risk/var/compare")
def risk_var_compare(
    portfolio: Portfolio,
    observations: int | None = Query(default=None, ge=1, le=5000),
):
    """Compare LINEAR / DELTA_GAMMA / FULL_REVALUATION historical VaR (M2.4)."""
    return service.compare_var_methodologies(portfolio, observations=observations)
@app.post("/risk/what-if")
def risk_what_if(
    request: WhatIfRequest,
    methodology: VaRMethodology | None = Query(
        default=None,
        description="Optional override; defaults to request.methodology (DELTA_GAMMA).",
    ),
):
    """Hypothetical add/remove/modify without mutating persisted portfolio (M2.9).

    Mounted at ``/risk/what-if`` until M7.2 API versioning moves routes under ``/api/v1``.
    """
    try:
        return service.what_if(request, methodology=methodology)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
@app.post("/risk/hierarchy")
def risk_hierarchy(portfolio: Portfolio): return service.hierarchy(portfolio)
@app.post("/risk/attribution")
def risk_attribution(request: AttributionRequest): return service.attribution(request)
@app.post("/risk/attribution/demo")
def risk_attribution_demo(portfolio: Portfolio): return service.demo_attribution(portfolio)
@app.post("/risk/change-attribution")
def risk_change_attribution(request: RiskChangeAttributionRequest):
    """Risk-metric change waterfall (VaR/ES drivers) — separate from P&L Explain (M4.4)."""
    return service.risk_change_attribution(request)
@app.post("/risk/query")
def risk_query(request: RiskQueryRequest): return service.query(request.portfolio,request.question)
@app.post("/risk/stress")
def risk_stress(
    portfolio: Portfolio,
    scenarios: list[StressScenario] = Depends(get_baseline_stress_scenarios),
):
    """Baseline stress P&L over DI DEFAULT scenarios (M5.9 follow-up)."""
    return service.stresses(portfolio, scenarios)
@app.get("/risk/stress/scenarios")
def risk_stress_scenarios(
    scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
):
    """List scenario definitions from DI repo; THREAT_SCENARIOS if repo empty (M5.9)."""
    return scenarios
@app.post("/risk/stress/custom")
def risk_stress_custom(request: CustomStressRequest): return service.stresses(request.portfolio,request.scenarios)
@app.post("/risk/stress/evaluate")
def risk_stress_evaluate(
    portfolio: Portfolio,
    scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
):
    """Threat evaluation over DI-backed scenario defaults (M5.9)."""
    return service.threat_evaluation(portfolio, scenarios)
@app.post("/risk/stress/evaluate/custom")
def risk_stress_evaluate_custom(request: CustomStressRequest): return service.threat_evaluation(request.portfolio,request.scenarios)
@app.post("/risk/stress/reverse")
def risk_stress_reverse(request: ReverseStressRequest): return service.reverse_stress(request.portfolio,request.target_loss_pct,request.factor,request.max_shock)
@app.post("/risk/stress/reverse/multi")
def risk_stress_reverse_multi(request: MultiFactorReverseStressRequest):
    return service.reverse_stress_multi(
        request.portfolio,
        request.target_loss_pct,
        factors=request.factors,
        weights=request.weights,
        max_shock=request.max_shock,
        max_shocks=request.max_shocks,
    )
@app.post("/risk/stress/compare")
def risk_stress_compare(request: ScenarioComparisonRequest):
    return service.compare_scenarios(
        request.portfolio,
        request.hedged_portfolio,
        request.scenarios,
        methodology=request.methodology,
    )
@app.post("/risk/contributors")
def risk_contributors(portfolio: Portfolio): return service.contributors(portfolio)
@app.post("/risk/limits")
def risk_limits(portfolio: Portfolio): return service.limits(portfolio)
@app.post("/risk/limits/drilldown")
def risk_limits_drilldown(request: LimitDrilldownRequest):
    """Limit breach drill-down: hierarchy node, metric, utilization, top contributors (M4.6)."""
    try:
        return service.limit_drilldown(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
