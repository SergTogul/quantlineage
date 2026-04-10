"""Repository protocol interfaces (persistence contracts for API services).

Implementations live in ``sqlalchemy_repos``. Callers depend on these ABCs so
M5.3/M5.4 lifecycle wiring can swap backends without touching risk math.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    RiskLimit,
    RiskRun,
    RiskRunStatus,
    StressScenario,
)


class PortfolioAlreadyExists(ValueError):
    """``create`` was called with an id that is already stored."""

    def __init__(self, portfolio_id: str) -> None:
        self.portfolio_id = portfolio_id
        super().__init__(f"portfolio already exists: {portfolio_id}")


class PortfolioNotFound(ValueError):
    """``update`` was called with an id that is not stored."""

    def __init__(self, portfolio_id: str) -> None:
        self.portfolio_id = portfolio_id
        super().__init__(f"portfolio not found: {portfolio_id}")


class PortfolioRepository(ABC):
    @abstractmethod
    def create(self, portfolio: Portfolio) -> Portfolio:
        """Insert a new portfolio. Raise if the id already exists."""

    @abstractmethod
    def update(self, portfolio: Portfolio) -> Portfolio:
        """Replace an existing portfolio. Raise if the id is missing."""

    @abstractmethod
    def save(self, portfolio: Portfolio) -> Portfolio:
        """Legacy upsert. Prefer :meth:`create` / :meth:`update` for identity-safe writes."""

    @abstractmethod
    def get(self, portfolio_id: str) -> Portfolio | None:
        ...

    @abstractmethod
    def delete(self, portfolio_id: str) -> bool:
        ...

    @abstractmethod
    def list_ids(self) -> list[str]:
        ...


class MarketSnapshotRepository(ABC):
    @abstractmethod
    def save(self, snapshot: MarketSnapshot, *, meta: dict[str, Any] | None = None) -> str:
        """Persist snapshot JSON; return snapshot id."""

    @abstractmethod
    def get(self, snapshot_id: str) -> MarketSnapshot | None:
        ...

    @abstractmethod
    def get_meta(self, snapshot_id: str) -> dict[str, Any] | None:
        """Return metadata dict (id, as_of, content_hash, meta) without full data."""


class ScenarioDefinitionRepository(ABC):
    @abstractmethod
    def save(self, scenario: StressScenario) -> StressScenario:
        ...

    @abstractmethod
    def get(self, scenario_id: str) -> StressScenario | None:
        ...

    @abstractmethod
    def list_all(self) -> list[StressScenario]:
        ...

    @abstractmethod
    def delete(self, scenario_id: str) -> bool:
        ...


class RiskRunRepository(ABC):
    @abstractmethod
    def create(self, run: RiskRun) -> RiskRun:
        """Persist a domain ``RiskRun`` header; return the stored DTO."""

    @abstractmethod
    def set_status(
        self,
        run_id: str,
        status: RiskRunStatus,
        *,
        error: str | None = None,
    ) -> RiskRun:
        """Update lifecycle status; return the refreshed domain DTO."""

    @abstractmethod
    def add_result(self, run_id: str, result_type: str, payload: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def get(self, run_id: str) -> RiskRun | None:
        """Return domain ``RiskRun`` (result refs, not full payloads)."""

    @abstractmethod
    def get_result_payloads(self, run_id: str) -> dict[str, dict[str, Any]] | None:
        """Return ``result_type`` → payload map, or None if run missing."""

    @abstractmethod
    def list_by_status(
        self,
        status: RiskRunStatus,
        *,
        limit: int = 50,
    ) -> list[RiskRun]:
        """Return runs in ``status`` ordered by ``created_at`` ascending (FIFO)."""

    @abstractmethod
    def claim_queued(self, *, limit: int = 1) -> list[RiskRun]:
        """Atomically claim up to ``limit`` QUEUED runs (→ RUNNING), FIFO.

        Postgres SQLAlchemy path uses ``FOR UPDATE SKIP LOCKED`` so concurrent
        workers do not race. Other backends use best-effort locking within the
        process/session (Compose single-worker demo remains valid).
        """


class LimitDefinitionRepository(ABC):
    @abstractmethod
    def save(self, limit_id: str, limit: RiskLimit, *, portfolio_id: str | None = None) -> str:
        ...

    @abstractmethod
    def get(self, limit_id: str) -> RiskLimit | None:
        ...

    @abstractmethod
    def list_for_portfolio(self, portfolio_id: str | None = None) -> Sequence[tuple[str, RiskLimit]]:
        """Return ``(id, RiskLimit)``; ``portfolio_id=None`` lists firm-wide defs."""

    @abstractmethod
    def delete(self, limit_id: str) -> bool:
        ...
