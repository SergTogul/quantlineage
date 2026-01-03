"""M5.2: first-class RiskRun domain columns on risk_runs.

Revision ID: 002_risk_run_domain_fields
Revises: 001_initial_persistence
Create Date: 2026-09-02

Adds pricing_engine_version, methodology, scenario_set. Does not rewrite 001.
Domain ``completed_at`` continues to map to existing ``finished_at``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_risk_run_domain_fields"
down_revision: Union[str, None] = "001_initial_persistence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "risk_runs",
        sa.Column("pricing_engine_version", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "risk_runs",
        sa.Column("methodology", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "risk_runs",
        sa.Column(
            "scenario_set",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("risk_runs", "scenario_set")
    op.drop_column("risk_runs", "methodology")
    op.drop_column("risk_runs", "pricing_engine_version")
