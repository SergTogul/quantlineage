"""Market snapshot routes (M7.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_portfolio_service
from app.domain.models import Portfolio
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/market", tags=["market"])


@router.post("/snapshot")
def market_snapshot(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.market_snapshot(portfolio)
