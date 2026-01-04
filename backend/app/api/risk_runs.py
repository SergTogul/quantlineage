"""Async risk-run HTTP routes (M5.4).

Dual-mounted at ``/risk/runs`` and ``/api/v1/risk/runs`` (M7.2).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.api.deps import get_risk_run_worker
from app.api.openapi_examples import (
    RESP_RISK_RUN_CREATE,
    RESP_RISK_RUN_GET,
    RISK_RUN_CREATE_BODY_EXAMPLES,
)
from app.domain.models import RiskRunCreateRequest, RiskRunView
from app.services.risk_run_service import RiskRunNotFound
from app.services.risk_run_worker import RiskRunWorker

router = APIRouter(tags=["risk-runs"])


@router.post(
    "/runs",
    response_model=RiskRunView,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue an async risk computation",
    response_description="Run accepted; poll GET /risk/runs/{id} for status/results.",
    responses=RESP_RISK_RUN_CREATE,
)
def create_risk_run(
    body: Annotated[
        RiskRunCreateRequest,
        Body(openapi_examples=RISK_RUN_CREATE_BODY_EXAMPLES),
    ],
    worker: RiskRunWorker = Depends(get_risk_run_worker),
) -> RiskRunView:
    """Create a QUEUED risk run and execute it on an in-process worker thread.

    Available at ``/risk/runs`` and ``/api/v1/risk/runs`` (M7.2 dual-mount).
    Persistence: in-memory by default; SQLAlchemy when RISKFORGE_DATABASE_URL
    is set at app lifespan (M5.6). When RISKFORGE_EXTERNAL_WORKER=1 (Compose
    backend), the run stays QUEUED until ``python -m app.worker`` polls it (M5.7).
    """
    try:
        return worker.submit(
            portfolio=body.portfolio,
            run_type=body.run_type,
            request=body.request,
            market_snapshot_id=body.market_snapshot_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/runs/{run_id}",
    response_model=RiskRunView,
    summary="Get risk-run status and results",
    responses=RESP_RISK_RUN_GET,
)
def get_risk_run(
    run_id: str,
    worker: RiskRunWorker = Depends(get_risk_run_worker),
) -> RiskRunView:
    try:
        return worker.get(run_id)
    except RiskRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"risk run not found: {run_id}",
        ) from exc
