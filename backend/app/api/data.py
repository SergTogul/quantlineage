"""Frozen public-history dataset routes (QuantLineage Wave A)."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from app.api.errors import error_payload
from app.api.instruments import _provider_http_error, get_history_provider, get_macro_provider
from app.market.history.artifact import (
    PUBLIC_HISTORY_CSV_ENV,
    PUBLIC_HISTORY_DIR_ENV,
    default_public_history_dir,
    resolve_public_history_csv,
    sidecar_path_for_csv,
)
from app.market.history.freeze import FreezeError, MissingRequiredFactorError, freeze_public_history
from app.market.history.spec import WAVE_A_DATASET_ID, WAVE_A_SPEC
from app.market.ingestion.errors import ProviderError
from app.market.ingestion.protocols import HistoricalDataProvider, MacroDataProvider
from app.market.quality import InsufficientAlignedHistoryError, SeriesValidationError

router = APIRouter(prefix="/data", tags=["data"])


class FreezeDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date


def public_history_output_dir() -> Path:
    """Directory for freeze writes. Tests point CSV/DIR env at tmp_path."""
    raw_csv = os.getenv(PUBLIC_HISTORY_CSV_ENV, "").strip()
    if raw_csv:
        path = Path(raw_csv).expanduser().resolve()
        parent = path.parent if path.suffix.lower() == ".csv" else path
        return parent
    raw_dir = os.getenv(PUBLIC_HISTORY_DIR_ENV, "").strip()
    if raw_dir:
        return Path(raw_dir).expanduser()
    return default_public_history_dir()


@router.post("/datasets")
def freeze_dataset(
    body: FreezeDatasetRequest,
    history_provider: HistoricalDataProvider = Depends(get_history_provider),
    macro_provider: MacroDataProvider = Depends(get_macro_provider),
):
    """Materialize Wave A public history. Returns id/version and CSV filename only."""
    if body.start > body.end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(
                code="bad_request", message="start must be on or before end", details=None
            ),
        )
    spec = replace(WAVE_A_SPEC, start=body.start, end=body.end)
    try:
        artifact = freeze_public_history(
            history_provider=history_provider,
            macro_provider=macro_provider,
            output_dir=public_history_output_dir(),
            spec=spec,
        )
    except InsufficientAlignedHistoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(
                code=exc.code,
                message=str(exc) or "Insufficient aligned history",
                details=None,
            ),
        ) from None
    except MissingRequiredFactorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(
                code=exc.code,
                message=str(exc) or "Missing required factor",
                details=None,
            ),
        ) from None
    except ProviderError as exc:
        raise _provider_http_error(exc) from None
    except SeriesValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(code=exc.code, message=str(exc) or "Invalid series", details=None),
        ) from None
    except FreezeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload(
                code=getattr(exc, "code", "freeze_failed"),
                message=str(exc) or "Freeze failed",
                details=None,
            ),
        ) from None
    return {
        "dataset_id": artifact.dataset_id,
        "dataset_version": artifact.dataset_version,
        "csv_path": artifact.csv_path.name,
    }


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, version: str | None = Query(default=None)):
    """Load a Wave A sidecar. ``version`` is the content hash of immutable bytes."""
    if dataset_id != WAVE_A_DATASET_ID:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_payload(code="not_found", message="Dataset not found", details=None),
        )
    try:
        csv_path = resolve_public_history_csv(dataset_version=version)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_payload(code="not_found", message="Dataset not found", details=None),
        ) from None
    sidecar = sidecar_path_for_csv(csv_path)
    if not sidecar.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_payload(code="not_found", message="Dataset not found", details=None),
        )
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if payload.get("dataset_id") != WAVE_A_DATASET_ID:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_payload(code="not_found", message="Dataset not found", details=None),
        )
    if version is not None and payload.get("dataset_version") != version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_payload(code="not_found", message="Dataset not found", details=None),
        )
    return payload
