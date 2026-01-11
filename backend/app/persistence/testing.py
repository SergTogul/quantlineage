"""Test helpers: create schema on SQLite without requiring live Postgres."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Import models so metadata is populated before create_all.
from app.persistence import models as _models  # noqa: F401
from app.persistence.base import Base
from app.persistence.session import create_engine_from_url


def make_sqlite_engine(url: str = "sqlite:///:memory:") -> Engine:
    """In-memory (or file) SQLite engine with tables created."""
    engine = create_engine_from_url(url, echo=False)
    Base.metadata.create_all(engine)
    return engine


def make_sqlite_session_factory(url: str = "sqlite:///:memory:") -> sessionmaker[Session]:
    engine = make_sqlite_engine(url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
