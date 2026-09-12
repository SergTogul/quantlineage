"""Market snapshot routes (M7.1) plus QuantLineage history/public snapshot."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_market_snapshot_repository, get_portfolio_service
from app.api.errors import error_payload
from app.api.instruments import (
    MAX_HISTORY_RANGE_DAYS,
    _fetch_catalog_series,
    _provider_http_error,
    get_history_provider,
    get_macro_provider,
    parse_start_end,
)
from app.api.schemas import RatesShowcaseView
from app.domain.models import Portfolio, as_of_wire
from app.market.catalog import get_catalog_record
from app.market.history.snapshot import (
    MissingPublicSnapshotMarkError,
    PublicSnapshotError,
    StalePublicSnapshotError,
    build_public_snapshot,
    persist_public_snapshot,
)
from app.market.ingestion.errors import ProviderError
from app.market.ingestion.protocols import HistoricalDataProvider, MacroDataProvider
from app.market.quality import SeriesLineage, SeriesValidationError, validate_series
from app.persistence.repositories import MarketSnapshotRepository
from app.risk.rates_showcase import build_rates_showcase
from app.sample import RATES_MACRO_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/market", tags=["market"])


class HistoryPointOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_date: date
    value: float


class InstrumentHistoryOut(SeriesLineage):
    points: list[HistoryPointOut] = Field(default_factory=list)


class PublicSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date


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


@router.get("/history/{instrument_id}", response_model=InstrumentHistoryOut)
def get_market_history(
    instrument_id: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    history_provider: HistoricalDataProvider = Depends(get_history_provider),
    macro_provider: MacroDataProvider = Depends(get_macro_provider),
) -> InstrumentHistoryOut:
    """Normalized levels plus lineage. Does not compute returns or convert FRED percent."""
    start_date, end_date = parse_start_end(start, end, max_days=MAX_HISTORY_RANGE_DAYS)
    record = get_catalog_record(instrument_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_payload(code="not_found", message="Instrument not found", details=None),
        )
    try:
        series = _fetch_catalog_series(
            record,
            start=start_date,
            end=end_date,
            history_provider=history_provider,
            macro_provider=macro_provider,
        )
        if not series.points:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_payload(code="not_found", message="No history", details=None),
            )
        lineage = validate_series(series, requested_end=end_date)
    except HTTPException:
        raise
    except ProviderError as exc:
        raise _provider_http_error(exc) from None
    except SeriesValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(code=exc.code, message="Invalid series", details=None),
        ) from None
    return InstrumentHistoryOut(
        **lineage.model_dump(),
        points=[
            HistoryPointOut(observation_date=point.observation_date, value=point.value)
            for point in series.points
        ],
    )


@router.post("/snapshots/from-public-data")
def snapshot_from_public_data(
    body: PublicSnapshotRequest,
    history_provider: HistoricalDataProvider = Depends(get_history_provider),
    macro_provider: MacroDataProvider = Depends(get_macro_provider),
    repo: MarketSnapshotRepository = Depends(get_market_snapshot_repository),
):
    """Build and persist a Wave A public snapshot. Fails closed on stale marks."""
    try:
        built = build_public_snapshot(
            as_of=body.as_of,
            history_provider=history_provider,
            macro_provider=macro_provider,
        )
    except StalePublicSnapshotError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(
                code=exc.code,
                message=str(exc) or "Stale observation",
                details=None,
            ),
        ) from None
    except MissingPublicSnapshotMarkError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(
                code=exc.code,
                message=str(exc) or "Missing required mark",
                details=None,
            ),
        ) from None
    except ProviderError as exc:
        raise _provider_http_error(exc) from None
    except PublicSnapshotError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(
                code=getattr(exc, "code", "public_snapshot_failed"),
                message=str(exc) or "Public snapshot failed",
                details=None,
            ),
        ) from None
    persist_public_snapshot(repo, built)
    snapshot = built.snapshot
    return {
        "id": snapshot.id,
        "as_of": as_of_wire(snapshot.as_of),
        "content_hash": snapshot.content_hash(),
        "lineage": built.lineage,
    }


@router.get("/snapshots/{snapshot_id}")
def get_market_snapshot(
    snapshot_id: str,
    repo: MarketSnapshotRepository = Depends(get_market_snapshot_repository),
):
    stored = repo.get(snapshot_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_payload(code="not_found", message="Snapshot not found", details=None),
        )
    return stored.model_dump(mode="json")
