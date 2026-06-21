"""SQLAlchemy ORM tables for M5.1+ persistence.

All instrument / market / risk payloads are stored as JSON. QuantLib curve
handles, process objects, and other pricing-engine runtime state must never
appear in these columns — only plain dict/list trees from Pydantic
``model_dump`` / snapshot serializers.

``RiskRunStatus`` is defined in ``app.domain.models`` (M5.2) and re-exported
here so ORM / repository imports stay stable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.domain.models import RiskRunStatus
from app.persistence.base import Base

__all__ = [
    "RiskRunStatus",
    "PortfolioRow",
    "TradeRow",
    "MarketSnapshotRow",
    "ScenarioDefinitionRow",
    "RiskRunRow",
    "RiskResultRow",
    "LimitDefinitionRow",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PortfolioRow(Base):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    firm: Mapped[str] = mapped_column(String(128), nullable=False, default="RiskForge")
    desk: Mapped[str] = mapped_column(String(128), nullable=False, default="Global Macro")
    strategy: Mapped[str] = mapped_column(String(128), nullable=False, default="Multi-Asset")
    # Server-owned monotonic version (R0.8.8). Create starts at 1.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Shared-profile object owner (RF-014). Seed/demo catalog uses ``demo``.
    owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    trades: Mapped[list[TradeRow]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="TradeRow.id",
    )
    risk_runs: Mapped[list[RiskRunRow]] = relationship(back_populates="portfolio")
    limit_definitions: Mapped[list[LimitDefinitionRow]] = relationship(
        back_populates="portfolio"
    )


class TradeRow(Base):
    """One portfolio position / trade.

    ``payload`` is the full discriminated Position JSON (type + fields).
    Hierarchy columns are denormalized for query; source of truth remains payload.
    """

    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("portfolio_id", "id", name="uq_trades_portfolio_id"),)

    # Surrogate PK so trade ids can repeat across portfolios.
    pk: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(128), nullable=False)
    portfolio_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    position_type: Mapped[str] = mapped_column(String(64), nullable=False)
    desk: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    strategy: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    book: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    portfolio: Mapped[PortfolioRow] = relationship(back_populates="trades")


class MarketSnapshotRow(Base):
    """Market snapshot metadata + JSON data blob (no QuantLib objects)."""

    __tablename__ = "market_snapshots"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    as_of: Mapped[str] = mapped_column(String(64), nullable=False, default="current")
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Small searchable attributes (labels, source tags); not the full marks.
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Full serializable MarketSnapshot tree (spots, vols, curves payloads, …).
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    risk_runs: Mapped[list[RiskRunRow]] = relationship(back_populates="market_snapshot")


class ScenarioDefinitionRow(Base):
    """Persisted canonical Scenario definition (ScenarioWire JSON)."""

    __tablename__ = "scenario_definitions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="factor")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON definition: formal ScenarioWire (typed shocks).
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class RiskRunRow(Base):
    """Persisted risk-run request / lifecycle (results in risk_results).

    Domain ``RiskRun`` maps ``completed_at``→``finished_at`` and ``error``→
    ``error_message``. First-class M5.2 columns: ``pricing_engine_version``,
    ``methodology``, ``scenario_set``. Spec columns (R0.8.1):
    ``historical_dataset_id``, ``historical_dataset_version``, ``as_of``,
    ``calculation_config`` — nullable so pre-spec rows still load.
    ``portfolio_version`` (R0.8.8) is the stored book version at submit;
    nullable so pre-version rows still load. Not a historical book archive.
    ``owner`` (RF-014) is the submitting principal; nullable so pre-ACL rows
    still load.
    """

    __tablename__ = "risk_runs"
    __table_args__ = (Index("ix_risk_runs_portfolio_status", "portfolio_id", "status"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    portfolio_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    market_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(128), ForeignKey("market_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[RiskRunStatus] = mapped_column(
        Enum(RiskRunStatus, name="risk_run_status", native_enum=False, length=32),
        nullable=False,
        default=RiskRunStatus.QUEUED,
    )
    run_type: Mapped[str] = mapped_column(String(64), nullable=False, default="summary")
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    pricing_engine_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    methodology: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scenario_set: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    historical_dataset_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    historical_dataset_version: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    as_of: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    calculation_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    portfolio: Mapped[PortfolioRow] = relationship(back_populates="risk_runs")
    market_snapshot: Mapped[Optional[MarketSnapshotRow]] = relationship(
        back_populates="risk_runs"
    )
    results: Mapped[list[RiskResultRow]] = relationship(
        back_populates="risk_run",
        cascade="all, delete-orphan",
        order_by="RiskResultRow.id",
    )


class RiskResultRow(Base):
    """One named result payload attached to a risk run (summary, VaR, stress, …)."""

    __tablename__ = "risk_results"
    __table_args__ = (
        UniqueConstraint("risk_run_id", "result_type", name="uq_risk_results_run_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    risk_run_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("risk_runs.id", ondelete="CASCADE"), nullable=False
    )
    result_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Physical JSON column; writes are validated per result_type (R0.8.7 / PERF-016).
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    risk_run: Mapped[RiskRunRow] = relationship(back_populates="results")


class LimitDefinitionRow(Base):
    """Configurable risk-limit definition (maps to domain ``RiskLimit``)."""

    __tablename__ = "limit_definitions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    portfolio_id: Mapped[Optional[str]] = mapped_column(
        String(128), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=True
    )
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    limit_value: Mapped[float] = mapped_column(Float, nullable=False)
    warning_threshold_pct: Mapped[float] = mapped_column(Float, nullable=False, default=80.0)
    scope: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    portfolio: Mapped[Optional[PortfolioRow]] = relationship(back_populates="limit_definitions")
