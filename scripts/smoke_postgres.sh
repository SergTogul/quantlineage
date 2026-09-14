#!/usr/bin/env bash
# Minimal Postgres persistence smoke (M5.1 / M5.6 / M9.9).
#
# Requires:
#   - QUANTLINEAGE_DATABASE_URL pointing at a reachable Postgres (psycopg3 URL)
#   - backend deps installed (sqlalchemy, alembic, psycopg, …)
#
# Usage (local Compose):
#   docker compose up -d postgres
#   export QUANTLINEAGE_DATABASE_URL=postgresql+psycopg://quantlineage:quantlineage@localhost:5432/quantlineage
#   ./scripts/smoke_postgres.sh
#
# CI: GitHub Actions service container sets the URL and runs this script.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

URL="${QUANTLINEAGE_DATABASE_URL:-}"
if [[ -z "${URL// }" ]]; then
  echo "ERROR: QUANTLINEAGE_DATABASE_URL must be set (postgresql+psycopg://…)" >&2
  exit 1
fi

export QUANTLINEAGE_DATABASE_URL="$URL"
export PYTHONPATH="${PYTHONPATH:-.}"

# Wait for Postgres (Compose health / GHA service container can lag first connect).
echo "==> wait for Postgres"
python - <<'PY'
from __future__ import annotations

import os
import sys
import time

import psycopg
from sqlalchemy.engine.url import make_url

url = make_url(os.environ["QUANTLINEAGE_DATABASE_URL"])
# SQLAlchemy uses postgresql+psycopg://…; psycopg.connect wants postgresql://…
dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
deadline = time.monotonic() + 60
last_err: BaseException | None = None
while time.monotonic() < deadline:
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        print("postgres accepting connections")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — retry until deadline
        last_err = exc
        time.sleep(1)
print(f"ERROR: Postgres not ready within 60s: {last_err}", file=sys.stderr)
sys.exit(1)
PY

echo "==> alembic upgrade head ($QUANTLINEAGE_DATABASE_URL)"
alembic upgrade head

echo "==> Python wiring / seed / repo smoke"
python - <<'PY'
from __future__ import annotations

from app.persistence.config import get_configured_database_url
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyLimitDefinitionRepository,
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyScenarioDefinitionRepository,
)
from app.persistence.wiring import (
    DEFAULT_MARKET_SNAPSHOT_ID,
    DEFAULT_PORTFOLIO_ID,
    build_persistence_wiring,
    default_limit_id,
    default_seed_scenarios,
)
from app.risk.limits import DEFAULT_LIMITS
from app.sample import SAMPLE_PORTFOLIO

url = get_configured_database_url()
assert url and url.startswith("postgresql"), f"expected postgres URL, got {url!r}"

# ensure_schema=False: rely on Alembic (create_all would mask migration gaps).
wiring = build_persistence_wiring(seed_sample=True, ensure_schema=False)
assert wiring.enabled is True
assert wiring.session_factory is not None

with session_scope(wiring.session_factory) as session:
    portfolio = SqlAlchemyPortfolioRepository(session).get(DEFAULT_PORTFOLIO_ID)
    assert portfolio is not None, "sample portfolio missing"
    assert portfolio.id == SAMPLE_PORTFOLIO.id
    assert len(portfolio.positions) == len(SAMPLE_PORTFOLIO.positions)

    snap = SqlAlchemyMarketSnapshotRepository(session).get(DEFAULT_MARKET_SNAPSHOT_ID)
    assert snap is not None, "sample market snapshot missing"
    assert snap.id == DEFAULT_MARKET_SNAPSHOT_ID

    scenarios = SqlAlchemyScenarioDefinitionRepository(session).list_all()
    expect_scenarios = {s.id or s.name for s in default_seed_scenarios()}
    got_scenarios = {s.id or s.name for s in scenarios}
    missing = expect_scenarios - got_scenarios
    assert not missing, f"missing scenarios: {sorted(missing)}"

    limits = dict(SqlAlchemyLimitDefinitionRepository(session).list_for_portfolio(None))
    for lim in DEFAULT_LIMITS:
        lid = default_limit_id(lim)
        assert lid in limits, f"missing limit {lid}"
        assert limits[lid].metric == lim.metric

print("postgres smoke OK: portfolio + snapshot + scenarios + limits")
PY

echo "==> smoke_postgres.sh complete"
