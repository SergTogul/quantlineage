"""R0.8.1: first-class RiskRun specification columns.

Revision ID: 003_risk_run_spec_fields
Revises: 002_risk_run_domain_fields
Create Date: 2026-09-03

Adds historical_dataset_id, historical_dataset_version, as_of,
calculation_config. All nullable so pre-spec rows stay valid.
Does not rewrite 001 or 002.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_risk_run_spec_fields"
down_revision: Union[str, None] = "002_risk_run_domain_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "risk_runs",
        sa.Column("historical_dataset_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "risk_runs",
        sa.Column("historical_dataset_version", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "risk_runs",
        sa.Column("as_of", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "risk_runs",
        sa.Column("calculation_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_runs", "calculation_config")
    op.drop_column("risk_runs", "as_of")
    op.drop_column("risk_runs", "historical_dataset_version")
    op.drop_column("risk_runs", "historical_dataset_id")
