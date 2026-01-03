"""Core risk routes (M7.1). Paths stay under /risk until M7.2 /api/v1 migration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_portfolio_service
from app.domain.models import Portfolio, RiskQueryRequest, VaRMethodology, WhatIfRequest
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/summary")
def risk_summary(
    portfolio: Portfolio,
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.summary(portfolio, methodology=methodology)


@router.post("/factors")
def risk_factors(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.factors(portfolio)


@router.post("/var")
def risk_var(
    portfolio: Portfolio,
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.var_report(portfolio, methodology=methodology)


@router.post("/es")
def risk_es(
    portfolio: Portfolio,
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Historical Expected Shortfall contributions by position / book / desk / strategy / factor (M2.5)."""
    return service.es_contributions(portfolio, methodology=methodology)


@router.post("/var/compare")
def risk_var_compare(
    portfolio: Portfolio,
    observations: int | None = Query(default=None, ge=1, le=5000),
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Compare LINEAR / DELTA_GAMMA / FULL_REVALUATION historical VaR (M2.4)."""
    return service.compare_var_methodologies(portfolio, observations=observations)


@router.post("/what-if")
def risk_what_if(
    request: WhatIfRequest,
    methodology: VaRMethodology | None = Query(
        default=None,
        description="Optional override; defaults to request.methodology (DELTA_GAMMA).",
    ),
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Hypothetical add/remove/modify without mutating persisted portfolio (M2.9).

    Mounted at ``/risk/what-if`` until M7.2 API versioning moves routes under ``/api/v1``.
    """
    try:
        return service.what_if(request, methodology=methodology)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/hierarchy")
def risk_hierarchy(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.hierarchy(portfolio)


@router.post("/query")
def risk_query(
    request: RiskQueryRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.query(request.portfolio, request.question)


@router.post("/contributors")
def risk_contributors(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.contributors(portfolio)
