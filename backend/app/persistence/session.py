"""Engine and session factory helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.config import DatabaseSettings, get_database_settings


def create_engine_from_url(url: str, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine; enable SQLite FK enforcement."""
    connect_args: dict = {}
    if url.startswith("sqlite:"):
        # Required for :memory: / file SQLite used by CI tests.
        connect_args["check_same_thread"] = False
    engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)
    if url.startswith("sqlite:"):

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _connection_record) -> None:  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(
    settings: DatabaseSettings | None = None,
    *,
    engine: Engine | None = None,
) -> sessionmaker[Session]:
    """Build a sessionmaker bound to ``settings`` or an existing engine."""
    settings = settings or get_database_settings()
    eng = engine or create_engine_from_url(settings.url, echo=settings.echo)
    return sessionmaker(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit on success, rollback on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
