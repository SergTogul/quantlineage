"""Coherent dashboard batch (R0.10.2 / RF-015).

One POST returns the keys ``loadDashboard`` already consumes. The service
calls existing PortfolioService methods sequentially; this is not a RiskRun
job platform. R0.10.3 refuses that inline compute when an external worker
is configured (see ``app.api.backpressure``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from app.api.backpressure import reject_inline_heavy
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
    VaRReport,
)
from app.risk.scenario_model import Scenario
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
    baseline: list[Scenario] = Depends(get_baseline_stress_scenarios),
    threat_scenarios: list[Scenario] = Depends(get_default_stress_scenarios),
    service: PortfolioService = Depends(get_portfolio_service),
) -> DashboardBatchResponse:
    """Compute the demo dashboard slices in one request.

    Body is an optional ``Portfolio``. Omit or send JSON ``null`` to use the
    default demo book (same as ``GET /portfolio``). Dual-mounted at
    ``/risk/dashboard`` and ``/api/v1/risk/dashboard``.

    When ``RISKFORGE_EXTERNAL_WORKER=1`` or ``RISKFORGE_HEAVY_INLINE=0``,
    this HEAVY batch refuses request-thread compute (R0.10.3) and points
    clients at ``POST /risk/runs``.
    """
    reject_inline_heavy(route="POST /risk/dashboard")
    book = portfolio if portfolio is not None else default_portfolio
    return DashboardBatchResponse.model_validate(
        service.dashboard(
            book,
            scenarios=baseline,
            threat_scenarios=threat_scenarios,
        )
    )
