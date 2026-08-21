"""Market snapshot routes (M7.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_portfolio_service
from app.api.schemas import RatesShowcaseView
from app.domain.models import Portfolio
from app.risk.rates_showcase import build_rates_showcase
from app.sample import RATES_MACRO_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/market", tags=["market"])


@router.post("/snapshot")
def market_snapshot(
    portfolio: Portfolio,
    service: PortfolioService = Depends(get_portfolio_service),
):
    return service.market_snapshot(portfolio)


@router.get(
    "/rates-showcase",
    response_model=RatesShowcaseView,
    summary="USD rates-macro curve nodes and key-rate DV01",
)
def rates_showcase(
    service: PortfolioService = Depends(get_portfolio_service),
) -> RatesShowcaseView:
    """Demo SOFR/OIS-style curve + SensitivityEngine KR-DV01. Not production multi-curve."""
    book = RATES_MACRO_PORTFOLIO
    market = demo_market_snapshot(book)
    return RatesShowcaseView.model_validate(
        build_rates_showcase(book, market, service.pricing)
    )
