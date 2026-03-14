"""Shared-deployment token gate (R0.11.5 / RF-014).

Local demo (loopback bind, default Compose) stays unauthenticated.

A shared / non-loopback profile is active when ``RISKFORGE_SHARED_DEPLOYMENT``
is truthy or ``RISKFORGE_BIND`` is set to an address outside
``{127.0.0.1, localhost, ::1}``. That profile fails closed without
``RISKFORGE_API_TOKEN`` and rejects unauthenticated API requests with 401.

This is a single shared-secret Bearer gate, not production IAM (no OIDC,
SSO, object ACLs, or in-process TLS).
"""

from __future__ import annotations

import hmac
import os
from typing import Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import error_payload

ENV_SHARED_DEPLOYMENT = "RISKFORGE_SHARED_DEPLOYMENT"
ENV_API_TOKEN = "RISKFORGE_API_TOKEN"
ENV_BIND = "RISKFORGE_BIND"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})

UNAUTHORIZED_MESSAGE = "Authentication required"
BOOT_ERROR = (
    "Shared/non-loopback deployment requires RISKFORGE_API_TOKEN. "
    "Local demo (loopback bind, default Compose) stays unauthenticated. "
    "This token gate is not production IAM."
)

_PUBLIC_EXACT = frozenset(
    {
        "/health",
        "/api/v1/health",
        "/openapi.json",
        "/docs",
        "/docs/",
        "/redoc",
        "/redoc/",
        "/docs/oauth2-redirect",
    }
)
_PUBLIC_PREFIXES = ("/docs/", "/redoc/")


def _env_flag(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in _TRUTHY


def _normalize_bind_host(raw: str) -> str:
    text = raw.strip()
    if text.startswith("[") and "]" in text:
        return text[1 : text.index("]")]
    if text.count(":") == 1 and not text.startswith(":"):
        host, maybe_port = text.rsplit(":", 1)
        if maybe_port.isdigit():
            return host
    return text


def is_loopback_bind(raw: str | None) -> bool:
    """Unset / blank bind is the local default (loopback)."""
    if raw is None or not str(raw).strip():
        return True
    host = _normalize_bind_host(str(raw)).strip().lower()
    return host in LOOPBACK_HOSTS


def configured_bind() -> str:
    return os.environ.get(ENV_BIND, "").strip()


def is_shared_deployment() -> bool:
    if _env_flag(ENV_SHARED_DEPLOYMENT):
        return True
    bind = configured_bind()
    return bool(bind) and not is_loopback_bind(bind)


def api_token() -> str | None:
    raw = os.environ.get(ENV_API_TOKEN)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def require_shared_auth_configured() -> None:
    """Fail closed at process start when a shared profile has no token."""
    if not is_shared_deployment():
        return
    if api_token() is None:
        raise RuntimeError(BOOT_ERROR)


def is_public_path(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def _extract_bearer(header: str | None) -> str | None:
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _bearer_matches(header: str | None, expected: str) -> bool:
    presented = _extract_bearer(header)
    if presented is None:
        return False
    return hmac.compare_digest(presented, expected)


def _unauthorized_response() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=error_payload(code="unauthorized", message=UNAUTHORIZED_MESSAGE),
        headers={"WWW-Authenticate": "Bearer"},
    )


class SharedTokenMiddleware:
    """Require Bearer token on non-public routes when the shared profile is on."""

    def __init__(self, app: ASGIApp, *, public_methods: Iterable[str] = ("OPTIONS",)) -> None:
        self.app = app
        self.public_methods = frozenset(method.upper() for method in public_methods)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not is_shared_deployment():
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method") or "")
        path = str(scope.get("path") or "")
        if method.upper() in self.public_methods or is_public_path(path):
            await self.app(scope, receive, send)
            return

        token = api_token()
        if token is None:
            await _unauthorized_response()(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if not _bearer_matches(headers.get("authorization"), token):
            await _unauthorized_response()(scope, receive, send)
            return

        await self.app(scope, receive, send)
