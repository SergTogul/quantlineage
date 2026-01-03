"""SQLAlchemy declarative base shared by ORM models and Alembic."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Metadata root for RiskForge persistence tables."""
