"""FastAPI dependency helpers (persistence / services)."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models import MarketSnapshot, Portfolio, StressScenario
from app.persistence.repositories import (
    LimitDefinitionRepository,
    MarketSnapshotRepository,
    ScenarioDefinitionRepository,
)
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyLimitDefinitionRepository,
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyScenarioDefinitionRepository,
)
from app.persistence.wiring import (
    DEFAULT_MARKET_SNAPSHOT_ID,
    DEFAULT_PORTFOLIO_ID,
    load_market_snapshot,
    load_portfolio,
)
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine
from app.risk.stress import DEFAULT_SCENARIOS, THREAT_SCENARIOS
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService
from app.services.risk_run_worker import RiskRunWorker

_DEFAULT_SCENARIO_IDS = {s.id for s in DEFAULT_SCENARIOS if s.id}

# Process-wide PortfolioService (pricing via factory; M7.1 DI for routers).
portfolio_service = PortfolioService(create_pricing_engine(), HistoricalRiskEngine())


def get_portfolio_service() -> PortfolioService:
    """Deterministic portfolio/risk service used by HTTP routers."""
    return portfolio_service



def get_session_factory(request: Request) -> sessionmaker[Session] | None:
    """SQLAlchemy session factory when persistence is enabled; else None."""
    return getattr(request.app.state, "session_factory", None)


def get_persistence_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "persistence_enabled", False))


def get_db_session(request: Request) -> Iterator[Session | None]:
    """Request-scoped SQLAlchemy session when DATABASE_URL is set; else None."""
    factory = get_session_factory(request)
    if factory is None:
        yield None
        return
    with session_scope(factory) as session:
        yield session


def get_default_portfolio(request: Request) -> Portfolio:
    """Demo portfolio: SQLAlchemy-backed when DATABASE_URL set, else SAMPLE."""
    factory = get_session_factory(request)
    portfolio_id = getattr(request.app.state, "default_portfolio_id", DEFAULT_PORTFOLIO_ID)
    return load_portfolio(factory, portfolio_id=portfolio_id, fallback=SAMPLE_PORTFOLIO)


def get_default_market_snapshot(request: Request) -> MarketSnapshot:
    """Demo market snapshot: SQLAlchemy / in-memory seed, else SAMPLE marks."""
    factory = get_session_factory(request)
    snapshot_id = getattr(
        request.app.state, "default_market_snapshot_id", DEFAULT_MARKET_SNAPSHOT_ID
    )
    memory_repo = getattr(request.app.state, "market_snapshot_repo", None)
    return load_market_snapshot(
        factory, snapshot_id=snapshot_id, memory_repo=memory_repo
    )


def get_market_snapshot_repository(
    request: Request,
    session: Session | None = Depends(get_db_session),
) -> MarketSnapshotRepository:
    """SQLAlchemy repo when persistence enabled; else in-memory seed store."""
    if session is not None:
        return SqlAlchemyMarketSnapshotRepository(session)
    repo = getattr(request.app.state, "market_snapshot_repo", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="market snapshot repository is not configured",
        )
    return repo


def get_scenario_definition_repository(
    request: Request,
    session: Session | None = Depends(get_db_session),
) -> ScenarioDefinitionRepository:
    """SQLAlchemy repo when persistence enabled; else in-memory seed store."""
    repo = _resolve_scenario_definition_repository(request, session)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="scenario definition repository is not configured",
        )
    return repo


def _resolve_scenario_definition_repository(
    request: Request,
    session: Session | None,
) -> ScenarioDefinitionRepository | None:
    """Return the wired scenario repo, or None when lifespan has not configured one."""
    if session is not None:
        return SqlAlchemyScenarioDefinitionRepository(session)
    return getattr(request.app.state, "scenario_definition_repo", None)


def get_stress_scenario_definition_repository(
    request: Request,
    session: Session | None = Depends(get_db_session),
) -> ScenarioDefinitionRepository | None:
    """Optional scenario repo for stress HTTP defaults (no 503 when unconfigured)."""
    return _resolve_scenario_definition_repository(request, session)


def get_default_stress_scenarios(
    repo: ScenarioDefinitionRepository | None = Depends(
        get_stress_scenario_definition_repository
    ),
) -> list[StressScenario]:
    """Scenario list for stress HTTP defaults (M5.9).

    Prefer ``scenario_definition_repo`` (memory or SQLAlchemy seed). Fall back to
    in-code ``THREAT_SCENARIOS`` when the repo is missing or empty so demos and
    legacy TestClients without lifespan still work.
    """
    scenarios = repo.list_all() if repo is not None else []
    if scenarios:
        return scenarios
    return list(THREAT_SCENARIOS)


def get_baseline_stress_scenarios(
    scenarios: list[StressScenario] = Depends(get_default_stress_scenarios),
) -> list[StressScenario]:
    """DEFAULT-only subset for ``POST /risk/stress`` (M5.9 follow-up).

    Filters the DI-backed list to in-code ``DEFAULT_SCENARIOS`` ids so persistence
    overrides apply while keeping the historical baseline set separate from
    threat/crisis definitions. Falls back to ``DEFAULT_SCENARIOS`` when no
    DEFAULT-id rows are present (empty/missing repo or threat-only fallback).
    """
    by_id = {s.id: s for s in scenarios if s.id in _DEFAULT_SCENARIO_IDS}
    if not by_id:
        return list(DEFAULT_SCENARIOS)
    return [by_id[s.id] for s in DEFAULT_SCENARIOS if s.id in by_id]


def get_limit_definition_repository(
    request: Request,
    session: Session | None = Depends(get_db_session),
) -> LimitDefinitionRepository:
    """SQLAlchemy repo when persistence enabled; else in-memory seed store."""
    if session is not None:
        return SqlAlchemyLimitDefinitionRepository(session)
    repo = getattr(request.app.state, "limit_definition_repo", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="limit definition repository is not configured",
        )
    return repo


def get_risk_run_worker(request: Request) -> RiskRunWorker:
    worker = getattr(request.app.state, "risk_run_worker", None)
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="risk run worker is not configured",
        )
    return worker
