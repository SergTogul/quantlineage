"""RiskForge FastAPI application — wiring only (M7.1–M7.2 dual-mount; M7.5–M7.6)."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.attribution import router as attribution_router
from app.api.auth import SharedTokenMiddleware, require_shared_auth_configured
from app.api.data import router as data_router
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.instruments import router as instruments_router
from app.api.legacy_deprecation import LegacyDeprecationMiddleware
from app.api.limits import router as limits_router
from app.api.market import router as market_router
from app.api.portfolio import router as portfolio_router
from app.api.risk import router as risk_router
from app.api.risk_runs import router as risk_runs_router
from app.api.stress import router as stress_router
from app.api.workload import WorkloadBodyLimitMiddleware, enforce_workload_limits
from app.persistence.wiring import build_persistence_wiring
from app.services.risk_factories import build_portfolio_service
from app.services.risk_run_worker import RiskRunWorker

API_V1_PREFIX = "/api/v1"

# Domain routers that already carry their path prefixes (e.g. /risk, /market).
# Dual-mounted at legacy root and under /api/v1 (M7.2).
_DOMAIN_ROUTERS = (
    health_router,
    portfolio_router,
    instruments_router,
    data_router,
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

    Shared / non-loopback profiles fail closed here unless ``RISKFORGE_API_TOKEN``
    or ``RISKFORGE_API_TOKENS`` is set (R0.11.5 / RF-014). Local loopback /
    default Compose stays unauthenticated.

    ``PortfolioService`` is constructed here via ``build_portfolio_service()``
    and stored on ``app.state`` so HTTP Depends and ``RiskRunWorker`` share
    one instance (R0.9.3).
    """
    require_shared_auth_configured()
    wiring = build_persistence_wiring()
    app.state.persistence_enabled = wiring.enabled
    app.state.session_factory = wiring.session_factory
    app.state.default_portfolio_id = wiring.default_portfolio_id
    app.state.default_market_snapshot_id = wiring.default_market_snapshot_id
    app.state.market_snapshot_repo = wiring.market_snapshot_repo
    app.state.scenario_definition_repo = wiring.scenario_definition_repo
    app.state.limit_definition_repo = wiring.limit_definition_repo

    service = build_portfolio_service()
    app.state.portfolio_service = service
    if wiring.enabled and wiring.session_factory is not None:
        worker = RiskRunWorker(service, session_factory=wiring.session_factory)
    else:
        worker = RiskRunWorker(service, market_snapshots=wiring.market_snapshot_repo)
        worker.ensure_running()

    app.state.risk_run_worker = worker
    service.risk_run_compare = worker.compare_runs
    yield
    worker.shutdown(wait=False)


app = FastAPI(
    title="RiskForge API",
    version="0.3.0",
    lifespan=lifespan,
    dependencies=[Depends(enforce_workload_limits)],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# M7.6: Deprecation/Sunset/Link on legacy dual-mount only (canonical = /api/v1).
app.add_middleware(LegacyDeprecationMiddleware)
# Byte cap must sit outside BaseHTTPMiddleware and FastAPI body parsing.
app.add_middleware(WorkloadBodyLimitMiddleware)
# Last add_middleware is outermost: token gate rejects unauthenticated /api first.
app.add_middleware(SharedTokenMiddleware)

# M7.5: one error envelope for legacy and /api/v1 mounts.
register_exception_handlers(app)

# M7.1/M7.2: same handlers at legacy paths and /api/v1/... (UI may keep legacy until M8).
for _router in _DOMAIN_ROUTERS:
    app.include_router(_router)
    app.include_router(_router, prefix=API_V1_PREFIX)

# risk_runs router paths are /runs, /runs/{id} — mount once under /risk and /api/v1/risk.
app.include_router(risk_runs_router, prefix="/risk")
app.include_router(risk_runs_router, prefix=f"{API_V1_PREFIX}/risk")


def __getattr__(name: str):
    """``app.main.service`` is a thin alias to ``app.state.portfolio_service``.

    Lifespan constructs that instance. Tests that need ``service`` must start
    lifespan (``with TestClient(app)``). There is no module-global fallback.
    """
    if name != "service":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    svc = getattr(app.state, "portfolio_service", None)
    if svc is None:
        raise AttributeError(
            "app.main.service is unavailable until FastAPI lifespan sets "
            "app.state.portfolio_service; use `with TestClient(app)` in tests"
        )
    return svc
