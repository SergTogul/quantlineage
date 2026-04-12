"""Request-thread backpressure for HEAVY inline risk (R0.10.3 / RF-015 leftover).

When a production-shaped deploy has an external worker
(``RISKFORGE_EXTERNAL_WORKER=1``) or explicitly disables inline heavy
compute (``RISKFORGE_HEAVY_INLINE=0``), HEAVY handlers refuse
FULL_REVALUATION summary and dashboard compute on the FastAPI request
thread and point clients at ``POST /risk/runs``.

This is not a job platform: it does not enqueue work. Workload caps
(positions / scenarios / bytes) remain in ``app.api.workload``.
INTERACTIVE LINEAR / DELTA_GAMMA summary stays synchronous.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, status

from app.api.errors import PUBLIC_BAD_REQUEST_MESSAGE, code_for_status, error_payload
from app.persistence.config import external_worker_enabled

ENV_HEAVY_INLINE = "RISKFORGE_HEAVY_INLINE"
RISK_RUNS_PATH = "/risk/runs"


def _flag_is_false(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in {"0", "false", "no", "off"}


def heavy_inline_allowed() -> bool:
    """True when HEAVY compute may run on the HTTP request thread.

    Refuse when ``RISKFORGE_HEAVY_INLINE`` is an explicit falsey value, or
    when ``RISKFORGE_EXTERNAL_WORKER=1`` (Compose backend + worker process).
    Unset → allow (local tests and in-process worker).
    """
    if _flag_is_false(ENV_HEAVY_INLINE):
        return False
    return not external_worker_enabled()


def refuse_inline_heavy(*, route: str) -> HTTPException:
    """HTTP 400 ``Invalid request`` pointing at ``POST /risk/runs``."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_payload(
            code=code_for_status(status.HTTP_400_BAD_REQUEST),
            message=PUBLIC_BAD_REQUEST_MESSAGE,
            details={"use": RISK_RUNS_PATH, "route": route},
        ),
    )


def reject_inline_heavy(*, route: str) -> None:
    """No-op when inline HEAVY is allowed; otherwise raise 400."""
    if heavy_inline_allowed():
        return
    raise refuse_inline_heavy(route=route)
