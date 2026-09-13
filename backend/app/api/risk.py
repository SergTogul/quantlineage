"""Core risk routes (M7.1). Paths stay under /risk until M7.2 /api/v1 migration."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from app.api.backpressure import reject_inline_heavy
from app.api.dashboard import router as dashboard_router
from app.api.deps import get_portfolio_service
from app.api.errors import http_bad_request
from app.api.openapi_examples import (
    PORTFOLIO_BODY_EXAMPLES,
    RESP_ES,
    RESP_VAR,
    RESP_WHAT_IF,
    WHAT_IF_BODY_EXAMPLES,
)
from app.api.schemas import RiskQueryRequest
from app.domain.models import (
    ESContributionReport,
    Portfolio,
    VaRMethodology,
    VaRReport,
    WhatIfReport,
    WhatIfRequest,
)
from app.risk.historical_analytics import (
    HistoricalAnalyticsRequest,
    HistoricalAnalyticsResult,
)
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/risk", tags=["risk"])
router.include_router(dashboard_router)


@router.post("/summary")
def risk_summary(
    portfolio: Portfolio,
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
    service: PortfolioService = Depends(get_portfolio_service),
):
    if methodology is VaRMethodology.FULL_REVALUATION:
        reject_inline_heavy(route="POST /risk/summary")
    return service.summary(portfolio, methodology=methodology)


@router.post(
    "/historical-analytics",
    response_model=HistoricalAnalyticsResult,
    summary="Historical wealth, drawdown, Sharpe, and VaR/ES",
)
def historical_analytics(
    request: HistoricalAnalyticsRequest,
    service: PortfolioService = Depends(get_portfolio_service),
) -> HistoricalAnalyticsResult:
    """Deterministic analytics on a frozen dataset + portfolio/snapshot identity.

    Dual-mounted at ``/risk/historical-analytics`` and
    ``/api/v1/risk/historical-analytics``. Does not call market-data providers.
    """
    reject_inline_heavy(route="POST /risk/historical-analytics")
    try:
        return service.historical_analytics(request)
    except ValueError as exc:
        raise http_bad_request(exc) from exc


@router.post("/factors")
def risk_factors(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.factors(portfolio)


@router.post(
    "/var",
    response_model=VaRReport,
    summary="Historical / parametric VaR report",
    responses=RESP_VAR,
)
def risk_var(
    portfolio: Annotated[
        Portfolio,
        Body(openapi_examples=PORTFOLIO_BODY_EXAMPLES),
    ],
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
    service: PortfolioService = Depends(get_portfolio_service),
) -> VaRReport:
    reject_inline_heavy(route="POST /risk/var")
    return service.var_report(portfolio, methodology=methodology)


@router.post(
    "/es",
    response_model=ESContributionReport,
    summary="Expected Shortfall contributions",
    responses=RESP_ES,
)
def risk_es(
    portfolio: Annotated[
        Portfolio,
        Body(openapi_examples=PORTFOLIO_BODY_EXAMPLES),
    ],
    methodology: VaRMethodology = Query(default=VaRMethodology.DELTA_GAMMA),
    service: PortfolioService = Depends(get_portfolio_service),
) -> ESContributionReport:
    """Historical Expected Shortfall contributions by position / book / desk / strategy / factor (M2.5)."""
    reject_inline_heavy(route="POST /risk/es")
    return service.es_contributions(portfolio, methodology=methodology)


@router.post("/var/compare")
def risk_var_compare(
    portfolio: Portfolio,
    observations: int | None = Query(default=None, ge=1, le=5000),
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Compare LINEAR / DELTA_GAMMA / FULL_REVALUATION historical VaR (M2.4)."""
    reject_inline_heavy(route="POST /risk/var/compare")
    return service.compare_var_methodologies(portfolio, observations=observations)


@router.post(
    "/what-if",
    response_model=WhatIfReport,
    summary="Hypothetical trade what-if / incremental risk",
    responses=RESP_WHAT_IF,
)
def risk_what_if(
    request: Annotated[
        WhatIfRequest,
        Body(openapi_examples=WHAT_IF_BODY_EXAMPLES),
    ],
    methodology: VaRMethodology | None = Query(
        default=None,
        description="Optional override; defaults to request.methodology (DELTA_GAMMA).",
    ),
    service: PortfolioService = Depends(get_portfolio_service),
) -> WhatIfReport:
    """Hypothetical add/remove/modify without mutating persisted portfolio (M2.9).

    Mounted at ``/risk/what-if`` and ``/api/v1/risk/what-if`` (M7.2 dual-mount).
    """
    reject_inline_heavy(route="POST /risk/what-if")
    try:
        return service.what_if(request, methodology=methodology)
    except ValueError as exc:
        raise http_bad_request(exc) from exc


@router.post("/hierarchy")
def risk_hierarchy(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    reject_inline_heavy(route="POST /risk/hierarchy")
    return service.hierarchy(portfolio)


@router.post("/query")
def risk_query(
    request: RiskQueryRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    reject_inline_heavy(route="POST /risk/query")
    return service.query(request.portfolio, request.question)


@router.post("/contributors")
def risk_contributors(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    reject_inline_heavy(route="POST /risk/contributors")
    return service.contributors(portfolio)
