"""Out-of-process risk-run worker entrypoint (M5.7 / R0.3.5).

This module is a **distinct OS process** from the FastAPI app
(``app.main`` / Compose ``backend``). Each process owns its own QuantLib
globals (``Settings``, ``IndexManager``). In-process QuantLib calls are still
serialized by ``_QL_PROCESS_LOCK``; parallel full revaluation is process
partitioned — scale by running more of this entrypoint, not by a QuantLib
thread pool.

Runs the same ``RiskRunWorker`` + SQLAlchemy session factory as the API
lifespan, claiming ``QUEUED`` rows from shared Postgres via
``claim_queued`` (``FOR UPDATE SKIP LOCKED``).

Usage (Compose)::

    python -m app.worker

Requires ``RISKFORGE_DATABASE_URL``. Pair with ``RISKFORGE_EXTERNAL_WORKER=1``
on the API so HTTP only enqueues (the API process must not execute those runs
in-thread against the same QuantLib state). Apply migrations first::

    alembic upgrade head

Compose ships one ``worker`` by default (demo). Additional worker replicas are
safe against double-claim on Postgres thanks to ``SKIP LOCKED``; Redis/RQ is
not required for claim safety. SQLite unit tests use a non-skip-locked
fallback (single-writer). This is not a job platform.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time

from app.persistence.config import get_configured_database_url
from app.persistence.wiring import build_persistence_wiring
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.services.portfolio_service import PortfolioService
from app.services.risk_run_worker import RiskRunWorker

logger = logging.getLogger("riskforge.worker")


def _poll_interval_s() -> float:
    raw = os.environ.get("RISKFORGE_WORKER_POLL_INTERVAL", "2").strip()
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 2.0


def _poll_batch() -> int:
    raw = os.environ.get("RISKFORGE_WORKER_POLL_BATCH", "10").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 10


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not get_configured_database_url():
        logger.error("RISKFORGE_DATABASE_URL is required for riskforge-worker")
        return 2

    wiring = build_persistence_wiring(seed_sample=True, ensure_schema=True)
    if not wiring.enabled or wiring.session_factory is None:
        logger.error("persistence wiring failed (database URL set but disabled?)")
        return 2

    service = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())
    worker = RiskRunWorker(service, session_factory=wiring.session_factory)
    interval = _poll_interval_s()
    batch = _poll_batch()
    stop = False

    def _handle_stop(signum: int, _frame: object) -> None:
        nonlocal stop
        logger.info("received signal %s; shutting down", signum)
        stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    logger.info(
        "riskforge-worker started (poll_interval=%ss batch=%s)",
        interval,
        batch,
    )
    try:
        while not stop:
            try:
                n = worker.poll_once(limit=batch)
            except Exception:  # noqa: BLE001 — keep polling after transient DB errors
                logger.exception("poll_once failed")
                n = 0
            if n == 0:
                time.sleep(interval)
            # else drain backlog without sleeping
    finally:
        worker.shutdown(wait=True)
        logger.info("riskforge-worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
