# Alembic migration scripts (`script_location = migrations`)

Named `migrations/` (not `alembic/`) so the directory does not shadow the installed `alembic` Python package when pytest runs with `backend/` on `sys.path`.

## Compose / Postgres

Before starting `backend` / `worker` against Compose Postgres:

```bash
export RISKFORGE_DATABASE_URL=postgresql+psycopg://riskforge:riskforge@localhost:5432/riskforge
alembic upgrade head
# or: docker compose run --rm backend alembic upgrade head
```

`create_all` in app wiring is a safety net for SQLite demos; prefer Alembic for Postgres.
