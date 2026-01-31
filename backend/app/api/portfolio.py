"""Portfolio routes (M7.1; M10.1 demo catalog)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_default_portfolio
from app.domain.models import Portfolio
from app.sample import DemoPortfolioSummary, demo_portfolio_summaries, get_demo_portfolio

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=Portfolio)
def portfolio(portfolio: Portfolio = Depends(get_default_portfolio)) -> Portfolio:
    """Default demo portfolio: SQLAlchemy when RISKFORGE_DATABASE_URL set, else SAMPLE."""
    return portfolio


@router.get("/portfolios", response_model=list[DemoPortfolioSummary])
def list_demo_portfolios() -> list[DemoPortfolioSummary]:
    """Catalog of themed in-code demo books (M10.1). No live market feeds."""
    return demo_portfolio_summaries()


@router.get("/portfolios/{portfolio_id}", response_model=Portfolio)
def get_named_demo_portfolio(portfolio_id: str) -> Portfolio:
    """Return one themed demo portfolio by id (equity-vol / rates-macro / global-macro)."""
    found = get_demo_portfolio(portfolio_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "demo_portfolio_not_found",
                "message": f"unknown demo portfolio id: {portfolio_id}",
                "details": {"portfolio_id": portfolio_id},
            },
        )
    return found
