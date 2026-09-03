"""M7.6: Deprecation / Sunset / Link headers on legacy (unversioned) API paths.

Canonical prefix is ``/api/v1`` (same as ``app.main.API_V1_PREFIX``). Dual-mount
remains until the published sunset date and client migration — see
``docs/api/v1_canonical_and_legacy_sunset.md``.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Keep in sync with ``app.main.API_V1_PREFIX`` (no import — avoids cycle).
API_V1_PREFIX = "/api/v1"

# RFC 8594 Sunset; Deprecation: true (RFC 9745-style).
# Planned removal target (not an automatic cut-over): see sunset doc.
LEGACY_SUNSET_HTTP_DATE = "Tue, 02 Mar 2027 00:00:00 GMT"
LEGACY_DEPRECATION_VALUE = "true"

# Dual-mounted public API roots (M7.2). Docs/OpenAPI/static are excluded.
_LEGACY_API_ROOTS = (
    "/health",
    "/portfolio",
    "/portfolios",
    "/market",
    "/risk",
)


def is_legacy_api_path(path: str) -> bool:
    """True for unversioned dual-mounted API paths (not ``/api/v1/...``)."""
    if path.startswith(API_V1_PREFIX + "/") or path == API_V1_PREFIX:
        return False
    for root in _LEGACY_API_ROOTS:
        if path == root or path.startswith(root + "/"):
            return True
    return False


def successor_version_path(path: str) -> str:
    """Map a legacy path to its canonical ``/api/v1`` counterpart."""
    if path.startswith(API_V1_PREFIX):
        return path
    return f"{API_V1_PREFIX}{path}"


def apply_legacy_deprecation_headers(path: str, response: Response) -> None:
    """Attach Deprecation / Sunset / Link on legacy responses only."""
    if not is_legacy_api_path(path):
        return
    successor = successor_version_path(path)
    response.headers["Deprecation"] = LEGACY_DEPRECATION_VALUE
    response.headers["Sunset"] = LEGACY_SUNSET_HTTP_DATE
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'


class LegacyDeprecationMiddleware(BaseHTTPMiddleware):
    """Annotate legacy dual-mount responses; leave ``/api/v1`` and non-API alone."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        apply_legacy_deprecation_headers(request.url.path, response)
        return response
