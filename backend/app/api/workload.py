"""HTTP workload caps so clients cannot submit pathological books/payloads.

R0.11.3 / RF-014. Env-overridable with safe local defaults:

- ``RISKFORGE_MAX_POSITIONS=500``
- ``RISKFORGE_MAX_SCENARIOS=50``
- ``RISKFORGE_MAX_REQUEST_BYTES=1048576`` (1 MiB)

Byte cap runs as pure ASGI middleware (``WorkloadBodyLimitMiddleware``) on the
receive stream **before** FastAPI reads a Pydantic body. ``Content-Length`` is
pre-checked; missing/chunked bodies are accumulated with a running total and
aborted after the first oversize chunk. The capped body is cached and replayed
so later ``request.body()`` does not re-read the client stream.

A FastAPI dependency (registered in ``app.main``) still walks parsed JSON for
``positions`` / ``scenarios`` lists and what-if ``add`` mutations that grow a
book. Rejection is HTTP 413 with the existing ``{code, message, details}``
envelope via ``app.api.errors.error_payload``.

Observation query ``le=5000`` on ``POST /risk/var/compare`` is unchanged
(owned by ``app.api.risk``). Reverse-stress iteration defaults are not touched.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import HTTPException, Request, status
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_payload

DEFAULT_MAX_POSITIONS = 500
DEFAULT_MAX_SCENARIOS = 50
DEFAULT_MAX_REQUEST_BYTES = 1_048_576
MAX_JSON_DEPTH = 64

ENV_MAX_POSITIONS = "RISKFORGE_MAX_POSITIONS"
ENV_MAX_SCENARIOS = "RISKFORGE_MAX_SCENARIOS"
ENV_MAX_REQUEST_BYTES = "RISKFORGE_MAX_REQUEST_BYTES"

PAYLOAD_TOO_LARGE = "payload_too_large"
MESSAGE_POSITIONS = "Request exceeds maximum positions"
MESSAGE_SCENARIOS = "Request exceeds maximum scenarios"
MESSAGE_BODY = "Request body exceeds maximum size"
MESSAGE_NESTING = "Request JSON exceeds maximum nesting depth"


class WorkloadLimitExceeded(ValueError):
    """Parsed payload exceeded a configured positions/scenarios/nesting cap."""

    def __init__(self, field: str, actual: int, limit: int) -> None:
        self.field = field
        self.actual = actual
        self.limit = limit
        super().__init__(self.message)

    @property
    def message(self) -> str:
        if self.field == "positions":
            return MESSAGE_POSITIONS
        if self.field == "scenarios":
            return MESSAGE_SCENARIOS
        if self.field == "nesting":
            return MESSAGE_NESTING
        return MESSAGE_BODY

    @property
    def details(self) -> dict[str, int | str]:
        return {"field": self.field, "limit": self.limit, "actual": self.actual}


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return value if value > 0 else default


def max_positions() -> int:
    return _positive_int(ENV_MAX_POSITIONS, DEFAULT_MAX_POSITIONS)


def max_scenarios() -> int:
    return _positive_int(ENV_MAX_SCENARIOS, DEFAULT_MAX_SCENARIOS)


def max_request_bytes() -> int:
    return _positive_int(ENV_MAX_REQUEST_BYTES, DEFAULT_MAX_REQUEST_BYTES)


def _add_with_position_count(changes: list[Any]) -> int:
    """Count ``add`` ops that carry a position object (work that becomes a position)."""
    n = 0
    for change in changes:
        if (
            isinstance(change, dict)
            and change.get("operation") == "add"
            and isinstance(change.get("position"), dict)
        ):
            n += 1
    return n


def _positions_for_changes(obj: dict[str, Any]) -> list[Any] | None:
    """Positions list paired with a ``changes`` list (siblings or what-if portfolio)."""
    positions = obj.get("positions")
    if isinstance(positions, list):
        return positions
    portfolio = obj.get("portfolio")
    if isinstance(portfolio, dict):
        nested = portfolio.get("positions")
        if isinstance(nested, list):
            return nested
    return None


def _iter_dicts(payload: Any, *, max_depth: int = MAX_JSON_DEPTH) -> Any:
    """Yield dict nodes iteratively; reject past ``max_depth`` instead of recursing."""
    stack: list[tuple[Any, int]] = [(payload, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > max_depth:
            raise WorkloadLimitExceeded("nesting", depth, max_depth)
        if isinstance(node, dict):
            yield node
            for child in node.values():
                stack.append((child, depth + 1))
        elif isinstance(node, list):
            for child in node:
                stack.append((child, depth + 1))


def enforce_parsed_payload(
    payload: Any,
    *,
    max_positions: int,
    max_scenarios: int,
) -> None:
    """Raise ``WorkloadLimitExceeded`` when a parsed body exceeds list caps."""
    if isinstance(payload, list) and len(payload) > max_scenarios:
        raise WorkloadLimitExceeded("scenarios", len(payload), max_scenarios)
    for obj in _iter_dicts(payload):
        positions = obj.get("positions")
        if isinstance(positions, list) and len(positions) > max_positions:
            raise WorkloadLimitExceeded("positions", len(positions), max_positions)
        scenarios = obj.get("scenarios")
        if isinstance(scenarios, list) and len(scenarios) > max_scenarios:
            raise WorkloadLimitExceeded("scenarios", len(scenarios), max_scenarios)
        changes = obj.get("changes")
        if not isinstance(changes, list):
            continue
        book = _positions_for_changes(obj)
        if book is None:
            continue
        computed = len(book) + _add_with_position_count(changes)
        if computed > max_positions:
            raise WorkloadLimitExceeded("positions", computed, max_positions)


def workload_http_exception(*, message: str, details: dict[str, Any]) -> HTTPException:
    """413 with the shared ``{code, message, details}`` envelope."""
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=error_payload(
            code=PAYLOAD_TOO_LARGE,
            message=message,
            details=details,
        ),
    )


def _raise_body_too_large(*, limit: int, actual: int) -> None:
    raise workload_http_exception(
        message=MESSAGE_BODY,
        details={"field": "body", "limit": limit, "actual": actual},
    )


def body_too_large_response(*, limit: int, actual: int) -> JSONResponse:
    """413 envelope used by the ASGI middleware (outside FastAPI handlers)."""
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content=error_payload(
            code=PAYLOAD_TOO_LARGE,
            message=MESSAGE_BODY,
            details={"field": "body", "limit": limit, "actual": actual},
        ),
    )


def _declared_content_length(scope: Scope) -> int | None:
    raw = Headers(scope=scope).get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _cache_body_capped(
    receive: Receive, byte_limit: int
) -> tuple[bytes | None, int | None]:
    """Pull ASGI body chunks until complete or over the cap.

    On overflow returns ``(None, running_total)`` and does not call ``receive``
    again (tail is not retained). Under the cap returns ``(cached, None)``.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return b"".join(chunks), None
        if message["type"] != "http.request":
            continue
        incoming = len(message.get("body", b""))
        next_total = total + incoming
        if next_total > byte_limit:
            return None, next_total
        total = next_total
        body = message.get("body", b"")
        if body:
            chunks.append(body)
        if not message.get("more_body", False):
            return b"".join(chunks), None


def _replay_receive(cached: bytes, receive: Receive) -> Receive:
    """Replay the capped body once, then forward later ASGI events."""
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": cached, "more_body": False}
        return await receive()

    return replay


class WorkloadBodyLimitMiddleware:
    """Pure ASGI middleware: byte cap on ``receive``, in front of Pydantic."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        byte_limit = max_request_bytes()
        declared = _declared_content_length(scope)
        if declared is not None and declared > byte_limit:
            response = body_too_large_response(limit=byte_limit, actual=declared)
            await response(scope, receive, send)
            return

        if scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        cached, overflow = await _cache_body_capped(receive, byte_limit)
        if overflow is not None:
            response = body_too_large_response(limit=byte_limit, actual=overflow)
            await response(scope, receive, send)
            return

        assert cached is not None
        await self.app(scope, _replay_receive(cached, receive), send)


async def _read_body_capped(request: Request, byte_limit: int) -> bytes:
    """Stream the ASGI body with a running total; abort without buffering the tail."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        incoming = len(chunk)
        next_total = total + incoming
        if next_total > byte_limit:
            _raise_body_too_large(limit=byte_limit, actual=next_total)
        total = next_total
        if chunk:
            chunks.append(chunk)
    body = b"".join(chunks)
    # Cache so later ``request.body()`` / JSON parsing do not re-read the stream.
    request._body = body
    return body


async def enforce_workload_limits(request: Request) -> None:
    """App-wide dependency: reject oversized bodies and pathological lists."""
    byte_limit = max_request_bytes()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = -1
        if declared > byte_limit:
            _raise_body_too_large(limit=byte_limit, actual=declared)

    if request.method not in {"POST", "PUT", "PATCH"}:
        return

    body = await _read_body_capped(request, byte_limit)
    if not body:
        return

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return

    try:
        enforce_parsed_payload(
            parsed,
            max_positions=max_positions(),
            max_scenarios=max_scenarios(),
        )
    except WorkloadLimitExceeded as exc:
        raise workload_http_exception(message=exc.message, details=exc.details) from exc
