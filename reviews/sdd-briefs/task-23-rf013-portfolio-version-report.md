# Task 23 Report — RF-013 portfolio_version (R0.8.8)

## Task
RF-013 / R0.8.8 — server-owned `portfolio_version`

## Owner
Backend / API Engineer (`docs/agents/07_BACKEND_API_ENGINEER.md`)

## Status
**CLOSE** (RF-013 CLOSED; named residuals accepted in writing)

## Summary
Domain `Portfolio.version` and ORM `portfolios.version` are server-owned integers. Create always stores **1** (client-supplied version ignored). `PortfolioRepository.update` increments only when the caller’s expected version matches; mismatch raises `PortfolioVersionConflict` and leaves the book unchanged. Legacy seed `save` upsert inserts at 1 or bumps on overwrite (no CAS). `RiskRun` / `RiskRunRow.portfolio_version` is copied from the **stored** book at attach-stored submit; execute still uses the current stored book (not a per-revision archive). Alembic `004_portfolio_version`. FINDINGS RF-013 is **CLOSED**. Demo snapshot ids and VaR numbers unchanged.

TDD: version/CAS/alembic pins failed first (no field, alembic still 003). Then green.

## Files changed
- `backend/app/domain/models.py` — `Portfolio.version`; `RiskRun.portfolio_version`
- `backend/app/persistence/models.py` — ORM columns
- `backend/app/persistence/repositories.py` — `PortfolioVersionConflict`; update/save docs
- `backend/app/persistence/sqlalchemy_repos.py` — create=1, CAS update, save bump
- `backend/app/persistence/risk_run_mapping.py` — map `portfolio_version`
- `backend/app/services/risk_run_service.py` — enqueue `portfolio_version`
- `backend/app/services/risk_run_worker.py` — return stored/created book; stamp version at submit
- `backend/app/api/schemas/transport.py` — `RiskRunView.portfolio_version`
- `backend/migrations/versions/004_portfolio_version.py`
- `backend/tests/test_portfolio_identity.py` — version / CAS / submit / HTTP pins
- `backend/tests/test_persistence.py` — schema + alembic `004_portfolio_version`
- `backend/tests/test_postgres_risk_run_lifecycle.py` — version pin when DSN present
- `reviews/FINDINGS.md` — RF-013 **CLOSED**
- `reviews/REMEDIATION_MILESTONE.md` — R0.8.8
- `reviews/r0.8.8-portfolio-version-report.md`
- `reviews/sdd-briefs/task-23-rf013-portfolio-version-report.md` — this handoff

## Public/interface changes
- `Portfolio.version: int` (default 1, `ge=1`); server overwrites on create
- `RiskRun.portfolio_version: int | None` (nullable for pre-R0.8.8 rows)
- `RiskRunView.portfolio_version`
- `PortfolioRepository.update` is compare-and-swap; `PortfolioVersionConflict`
- `RiskRunService.enqueue(..., portfolio_version=)`
- Alembic revision `004_portfolio_version` (`portfolios.version` NOT NULL default 1; `risk_runs.portfolio_version` nullable)
- No VaR/demo snapshot identity change

## Numerical conventions
- Units: unchanged
- Sign convention: unchanged
- Day count/calendar if relevant: n/a
- Tolerances/reference: same-spec exact payload equality (`test_same_spec_parity.py`); no goldens touched

## Tests added/updated
- `test_create_starts_at_version_1_ignoring_client_version`
- `test_update_bumps_version`
- `test_stale_version_update_fails_closed`
- `test_save_upsert_sets_or_bumps_version`
- `test_submit_records_stored_portfolio_version`
- HTTP `global-macro` pin asserts `portfolio_version == 1` and SQL column
- `test_schema_has_expected_tables` / `test_alembic_upgrade_on_sqlite_file` column + head revision
- Postgres lifecycle asserts `accepted.portfolio_version == 1` when DSN present

## Commands executed
TDD red (new pins, before production change):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line \
  tests/test_portfolio_identity.py tests/test_persistence.py \
  -k "version or alembic or schema_has_expected"
```

Result: **7 failed, 15 deselected** (no `version` field; alembic head still `003_risk_run_spec_fields`).

Brief + covering (after implement):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_persistence.py \
  tests/test_portfolio_identity.py \
  tests/test_same_spec_parity.py \
  tests/test_result_payload_schema.py
```

Result: **38 passed**, 1 pre-existing Starlette/httpx `TestClient` deprecation warning.

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_result_payload_schema.py \
  tests/test_persistence.py \
  tests/test_risk_run.py \
  tests/test_risk_run_lifecycle.py \
  tests/test_risk_run_api.py \
  tests/test_risk_run_spec.py \
  tests/test_same_spec_parity.py \
  tests/test_portfolio_identity.py \
  tests/test_durable_worker.py \
  tests/test_postgres_risk_run_lifecycle.py \
  tests/test_domain_transport_split.py \
  tests/test_api_openapi_examples.py \
  tests/test_persistence_di.py
```

Result: **182 passed, 4 skipped** (Postgres DSN absent, existing skip), 1 pre-existing warning.

```bash
.venv/bin/ruff check \
  app/domain/models.py \
  app/persistence/models.py \
  app/persistence/repositories.py \
  app/persistence/sqlalchemy_repos.py \
  app/persistence/risk_run_mapping.py \
  app/services/risk_run_service.py \
  app/services/risk_run_worker.py \
  app/api/schemas/transport.py \
  migrations/versions/004_portfolio_version.py \
  tests/test_portfolio_identity.py
```

All checks passed.

## Results
- Backend required suite: **38 passed** (brief files); covering **182 passed, 4 skipped**
- Ruff: all checks passed (changed files listed above)
- Frontend: n/a
- QuantLib: n/a
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none (4 Postgres skips = no DSN, same rule as R0.8.5)
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## MET vs PARTIAL vs UNMET (this gate)

Acceptance: overwrite `global-macro` **MET** (cite R0.8.6); reproduce from IDs **MET** (cite R0.8.5); Postgres **MET** (cite R0.8.5); unconstrained derived JSON **MET** (cite R0.8.7); `portfolio_id` / `portfolio_version` stored and CAS-checked **MET** (this slice).

Required direction: create vs update **MET**; versioned identities **MET**; server ownership/versioning **MET**; inline calculate **PARTIAL** (accepted residual).

## Why CLOSE
Version is stored, returned, compare-and-swap checked, and stamped on the run header. A dead column would have kept the finding open. Named residuals match the brief (seed `save`; live calculate POST; RF-014 ACLs; client id on first create).

## Known limitations / risks
- Leftover seed `save` upsert (no CAS)
- Live calculate still POSTs a full book
- Object ACLs = RF-014
- Client-chosen id on first create-if-absent
- Run header version is a submit-time stamp; execute uses the current stored book (not a historical archive)

## Follow-up / next owner
- Owner: independent reviewer (Task 23 review)
- Requested action: APPROVE CLOSE RF-013
- Blocking?: no
