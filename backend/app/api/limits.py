"""Limit status and drill-down routes (M7.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_portfolio_service
from app.domain.models import LimitDrilldownRequest, Portfolio
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/risk", tags=["limits"])


@router.post("/limits")
def risk_limits(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.limits(portfolio)


@router.post("/limits/drilldown")
def risk_limits_drilldown(
    request: LimitDrilldownRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Limit breach drill-down: hierarchy node, metric, utilization, top contributors (M4.6)."""
    try:
        return service.limit_drilldown(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
