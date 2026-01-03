"""Portfolio routes (M7.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_default_portfolio
from app.domain.models import Portfolio

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=Portfolio)
def portfolio(portfolio: Portfolio = Depends(get_default_portfolio)) -> Portfolio:
    """Demo portfolio: SQLAlchemy when RISKFORGE_DATABASE_URL set, else SAMPLE."""
    return portfolio
