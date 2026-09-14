"""Database URL and engine settings.

Production / Compose default DSN (psycopg3 driver)::

    postgresql+psycopg://quantlineage:quantlineage@localhost:5432/quantlineage

Inside the Compose network, host is ``postgres`` instead of ``localhost``.
Override with ``QUANTLINEAGE_DATABASE_URL``. CI and unit tests use SQLite
(``sqlite:///:memory:`` or a temp file) so Postgres is not required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Documented Compose / local Postgres DSN (see docker-compose.yml).
DEFAULT_POSTGRES_DSN = "postgresql+psycopg://quantlineage:quantlineage@localhost:5432/quantlineage"
DEFAULT_SQLITE_DSN = "sqlite:///:memory:"


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Resolved connection settings for the persistence layer."""

    url: str
    echo: bool = False

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite:")

    @property
    def is_postgres(self) -> bool:
        return self.url.startswith("postgresql")


def get_configured_database_url() -> str | None:
    """Return ``QUANTLINEAGE_DATABASE_URL`` when explicitly set (non-blank).

    Unlike ``get_database_settings``, this does **not** fall back to the
    default SQLite DSN. FastAPI DI uses this to keep sample/memory mode
    when the env var is unset (M5.6).
    """
    raw = os.environ.get("QUANTLINEAGE_DATABASE_URL")
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _env_flag(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def external_worker_enabled() -> bool:
    """When true, API enqueues QUEUED runs but does not execute them locally.

    Compose sets ``QUANTLINEAGE_EXTERNAL_WORKER=1`` on ``backend`` so the
    ``worker`` service (``python -m app.worker``) drains the shared Postgres
    queue in a **separate OS process** (R0.3.5 QuantLib process partition).
    Unset → in-process ThreadPoolExecutor job scheduler (default for unit
    tests); QuantLib still takes ``_QL_PROCESS_LOCK``.
    """
    return _env_flag("QUANTLINEAGE_EXTERNAL_WORKER")


def get_database_settings(
    *,
    url: str | None = None,
    echo: bool | None = None,
) -> DatabaseSettings:
    """Load settings from explicit args or environment.

    Env vars:
    - ``QUANTLINEAGE_DATABASE_URL`` — SQLAlchemy URL (Postgres or SQLite)
    - ``QUANTLINEAGE_DB_ECHO`` — ``1`` / ``true`` to log SQL
    """
    resolved = url or get_configured_database_url() or DEFAULT_SQLITE_DSN
    if echo is None:
        raw = os.environ.get("QUANTLINEAGE_DB_ECHO", "").strip().lower()
        echo = raw in {"1", "true", "yes", "on"}
    return DatabaseSettings(url=resolved, echo=bool(echo))
