"""P&L and risk-change attribution routes (M7.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_portfolio_service
from app.domain.models import AttributionRequest, Portfolio, RiskChangeAttributionRequest
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/risk", tags=["attribution"])


@router.post("/attribution")
def risk_attribution(
    request: AttributionRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.attribution(request)


@router.post("/attribution/demo")
def risk_attribution_demo(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.demo_attribution(portfolio)


@router.post("/change-attribution")
def risk_change_attribution(
    request: RiskChangeAttributionRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Risk-metric change waterfall (VaR/ES drivers) — separate from P&L Explain (M4.4)."""
    return service.risk_change_attribution(request)
