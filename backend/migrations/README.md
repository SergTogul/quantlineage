# Alembic migration scripts (`script_location = migrations`)

Named `migrations/` (not `alembic/`) so the directory does not shadow the installed `alembic` Python package when pytest runs with `backend/` on `sys.path`.

## Compose / Postgres

Before starting `backend` / `worker` against Compose Postgres:

```bash
export QUANTLINEAGE_DATABASE_URL=postgresql+psycopg://quantlineage:quantlineage@localhost:5432/quantlineage
alembic upgrade head
# or: docker compose run --rm backend alembic upgrade head
```

`create_all` in app wiring is a safety net for SQLite demos; prefer Alembic for Postgres.
