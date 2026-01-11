"""Consistent API error payload ``{code, message, details}`` (M7.5).

Handlers are registered once on the FastAPI app so legacy and ``/api/v1``
mounts share the same shape. Successful response schemas are unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Stable machine-readable codes for common HTTP statuses.
_STATUS_TO_CODE: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
    status.HTTP_501_NOT_IMPLEMENTED: "not_implemented",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}


class ErrorBody(BaseModel):
    """Standard error envelope returned by all HTTP error handlers."""

    code: str = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Human-readable summary")
    details: dict[str, Any] | list[Any] | None = Field(
        default=None,
        description="Optional structured context (validation errors, etc.)",
    )


def code_for_status(status_code: int) -> str:
    """Map an HTTP status to a default ``code`` string."""
    return _STATUS_TO_CODE.get(status_code, f"http_{status_code}")


def error_payload(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable ``{code, message, details}`` dict."""
    return ErrorBody(code=code, message=message, details=details).model_dump()


def _from_structured_detail(detail: dict[str, Any], status_code: int) -> ErrorBody:
    """Interpret ``HTTPException.detail`` when callers pass a dict."""
    code = detail.get("code")
    message = detail.get("message")
    details = detail.get("details")
    if isinstance(code, str) and isinstance(message, str):
        if details is not None and not isinstance(details, (dict, list)):
            details = {"value": details}
        return ErrorBody(code=code, message=message, details=details)
    # Non-conforming dict: keep as details, synthesize message/code.
    return ErrorBody(
        code=code_for_status(status_code),
        message="Request failed",
        details=detail,
    )


def body_from_http_exception(exc: HTTPException | StarletteHTTPException) -> ErrorBody:
    """Normalize FastAPI/Starlette ``HTTPException`` into ``ErrorBody``."""
    detail = exc.detail
    status_code = int(exc.status_code)

    if isinstance(detail, dict):
        return _from_structured_detail(detail, status_code)

    if isinstance(detail, list):
        return ErrorBody(
            code=code_for_status(status_code),
            message="Request failed",
            details=detail,
        )

    if detail is None:
        message = code_for_status(status_code).replace("_", " ")
    else:
        message = str(detail)

    return ErrorBody(
        code=code_for_status(status_code),
        message=message,
        details=None,
    )


def body_from_validation_error(exc: RequestValidationError) -> ErrorBody:
    """Map Pydantic/FastAPI request validation failures to ``ErrorBody``."""
    return ErrorBody(
        code="validation_error",
        message="Request validation failed",
        details={"errors": exc.errors()},
    )


def body_internal_error() -> ErrorBody:
    """Opaque 500 body — never leak exception strings to clients."""
    return ErrorBody(
        code="internal_error",
        message="An unexpected error occurred",
        details=None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach centralized handlers so every mount shares the error shape."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        body = body_from_http_exception(exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        body = body_from_http_exception(exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = body_from_validation_error(exc)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=body.model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled API exception: %s", exc)
        body = body_internal_error()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=body.model_dump(),
        )
