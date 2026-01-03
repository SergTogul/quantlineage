"""Initial persistence schema (M5.1).

Revision ID: 001_initial_persistence
Revises:
Create Date: 2026-09-02

Tables: portfolios, trades, market_snapshots, scenario_definitions,
risk_runs, risk_results, limit_definitions.

JSON columns hold plain serializable domain payloads only — never QuantLib
runtime objects.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_persistence"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("firm", sa.String(length=128), nullable=False),
        sa.Column("desk", sa.String(length=128), nullable=False),
        sa.Column("strategy", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("as_of", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "scenario_definitions",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "trades",
        sa.Column("pk", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("portfolio_id", sa.String(length=128), nullable=False),
        sa.Column("position_type", sa.String(length=64), nullable=False),
        sa.Column("desk", sa.String(length=128), nullable=True),
        sa.Column("strategy", sa.String(length=128), nullable=True),
        sa.Column("book", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("portfolio_id", "id", name="uq_trades_portfolio_id"),
    )
    op.create_table(
        "limit_definitions",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("portfolio_id", sa.String(length=128), nullable=True),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("limit_value", sa.Float(), nullable=False),
        sa.Column("warning_threshold_pct", sa.Float(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=True),
        sa.Column("label", sa.String(length=256), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "risk_runs",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("portfolio_id", sa.String(length=128), nullable=False),
        sa.Column("market_snapshot_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["market_snapshot_id"], ["market_snapshots.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_risk_runs_portfolio_status",
        "risk_runs",
        ["portfolio_id", "status"],
    )
    op.create_table(
        "risk_results",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("risk_run_id", sa.String(length=128), nullable=False),
        sa.Column("result_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["risk_run_id"], ["risk_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("risk_run_id", "result_type", name="uq_risk_results_run_type"),
    )


def downgrade() -> None:
    op.drop_table("risk_results")
    op.drop_index("ix_risk_runs_portfolio_status", table_name="risk_runs")
    op.drop_table("risk_runs")
    op.drop_table("limit_definitions")
    op.drop_table("trades")
    op.drop_table("scenario_definitions")
    op.drop_table("market_snapshots")
    op.drop_table("portfolios")
