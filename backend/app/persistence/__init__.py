"""PostgreSQL / SQLAlchemy persistence boundary (M5.1).

Stores JSON-serializable domain payloads only. Never persist QuantLib
handles, curve objects, or other pricing-engine runtime state.
"""

from app.persistence.config import (
    DatabaseSettings,
    get_configured_database_url,
    get_database_settings,
)
from app.persistence.session import create_engine_from_url, create_session_factory, session_scope
from app.persistence.wiring import (
    PersistenceWiring,
    build_persistence_wiring,
    load_market_snapshot,
    load_portfolio,
)

__all__ = [
    "DatabaseSettings",
    "get_configured_database_url",
    "get_database_settings",
    "create_engine_from_url",
    "create_session_factory",
    "session_scope",
    "PersistenceWiring",
    "build_persistence_wiring",
    "load_portfolio",
    "load_market_snapshot",
]
