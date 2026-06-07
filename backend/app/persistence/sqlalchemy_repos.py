"""SQLAlchemy implementations of persistence repository interfaces."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Sequence

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    Position,
    RiskLimit,
    RiskRun,
    RiskRunStatus,
    as_of_wire,
)
from app.persistence.models import (
    LimitDefinitionRow,
    MarketSnapshotRow,
    PortfolioRow,
    RiskResultRow,
    RiskRunRow,
    ScenarioDefinitionRow,
    TradeRow,
)
from app.persistence.repositories import (
    LimitDefinitionRepository,
    MarketSnapshotRepository,
    PortfolioAlreadyExists,
    PortfolioNotFound,
    PortfolioRepository,
    RiskRunRepository,
    ScenarioDefinitionRepository,
)
from app.persistence.risk_run_mapping import (
    results_payload_map,
    risk_run_to_row,
    row_to_risk_run,
)
from app.persistence.scenario_codec import definition_to_scenario, scenario_to_definition
from app.risk.scenario_model import Scenario

_POSITION_ADAPTER = TypeAdapter(Position)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyPortfolioRepository(PortfolioRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, portfolio: Portfolio) -> Portfolio:
        if self._session.get(PortfolioRow, portfolio.id) is not None:
            raise PortfolioAlreadyExists(portfolio.id)
        row = PortfolioRow(id=portfolio.id)
        self._session.add(row)
        return self._write(row, portfolio)

    def update(self, portfolio: Portfolio) -> Portfolio:
        row = self._session.get(PortfolioRow, portfolio.id)
        if row is None:
            raise PortfolioNotFound(portfolio.id)
        return self._write(row, portfolio)

    def save(self, portfolio: Portfolio) -> Portfolio:
        """Legacy upsert for seed/callers that have not switched to create/update."""
        row = self._session.get(PortfolioRow, portfolio.id)
        if row is None:
            row = PortfolioRow(id=portfolio.id)
            self._session.add(row)
        return self._write(row, portfolio)

    def _write(self, row: PortfolioRow, portfolio: Portfolio) -> Portfolio:
        row.name = portfolio.name
        row.firm = portfolio.firm
        row.desk = portfolio.desk
        row.strategy = portfolio.strategy
        row.updated_at = _utcnow()
        # Replace trades wholesale so deleted positions disappear.
        row.trades.clear()
        self._session.flush()
        for pos in portfolio.positions:
            payload = pos.model_dump(mode="json")
            row.trades.append(
                TradeRow(
                    id=pos.id,
                    portfolio_id=portfolio.id,
                    position_type=pos.type,
                    desk=getattr(pos, "desk", None),
                    strategy=getattr(pos, "strategy", None),
                    book=getattr(pos, "book", None),
                    payload=payload,
                )
            )
        self._session.flush()
        return portfolio

    def get(self, portfolio_id: str) -> Portfolio | None:
        row = self._session.get(PortfolioRow, portfolio_id)
        if row is None:
            return None
        positions = [_POSITION_ADAPTER.validate_python(t.payload) for t in row.trades]
        return Portfolio(
            id=row.id,
            name=row.name,
            firm=row.firm,
            desk=row.desk,
            strategy=row.strategy,
            positions=positions,
        )

    def delete(self, portfolio_id: str) -> bool:
        row = self._session.get(PortfolioRow, portfolio_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def list_ids(self) -> list[str]:
        return list(self._session.scalars(select(PortfolioRow.id).order_by(PortfolioRow.id)))


class SqlAlchemyMarketSnapshotRepository(MarketSnapshotRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, snapshot: MarketSnapshot, *, meta: dict[str, Any] | None = None) -> str:
        data = snapshot.model_dump(mode="json")
        content_hash = snapshot.content_hash()
        row = self._session.get(MarketSnapshotRow, snapshot.id)
        if row is None:
            row = MarketSnapshotRow(id=snapshot.id)
            self._session.add(row)
        row.as_of = as_of_wire(snapshot.as_of)
        row.content_hash = content_hash
        row.meta = dict(meta or {})
        row.data = data
        self._session.flush()
        return snapshot.id

    def get(self, snapshot_id: str) -> MarketSnapshot | None:
        row = self._session.get(MarketSnapshotRow, snapshot_id)
        if row is None:
            return None
        return MarketSnapshot.model_validate(row.data)

    def get_meta(self, snapshot_id: str) -> dict[str, Any] | None:
        row = self._session.get(MarketSnapshotRow, snapshot_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "as_of": row.as_of,
            "content_hash": row.content_hash,
            "meta": dict(row.meta or {}),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


class SqlAlchemyScenarioDefinitionRepository(ScenarioDefinitionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, scenario: Scenario) -> Scenario:
        if not isinstance(scenario, Scenario):
            raise TypeError(f"scenario definitions store Scenario, got {type(scenario)!r}")
        sid = scenario.id
        payload = scenario_to_definition(scenario)
        row = self._session.get(ScenarioDefinitionRow, sid)
        if row is None:
            row = ScenarioDefinitionRow(id=sid)
            self._session.add(row)
        row.name = scenario.name
        row.category = scenario.category.value
        row.description = scenario.description
        row.definition = payload
        row.updated_at = _utcnow()
        self._session.flush()
        return scenario

    def get(self, scenario_id: str) -> Scenario | None:
        row = self._session.get(ScenarioDefinitionRow, scenario_id)
        if row is None:
            return None
        return definition_to_scenario(row.definition)

    def list_all(self) -> list[Scenario]:
        rows = self._session.scalars(
            select(ScenarioDefinitionRow).order_by(ScenarioDefinitionRow.id)
        ).all()
        return [definition_to_scenario(r.definition) for r in rows]

    def delete(self, scenario_id: str) -> bool:
        row = self._session.get(ScenarioDefinitionRow, scenario_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True


class SqlAlchemyRiskRunRepository(RiskRunRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, run: RiskRun) -> RiskRun:
        row = risk_run_to_row(run)
        self._session.add(row)
        self._session.flush()
        return row_to_risk_run(row)

    def set_status(
        self,
        run_id: str,
        status: RiskRunStatus,
        *,
        error: str | None = None,
    ) -> RiskRun:
        row = self._session.get(RiskRunRow, run_id)
        if row is None:
            raise KeyError(f"risk run not found: {run_id}")
        row.status = status
        if status == RiskRunStatus.RUNNING and row.started_at is None:
            row.started_at = _utcnow()
        if status in {RiskRunStatus.COMPLETED, RiskRunStatus.FAILED}:
            if row.started_at is None:
                row.started_at = row.created_at or _utcnow()
            row.finished_at = _utcnow()
        if status == RiskRunStatus.FAILED:
            if error is None or not str(error).strip():
                raise ValueError("FAILED status requires a non-empty error")
            row.error_message = error
        elif error is not None:
            row.error_message = error
        if status == RiskRunStatus.COMPLETED:
            row.error_message = None
        self._session.flush()
        return row_to_risk_run(row)

    def add_result(self, run_id: str, result_type: str, payload: dict[str, Any]) -> None:
        if self._session.get(RiskRunRow, run_id) is None:
            raise KeyError(f"risk run not found: {run_id}")
        existing = self._session.scalars(
            select(RiskResultRow).where(
                RiskResultRow.risk_run_id == run_id,
                RiskResultRow.result_type == result_type,
            )
        ).first()
        if existing is not None:
            existing.payload = payload
        else:
            self._session.add(
                RiskResultRow(risk_run_id=run_id, result_type=result_type, payload=payload)
            )
        self._session.flush()

    def get(self, run_id: str) -> RiskRun | None:
        row = self._session.get(RiskRunRow, run_id)
        if row is None:
            return None
        return row_to_risk_run(row)

    def get_result_payloads(self, run_id: str) -> dict[str, dict[str, Any]] | None:
        row = self._session.get(RiskRunRow, run_id)
        if row is None:
            return None
        return results_payload_map(row)

    def list_by_status(
        self,
        status: RiskRunStatus,
        *,
        limit: int = 50,
    ) -> list[RiskRun]:
        rows = self._session.scalars(
            select(RiskRunRow)
            .where(RiskRunRow.status == status)
            .order_by(RiskRunRow.created_at.asc(), RiskRunRow.id.asc())
            .limit(max(0, int(limit)))
        ).all()
        return [row_to_risk_run(row) for row in rows]

    def claim_queued(self, *, limit: int = 1) -> list[RiskRun]:
        """Claim QUEUED → RUNNING; Postgres uses ``FOR UPDATE SKIP LOCKED``.

        SQLite (unit tests) and other dialects select FIFO without skip-locked
        row locking — fine for single-writer demos, not multi-worker-safe.
        """
        n = max(0, int(limit))
        if n == 0:
            return []
        stmt = (
            select(RiskRunRow)
            .where(RiskRunRow.status == RiskRunStatus.QUEUED)
            .order_by(RiskRunRow.created_at.asc(), RiskRunRow.id.asc())
            .limit(n)
        )
        bind = self._session.get_bind()
        dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""
        if dialect == "postgresql":
            # Concurrent workers: lock eligible rows; skip those locked by peers.
            stmt = stmt.with_for_update(skip_locked=True)
        rows = list(self._session.scalars(stmt).all())
        if not rows:
            return []
        now = _utcnow()
        claimed: list[RiskRun] = []
        for row in rows:
            row.status = RiskRunStatus.RUNNING
            if row.started_at is None:
                row.started_at = now
            claimed.append(row_to_risk_run(row))
        self._session.flush()
        return claimed


class SqlAlchemyLimitDefinitionRepository(LimitDefinitionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, limit_id: str, limit: RiskLimit, *, portfolio_id: str | None = None) -> str:
        row = self._session.get(LimitDefinitionRow, limit_id)
        if row is None:
            row = LimitDefinitionRow(id=limit_id)
            self._session.add(row)
        row.portfolio_id = portfolio_id
        row.metric = limit.metric
        row.limit_value = float(limit.limit)
        row.warning_threshold_pct = float(limit.warning_threshold_pct)
        row.scope = limit.scope
        row.label = limit.label
        row.active = True
        row.updated_at = _utcnow()
        self._session.flush()
        return limit_id

    def get(self, limit_id: str) -> RiskLimit | None:
        row = self._session.get(LimitDefinitionRow, limit_id)
        if row is None or not row.active:
            return None
        return RiskLimit(
            metric=row.metric,  # type: ignore[arg-type]
            limit=row.limit_value,
            warning_threshold_pct=row.warning_threshold_pct,
            scope=row.scope,  # type: ignore[arg-type]
            label=row.label,
        )

    def list_for_portfolio(
        self, portfolio_id: str | None = None
    ) -> Sequence[tuple[str, RiskLimit]]:
        stmt = select(LimitDefinitionRow).where(LimitDefinitionRow.active.is_(True))
        if portfolio_id is None:
            stmt = stmt.where(LimitDefinitionRow.portfolio_id.is_(None))
        else:
            stmt = stmt.where(LimitDefinitionRow.portfolio_id == portfolio_id)
        rows = self._session.scalars(stmt.order_by(LimitDefinitionRow.id)).all()
        out: list[tuple[str, RiskLimit]] = []
        for row in rows:
            out.append(
                (
                    row.id,
                    RiskLimit(
                        metric=row.metric,  # type: ignore[arg-type]
                        limit=row.limit_value,
                        warning_threshold_pct=row.warning_threshold_pct,
                        scope=row.scope,  # type: ignore[arg-type]
                        label=row.label,
                    ),
                )
            )
        return out

    def delete(self, limit_id: str) -> bool:
        row = self._session.get(LimitDefinitionRow, limit_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True
