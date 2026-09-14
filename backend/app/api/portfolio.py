"""Portfolio routes (M7.1; M10.1 demo catalog; RF-014 stored ACLs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.acl import allow_read, allow_write, request_principal
from app.api.deps import get_db_session, get_default_portfolio
from app.api.errors import http_forbidden
from app.domain.models import Portfolio
from app.persistence.repositories import (
    PortfolioNotFound,
    PortfolioVersionConflict,
)
from app.persistence.sqlalchemy_repos import SqlAlchemyPortfolioRepository
from app.sample import DemoPortfolioSummary, demo_portfolio_summaries, get_demo_portfolio

router = APIRouter(tags=["portfolio"])


def _demo_not_found(portfolio_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "demo_portfolio_not_found",
            "message": f"unknown demo portfolio id: {portfolio_id}",
            "details": {"portfolio_id": portfolio_id},
        },
    )


@router.get("/portfolio", response_model=Portfolio)
def portfolio(portfolio: Portfolio = Depends(get_default_portfolio)) -> Portfolio:
    """Default demo portfolio: SQLAlchemy when QUANTLINEAGE_DATABASE_URL set, else SAMPLE."""
    return portfolio


@router.get("/portfolios", response_model=list[DemoPortfolioSummary])
def list_demo_portfolios() -> list[DemoPortfolioSummary]:
    """Catalog of themed in-code demo books (M10.1). No live market feeds.

    Read-only catalog: not object-ACL gated. Seed rows in persistence are owned
    by principal ``demo``.
    """
    return demo_portfolio_summaries()


@router.get("/portfolios/{portfolio_id}", response_model=Portfolio)
def get_named_demo_portfolio(
    portfolio_id: str,
    request: Request,
    session: Session | None = Depends(get_db_session),
) -> Portfolio:
    """Return a themed demo book (read-only catalog) or a stored book (ACL)."""
    found = get_demo_portfolio(portfolio_id)
    if found is not None:
        return found
    if session is None:
        raise _demo_not_found(portfolio_id)
    repo = SqlAlchemyPortfolioRepository(session)
    stored = repo.get(portfolio_id)
    if stored is None:
        raise _demo_not_found(portfolio_id)
    if not allow_read(repo.get_owner(portfolio_id), request_principal(request)):
        raise http_forbidden()
    return stored


@router.put("/portfolios/{portfolio_id}", response_model=Portfolio)
def update_stored_portfolio(
    portfolio_id: str,
    body: Portfolio,
    request: Request,
    session: Session | None = Depends(get_db_session),
) -> Portfolio:
    """Replace a stored portfolio. Shared profile: owner-only (403 otherwise)."""
    if body.id != portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "bad_request",
                "message": "portfolio id in path and body must match",
                "details": {"path_id": portfolio_id, "body_id": body.id},
            },
        )
    if session is None:
        raise _demo_not_found(portfolio_id)
    repo = SqlAlchemyPortfolioRepository(session)
    stored = repo.get(portfolio_id)
    if stored is None:
        raise _demo_not_found(portfolio_id)
    if not allow_write(repo.get_owner(portfolio_id), request_principal(request)):
        raise http_forbidden()
    try:
        return repo.update(body)
    except PortfolioNotFound as exc:
        raise _demo_not_found(portfolio_id) from exc
    except PortfolioVersionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "conflict",
                "message": "portfolio version conflict",
                "details": {
                    "portfolio_id": exc.portfolio_id,
                    "expected": exc.expected,
                    "actual": exc.actual,
                },
            },
        ) from exc
