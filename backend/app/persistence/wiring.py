"""Optional SQLAlchemy wiring for FastAPI (M5.6).

When ``RISKFORGE_DATABASE_URL`` is set, build a session factory and seed the
demo portfolio, market snapshot, scenario definitions, and limit definitions.
When unset, callers stay on sample / in-memory backends so existing unit tests
remain unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.domain.models import MarketSnapshot, Portfolio, RiskLimit, StressScenario
from app.market.snapshot import PositionMarketDataProvider

# Import models so metadata is populated before create_all.
from app.persistence import models as _models  # noqa: F401
from app.persistence.base import Base
from app.persistence.config import get_configured_database_url, get_database_settings
from app.persistence.memory_repos import (
    InMemoryLimitDefinitionRepository,
    InMemoryMarketSnapshotRepository,
    InMemoryScenarioDefinitionRepository,
)
from app.persistence.repositories import (
    LimitDefinitionRepository,
    MarketSnapshotRepository,
    ScenarioDefinitionRepository,
)
from app.persistence.session import create_engine_from_url, create_session_factory, session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyLimitDefinitionRepository,
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyScenarioDefinitionRepository,
)
from app.risk.limits import DEFAULT_LIMITS
from app.risk.stress import DEFAULT_SCENARIOS, THREAT_SCENARIOS
from app.sample import SAMPLE_PORTFOLIO

logger = logging.getLogger(__name__)

DEFAULT_PORTFOLIO_ID = SAMPLE_PORTFOLIO.id
DEFAULT_MARKET_SNAPSHOT_ID = "position_marks"


def default_sample_market_snapshot() -> MarketSnapshot:
    """Immutable marks snapshot derived from ``SAMPLE_PORTFOLIO``."""
    snap = PositionMarketDataProvider().snapshot(SAMPLE_PORTFOLIO)
    return snap.model_copy(update={"id": DEFAULT_MARKET_SNAPSHOT_ID})


def default_seed_scenarios() -> list[StressScenario]:
    """Demo scenario definitions: DEFAULT + THREAT, deduped by id."""
    seen: set[str] = set()
    out: list[StressScenario] = []
    for scenario in list(DEFAULT_SCENARIOS) + list(THREAT_SCENARIOS):
        sid = scenario.id or scenario.name
        if not sid or sid in seen:
            continue
        seen.add(sid)
        if scenario.id is None:
            scenario = scenario.model_copy(update={"id": sid})
        out.append(scenario)
    return out


def default_limit_id(limit: RiskLimit) -> str:
    """Stable id for seeded / firm-wide limit definitions."""
    return f"limit-{limit.scope}-{limit.metric}"


@dataclass(frozen=True, slots=True)
class PersistenceWiring:
    """Resolved persistence mode for API lifespan / DI."""

    enabled: bool
    session_factory: sessionmaker[Session] | None = None
    default_portfolio_id: str = DEFAULT_PORTFOLIO_ID
    default_market_snapshot_id: str = DEFAULT_MARKET_SNAPSHOT_ID
    # Populated when enabled=False so Depends can serve the same contracts.
    market_snapshot_repo: MarketSnapshotRepository | None = None
    scenario_definition_repo: ScenarioDefinitionRepository | None = None
    limit_definition_repo: LimitDefinitionRepository | None = None


def build_persistence_wiring(
    *,
    url: str | None = None,
    seed_sample: bool = True,
    ensure_schema: bool = True,
) -> PersistenceWiring:
    """Build session factory when a database URL is configured.

    ``url`` overrides the env var (useful in tests). Blank / unset → disabled
    (in-memory repos pre-seeded from sample defaults).
    """
    resolved = (url.strip() if isinstance(url, str) else None) or get_configured_database_url()
    if not resolved:
        return _build_memory_wiring(seed_sample=seed_sample)

    settings = get_database_settings(url=resolved)
    engine = create_engine_from_url(settings.url, echo=settings.echo)
    if ensure_schema:
        # Demo / SQLite tests: create tables without requiring a prior alembic run.
        # Compose Postgres should still run alembic; create_all is a no-op when
        # tables already exist.
        Base.metadata.create_all(engine)
    factory = create_session_factory(settings, engine=engine)

    if seed_sample:
        _seed_sqlalchemy_defaults(factory)

    return PersistenceWiring(
        enabled=True,
        session_factory=factory,
        default_portfolio_id=DEFAULT_PORTFOLIO_ID,
        default_market_snapshot_id=DEFAULT_MARKET_SNAPSHOT_ID,
    )


def _build_memory_wiring(*, seed_sample: bool) -> PersistenceWiring:
    market_repo: MarketSnapshotRepository = InMemoryMarketSnapshotRepository()
    scenario_repo: ScenarioDefinitionRepository = InMemoryScenarioDefinitionRepository()
    limit_repo: LimitDefinitionRepository = InMemoryLimitDefinitionRepository()
    if seed_sample:
        _seed_into_repos(market_repo, scenario_repo, limit_repo)
    return PersistenceWiring(
        enabled=False,
        default_portfolio_id=DEFAULT_PORTFOLIO_ID,
        default_market_snapshot_id=DEFAULT_MARKET_SNAPSHOT_ID,
        market_snapshot_repo=market_repo,
        scenario_definition_repo=scenario_repo,
        limit_definition_repo=limit_repo,
    )


def _seed_sqlalchemy_defaults(factory: sessionmaker[Session]) -> None:
    with session_scope(factory) as session:
        portfolio_repo = SqlAlchemyPortfolioRepository(session)
        if portfolio_repo.get(SAMPLE_PORTFOLIO.id) is None:
            portfolio_repo.save(SAMPLE_PORTFOLIO)
            logger.info("seeded sample portfolio %s", SAMPLE_PORTFOLIO.id)

        market_repo = SqlAlchemyMarketSnapshotRepository(session)
        scenario_repo = SqlAlchemyScenarioDefinitionRepository(session)
        limit_repo = SqlAlchemyLimitDefinitionRepository(session)
        _seed_into_repos(market_repo, scenario_repo, limit_repo)


def _seed_into_repos(
    market_repo: MarketSnapshotRepository,
    scenario_repo: ScenarioDefinitionRepository,
    limit_repo: LimitDefinitionRepository,
) -> None:
    snap = default_sample_market_snapshot()
    if market_repo.get(snap.id) is None:
        market_repo.save(snap, meta={"source": "sample", "portfolio_id": SAMPLE_PORTFOLIO.id})
        logger.info("seeded sample market snapshot %s", snap.id)

    scenarios = default_seed_scenarios()
    for scenario in scenarios:
        sid = scenario.id or scenario.name
        if scenario_repo.get(sid) is None:
            scenario_repo.save(scenario)
    logger.info("seeded scenario definitions (%d)", len(scenarios))

    for limit in DEFAULT_LIMITS:
        lid = default_limit_id(limit)
        if limit_repo.get(lid) is None:
            # Firm-wide defaults (portfolio_id=None).
            limit_repo.save(lid, limit, portfolio_id=None)
    logger.info("seeded limit definitions (%d)", len(DEFAULT_LIMITS))


def load_portfolio(
    factory: sessionmaker[Session] | None,
    *,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    fallback: Portfolio | None = None,
) -> Portfolio:
    """Load portfolio from SQLAlchemy when wired; else return fallback/sample."""
    fallback = fallback if fallback is not None else SAMPLE_PORTFOLIO
    if factory is None:
        return fallback
    with session_scope(factory) as session:
        loaded = SqlAlchemyPortfolioRepository(session).get(portfolio_id)
        if loaded is None:
            return fallback
        return loaded


def load_market_snapshot(
    factory: sessionmaker[Session] | None,
    *,
    snapshot_id: str = DEFAULT_MARKET_SNAPSHOT_ID,
    memory_repo: MarketSnapshotRepository | None = None,
    fallback: MarketSnapshot | None = None,
) -> MarketSnapshot:
    """Load market snapshot from SQLAlchemy or in-memory repo; else sample."""
    fallback = fallback if fallback is not None else default_sample_market_snapshot()
    if factory is not None:
        with session_scope(factory) as session:
            loaded = SqlAlchemyMarketSnapshotRepository(session).get(snapshot_id)
            if loaded is not None:
                return loaded
        return fallback
    if memory_repo is not None:
        loaded = memory_repo.get(snapshot_id)
        if loaded is not None:
            return loaded
    return fallback
