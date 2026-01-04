"""Stress / reverse-stress / threat routes (M7.1). Under /risk until M7.2."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.api.deps import (
    get_baseline_stress_scenarios,
    get_default_stress_scenarios,
    get_portfolio_service,
)
from app.api.openapi_examples import (
    HEDGE_COMPARE_BODY_EXAMPLES,
    RESP_HEDGE_COMPARE,
    RESP_REVERSE,
    RESP_REVERSE_MULTI,
    RESP_STRESS,
    REVERSE_BODY_EXAMPLES,
    REVERSE_MULTI_BODY_EXAMPLES,
    STRESS_BODY_EXAMPLES,
)
from app.domain.models import (
    CustomStressRequest,
    MultiFactorReverseStressRequest,
    Portfolio,
    ReverseStressRequest,
    ScenarioComparisonRequest,
    StressScenario,
)
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/risk", tags=["stress"])


@router.post(
    "/stress",
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
):
    """Baseline stress P&L over DI DEFAULT scenarios (M5.9 follow-up)."""
    return service.stresses(portfolio, scenarios)


@router.get("/stress/scenarios")
def risk_stress_scenarios(
    scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
):
    """List scenario definitions from DI repo; THREAT_SCENARIOS if repo empty (M5.9)."""
    return scenarios


@router.post("/stress/custom")
def risk_stress_custom(
    request: CustomStressRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.stresses(request.portfolio, request.scenarios)


@router.post("/stress/evaluate")
def risk_stress_evaluate(
    portfolio: Portfolio,
    scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Threat evaluation over DI-backed scenario defaults (M5.9)."""
    return service.threat_evaluation(portfolio, scenarios)


@router.post("/stress/evaluate/custom")
def risk_stress_evaluate_custom(
    request: CustomStressRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.threat_evaluation(request.portfolio, request.scenarios)


@router.post(
    "/stress/reverse",
    summary="Single-factor reverse stress",
    responses=RESP_REVERSE,
)
def risk_stress_reverse(
    request: Annotated[
        ReverseStressRequest,
        Body(openapi_examples=REVERSE_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.reverse_stress(
        request.portfolio,
        request.target_loss_pct,
        request.factor,
        request.max_shock,
    )


@router.post(
    "/stress/reverse/multi",
    summary="Multi-factor reverse stress",
    responses=RESP_REVERSE_MULTI,
)
def risk_stress_reverse_multi(
    request: Annotated[
        MultiFactorReverseStressRequest,
        Body(openapi_examples=REVERSE_MULTI_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
):
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
    summary="Hedge comparison (VaR/ES + scenario P&L)",
    responses=RESP_HEDGE_COMPARE,
)
def risk_stress_compare(
    request: Annotated[
        ScenarioComparisonRequest,
        Body(openapi_examples=HEDGE_COMPARE_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.compare_scenarios(
        request.portfolio,
        request.hedged_portfolio,
        request.scenarios,
        methodology=request.methodology,
    )
