"""RF-014: object owner on stored portfolios and risk runs.

Revision ID: 005_object_owner
Revises: 004_portfolio_version
Create Date: 2026-09-09

Adds nullable portfolios.owner and risk_runs.owner. Seed/demo catalog
rows use principal ``demo``. Shared-profile ACLs fail closed when owner
is missing. Does not rewrite 001–004.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_object_owner"
down_revision: Union[str, None] = "004_portfolio_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("owner", sa.String(length=128), nullable=True))
    op.add_column("risk_runs", sa.Column("owner", sa.String(length=128), nullable=True))
    op.execute("UPDATE portfolios SET owner = 'demo' WHERE owner IS NULL")


def downgrade() -> None:
    op.drop_column("risk_runs", "owner")
    op.drop_column("portfolios", "owner")
