"""Stress / reverse-stress / threat routes (M7.1). Under /risk until M7.2.

M3.8: formal ``Scenario`` wire under ``/risk/stress/formal/*`` and
``GET /risk/stress/scenarios/formal`` (legacy ``StressScenario`` endpoints unchanged).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.api.backpressure import reject_inline_heavy
from app.api.deps import (
    get_baseline_stress_scenarios,
    get_default_market_snapshot,
    get_default_stress_scenarios,
    get_portfolio_service,
)
from app.api.openapi_examples import (
    FORMAL_CUSTOM_STRESS_BODY_EXAMPLES,
    HEDGE_COMPARE_BODY_EXAMPLES,
    RESP_HEDGE_COMPARE,
    RESP_REVERSE,
    RESP_REVERSE_MULTI,
    RESP_STRESS,
    REVERSE_BODY_EXAMPLES,
    REVERSE_MULTI_BODY_EXAMPLES,
    STRESS_BODY_EXAMPLES,
)
from app.api.scenario_wire import (
    FormalCustomStressRequest,
    ScenarioWire,
    stress_to_wire,
    wires_to_stress,
)
from app.domain.models import (
    CustomStressRequest,
    HedgeComparisonReport,
    MarketSnapshot,
    MultiFactorReverseStressRequest,
    MultiFactorReverseStressResult,
    Portfolio,
    ReverseStressRequest,
    ReverseStressResult,
    ScenarioComparisonRequest,
    StressResult,
    StressScenario,
)
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/risk", tags=["stress"])


@router.post(
    "/stress",
    response_model=list[StressResult],
    summary="Baseline stress P&L",
    responses=RESP_STRESS,
)
def risk_stress(
    portfolio: Annotated[
        Portfolio,
        Body(openapi_examples=STRESS_BODY_EXAMPLES),
    ],
    scenarios: list[StressScenario] = Depends(get_baseline_stress_scenarios),
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[StressResult]:
    """Baseline stress P&L over DI DEFAULT scenarios (M5.9 follow-up)."""
    reject_inline_heavy(route="POST /risk/stress")
    return service.stresses(portfolio, scenarios)


@router.get("/stress/scenarios")
def risk_stress_scenarios(
    scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
):
    """List scenario definitions from DI repo; THREAT_SCENARIOS if repo empty (M5.9)."""
    return scenarios


@router.get(
    "/stress/scenarios/formal",
    response_model=list[ScenarioWire],
    summary="List scenarios as formal Scenario wire (M3.8)",
)
def risk_stress_scenarios_formal(
    scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
    base: MarketSnapshot = Depends(get_default_market_snapshot),
) -> list[ScenarioWire]:
    """Same DI defaults as ``GET /stress/scenarios``, projected to formal wire."""
    return [stress_to_wire(s, base) for s in scenarios]


@router.post("/stress/custom")
def risk_stress_custom(
    request: CustomStressRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    reject_inline_heavy(route="POST /risk/stress/custom")
    return service.stresses(request.portfolio, request.scenarios)


@router.post(
    "/stress/formal/custom",
    response_model=list[StressResult],
    summary="Custom stress P&L (formal Scenario wire)",
    responses=RESP_STRESS,
)
def risk_stress_formal_custom(
    request: Annotated[
        FormalCustomStressRequest,
        Body(openapi_examples=FORMAL_CUSTOM_STRESS_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[StressResult]:
    """Accept formal Scenario wire; adapt to StressScenario for StressEngine (M3.8)."""
    reject_inline_heavy(route="POST /risk/stress/formal/custom")
    return service.stresses(request.portfolio, wires_to_stress(request.scenarios))


@router.post("/stress/evaluate")
def risk_stress_evaluate(
    portfolio: Portfolio,
    scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Threat evaluation over DI-backed scenario defaults (M5.9)."""
    reject_inline_heavy(route="POST /risk/stress/evaluate")
    return service.threat_evaluation(portfolio, scenarios)


@router.post("/stress/evaluate/custom")
def risk_stress_evaluate_custom(
    request: CustomStressRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    reject_inline_heavy(route="POST /risk/stress/evaluate/custom")
    return service.threat_evaluation(request.portfolio, request.scenarios)


@router.post(
    "/stress/formal/evaluate/custom",
    summary="Threat evaluation (formal Scenario wire)",
)
def risk_stress_formal_evaluate_custom(
    request: Annotated[
        FormalCustomStressRequest,
        Body(openapi_examples=FORMAL_CUSTOM_STRESS_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Accept formal Scenario wire; adapt to StressScenario for threat evaluate (M3.8)."""
    reject_inline_heavy(route="POST /risk/stress/formal/evaluate/custom")
    return service.threat_evaluation(
        request.portfolio, wires_to_stress(request.scenarios)
    )


@router.post(
    "/stress/reverse",
    response_model=ReverseStressResult,
    summary="Single-factor reverse stress",
    responses=RESP_REVERSE,
)
def risk_stress_reverse(
    request: Annotated[
        ReverseStressRequest,
        Body(openapi_examples=REVERSE_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> ReverseStressResult:
    reject_inline_heavy(route="POST /risk/stress/reverse")
    return service.reverse_stress(
        request.portfolio,
        request.target_loss_pct,
        request.factor,
        request.max_shock,
    )


@router.post(
    "/stress/reverse/multi",
    response_model=MultiFactorReverseStressResult,
    summary="Multi-factor reverse stress",
    responses=RESP_REVERSE_MULTI,
)
def risk_stress_reverse_multi(
    request: Annotated[
        MultiFactorReverseStressRequest,
        Body(openapi_examples=REVERSE_MULTI_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> MultiFactorReverseStressResult:
    reject_inline_heavy(route="POST /risk/stress/reverse/multi")
    return service.reverse_stress_multi(
        request.portfolio,
        request.target_loss_pct,
        factors=request.factors,
        weights=request.weights,
        max_shock=request.max_shock,
        max_shocks=request.max_shocks,
    )


@router.post(
    "/stress/compare",
    response_model=HedgeComparisonReport,
    summary="Hedge comparison (VaR/ES + scenario P&L)",
    responses=RESP_HEDGE_COMPARE,
)
def risk_stress_compare(
    request: Annotated[
        ScenarioComparisonRequest,
        Body(openapi_examples=HEDGE_COMPARE_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> HedgeComparisonReport:
    reject_inline_heavy(route="POST /risk/stress/compare")
    return service.compare_scenarios(
        request.portfolio,
        request.hedged_portfolio,
        request.scenarios,
        methodology=request.methodology,
    )
