"""Limit status and drill-down routes (M7.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.api.backpressure import reject_inline_heavy
from app.api.deps import get_portfolio_service
from app.api.errors import http_bad_request
from app.api.openapi_examples import LIMITS_DRILLDOWN_BODY_EXAMPLES, RESP_LIMITS_DRILLDOWN
from app.api.schemas import LimitDrilldownRequest
from app.domain.models import LimitDrilldownReport, Portfolio
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/risk", tags=["limits"])


@router.post("/limits")
def risk_limits(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    reject_inline_heavy(route="POST /risk/limits")
    return service.limits(portfolio)


@router.post(
    "/limits/drilldown",
    response_model=LimitDrilldownReport,
    summary="Limit breach drill-down",
    responses=RESP_LIMITS_DRILLDOWN,
)
def risk_limits_drilldown(
    request: Annotated[
        LimitDrilldownRequest,
        Body(openapi_examples=LIMITS_DRILLDOWN_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> LimitDrilldownReport:
    """Limit breach drill-down: hierarchy node, metric, utilization, top contributors (M4.6)."""
    try:
        return service.limit_drilldown(
            portfolio=request.portfolio,
            metric=request.metric,
            hierarchy=request.hierarchy,
            limits=request.limits,
            top_n=request.top_n,
            breaches_only=request.breaches_only,
        )
    except ValueError as exc:
        raise http_bad_request(exc) from exc
