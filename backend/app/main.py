"""RiskForge FastAPI application — wiring only (M7.1–M7.2 dual-mount; M7.5–M7.6)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.attribution import router as attribution_router
from app.api.deps import portfolio_service
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.legacy_deprecation import LegacyDeprecationMiddleware
from app.api.limits import router as limits_router
from app.api.market import router as market_router
from app.api.portfolio import router as portfolio_router
from app.api.risk import router as risk_router
from app.api.risk_runs import router as risk_runs_router
from app.api.stress import router as stress_router
from app.persistence.wiring import build_persistence_wiring
from app.services.risk_run_worker import RiskRunWorker

# Default in-memory worker; lifespan may replace with SQLAlchemy-backed worker
# when RISKFORGE_DATABASE_URL is set (M5.6).
risk_run_worker = RiskRunWorker(portfolio_service)

# Backward-compatible alias for tests/tools that import ``app.main.service``.
service = portfolio_service

API_V1_PREFIX = "/api/v1"

# Domain routers that already carry their path prefixes (e.g. /risk, /market).
# Dual-mounted at legacy root and under /api/v1 (M7.2).
_DOMAIN_ROUTERS = (
    health_router,
    portfolio_router,
    market_router,
    risk_router,
    stress_router,
    attribution_router,
    limits_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire optional SQLAlchemy persistence; else sample / memory backends.

    When ``RISKFORGE_DATABASE_URL`` is set, seeds portfolio + market snapshot +
    scenario / limit definitions and exposes SQLAlchemy via session factory.
    When unset, in-memory repos (pre-seeded) live on ``app.state`` for Depends.
    """
    wiring = build_persistence_wiring()
    app.state.persistence_enabled = wiring.enabled
    app.state.session_factory = wiring.session_factory
    app.state.default_portfolio_id = wiring.default_portfolio_id
    app.state.default_market_snapshot_id = wiring.default_market_snapshot_id
    app.state.market_snapshot_repo = wiring.market_snapshot_repo
    app.state.scenario_definition_repo = wiring.scenario_definition_repo
    app.state.limit_definition_repo = wiring.limit_definition_repo

    if wiring.enabled and wiring.session_factory is not None:
        worker = RiskRunWorker(portfolio_service, session_factory=wiring.session_factory)
    else:
        worker = risk_run_worker
        worker.ensure_running()

    app.state.risk_run_worker = worker
    yield
    worker.shutdown(wait=False)


app = FastAPI(title="RiskForge API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# M7.6: Deprecation/Sunset/Link on legacy dual-mount only (canonical = /api/v1).
app.add_middleware(LegacyDeprecationMiddleware)

# M7.5: one error envelope for legacy and /api/v1 mounts.
register_exception_handlers(app)

# M7.1/M7.2: same handlers at legacy paths and /api/v1/... (UI may keep legacy until M8).
for _router in _DOMAIN_ROUTERS:
    app.include_router(_router)
    app.include_router(_router, prefix=API_V1_PREFIX)

# risk_runs router paths are /runs, /runs/{id} — mount once under /risk and /api/v1/risk.
app.include_router(risk_runs_router, prefix="/risk")
app.include_router(risk_runs_router, prefix=f"{API_V1_PREFIX}/risk")
