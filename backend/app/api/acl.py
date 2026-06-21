"""Shared-profile object ACLs (RF-014). Not OIDC / SSO / production IAM.

Local demo (unauthenticated loopback) skips these checks. Shared profile
stamps a Bearer-mapped principal and fail-closed IDOR on stored books/runs.
Seed/demo catalog books are owned by ``demo`` (readable; not writable by
other principals).
"""

from __future__ import annotations

from fastapi import Request

from app.api.auth import is_shared_deployment

DEMO_PRINCIPAL = "demo"


class PortfolioAccessDenied(PermissionError):
    """Caller is authenticated but not allowed to use this stored portfolio."""


def request_principal(request: Request) -> str | None:
    return getattr(request.state, "principal", None)


def allow_read(owner: str | None, principal: str | None) -> bool:
    if not is_shared_deployment():
        return True
    if principal is None or owner is None:
        return False
    if owner == DEMO_PRINCIPAL:
        return True
    return owner == principal


def allow_write(owner: str | None, principal: str | None) -> bool:
    if not is_shared_deployment():
        return True
    if principal is None or owner is None:
        return False
    return owner == principal


def allow_run_read(run_owner: str | None, principal: str | None) -> bool:
    if not is_shared_deployment():
        return True
    if principal is None or run_owner is None:
        return False
    return run_owner == principal
