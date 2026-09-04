"""Coherent dashboard batch (R0.10.2 / RF-015).

One POST returns the keys ``loadDashboard`` already consumes. The service
calls existing PortfolioService methods sequentially; this is not a RiskRun
job platform and does not move work off the request thread.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from app.api.deps import (
    get_baseline_stress_scenarios,
    get_default_portfolio,
    get_default_stress_scenarios,
    get_portfolio_service,
)
from app.domain.models import (
    AttributionReport,
    Contributor,
    HierarchyNode,
    LimitResult,
    Portfolio,
    RiskFactorExposure,
    RiskSummary,
    ScenarioEvaluationReport,
    StressResult,
    StressScenario,
    VaRReport,
)
from app.services.portfolio_service import PortfolioService

router = APIRouter()


class DashboardBatchResponse(BaseModel):
    """Wire shape for POST /risk/dashboard — keys match frontend loadDashboard."""

    portfolio: Portfolio
    summary: RiskSummary
    stress: list[StressResult]
    threats: ScenarioEvaluationReport
    contributors: list[Contributor]
    limits: list[LimitResult]
    factors: list[RiskFactorExposure]
    varReport: VaRReport
    hierarchy: HierarchyNode
    attribution: AttributionReport


@router.post(
    "/dashboard",
    response_model=DashboardBatchResponse,
    summary="Coherent dashboard batch",
)
def risk_dashboard(
    portfolio: Annotated[Portfolio | None, Body()] = None,
    default_portfolio: Portfolio = Depends(get_default_portfolio),
    baseline: list[StressScenario] = Depends(get_baseline_stress_scenarios),
    threat_scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
    service: PortfolioService = Depends(get_portfolio_service),
) -> DashboardBatchResponse:
    """Compute the demo dashboard slices in one request.

    Body is an optional ``Portfolio``. Omit or send JSON ``null`` to use the
    default demo book (same as ``GET /portfolio``). Dual-mounted at
    ``/risk/dashboard`` and ``/api/v1/risk/dashboard``.
    """
    book = portfolio if portfolio is not None else default_portfolio
    return DashboardBatchResponse.model_validate(
        service.dashboard(
            book,
            scenarios=baseline,
            threat_scenarios=threat_scenarios,
        )
    )
