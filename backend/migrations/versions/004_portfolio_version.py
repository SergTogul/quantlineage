"""R0.8.8: server-owned portfolio version + RiskRun.portfolio_version.

Revision ID: 004_portfolio_version
Revises: 003_risk_run_spec_fields
Create Date: 2026-09-09

Adds portfolios.version (NOT NULL, default 1) and nullable
risk_runs.portfolio_version captured at submit. Not a historical archive
of every book revision. Does not rewrite 001–003.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_portfolio_version"
down_revision: Union[str, None] = "003_risk_run_spec_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolios",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "risk_runs",
        sa.Column("portfolio_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_runs", "portfolio_version")
    op.drop_column("portfolios", "version")
