# Task 31 Report — RF-014 shared-profile ACLs + TLS + secrets

## Task
RF-014 shared-profile object ACLs, TLS terminator, and secret model

## Owner
Backend / API Engineer (`docs/agents/07_BACKEND_API_ENGINEER.md`)

## Status
**CLOSED.** RF-014 **CLOSED** as **MET**. Local demo stays unauthenticated. Not OIDC. Milestone R0 leftover wave remains **IN PROGRESS** (labeled-runner SLA not MET). Did not restore Milestone R0 COMPLETE.

## Summary
Shared profile maps Bearer tokens to principals (`RISKFORGE_API_TOKENS` as `principal:token`, plus existing `RISKFORGE_API_TOKEN`). Authenticated principals cannot read/update another principal’s stored portfolio or its risk runs (403). Seed/demo catalog is owned by principal `demo` (readable; updates by others 403). `docker-compose.shared.yml` puts Caddy TLS on host 443; backend stays internal (`expose` 8000, no host publish). Shared secrets use `${POSTGRES_PASSWORD:?}` and `.env.shared.example`. Local `docker-compose.yml` is unchanged (loopback, unauthenticated, demo DB password allowed). HTTP tests use `with TestClient(app)`. Demo snapshot ids unchanged.

TDD: ACL/compose tests failed first (boot required `RISKFORGE_API_TOKEN`; compose file missing). Close pin failed until FINDINGS status was CLOSED. Then green.

## Files changed
- `backend/app/api/auth.py` — principal token map; request `principal`
- `backend/app/api/acl.py` — shared-profile read/write/run ACL helpers
- `backend/app/api/errors.py` — `http_forbidden`
- `backend/app/api/portfolio.py` — stored GET/PUT with ACL; demo catalog read-only
- `backend/app/api/risk_runs.py` — stamp/check run owner; attach IDOR 403
- `backend/app/api/execution_class.py` — classify `PUT /portfolios/{id}`
- `backend/app/main.py` — lifespan comment
- `backend/app/domain/models.py` — `RiskRun.owner`
- `backend/app/persistence/models.py` — `portfolios.owner`, `risk_runs.owner`
- `backend/app/persistence/sqlalchemy_repos.py` — create/save owner; `get_owner`
- `backend/app/persistence/risk_run_mapping.py` — owner mapping
- `backend/app/services/risk_run_service.py` — enqueue `owner`
- `backend/app/services/risk_run_worker.py` — ACL on attach; stamp owner
- `backend/migrations/versions/005_object_owner.py`
- `backend/tests/test_shared_acls.py`
- `backend/tests/test_shared_compose.py`
- `backend/tests/test_rf020_r0_exit.py` — `OPEN_LEFTOVERS` empty; RF-014 CLOSED pin
- `backend/tests/test_persistence.py` — alembic head `005_object_owner`
- `docker-compose.shared.yml`
- `deploy/Caddyfile`
- `.env.shared.example`
- `.gitignore` — `.env.shared`
- `BUILD_NOTES.md`, `docs/known_limitations.md`
- `reviews/FINDINGS.md`, `reviews/REMEDIATION_MILESTONE.md`, `ROADMAP.md`
- `reviews/r0.11.8-rf014-shared-acls-tls-report.md`
- `reviews/sdd-briefs/task-31-rf014-shared-acls-report.md` — this handoff

## Public/interface changes
- `RISKFORGE_API_TOKENS` / optional `RISKFORGE_API_PRINCIPAL`
- `PUT /portfolios/{portfolio_id}` (and `/api/v1/...`) for stored updates
- `GET /portfolios/{id}` returns stored books with ACL when not a demo catalog id
- 403 `{code: forbidden}` on IDOR
- Alembic `005_object_owner`
- Shared Compose file (not an overlay merge)

## Numerical conventions
- n/a (authz / deployment boundary). Demo snapshot ids unchanged.

## Tests added/updated
- `test_shared_idor_cannot_read_other_principal_stored_portfolio`
- `test_shared_idor_cannot_update_other_principal_stored_portfolio`
- `test_shared_idor_cannot_read_other_principal_risk_run`
- `test_shared_idor_cannot_attach_other_principal_portfolio_to_new_run`
- `test_shared_demo_catalog_stays_readable`
- `test_shared_cannot_update_demo_owned_seed_book`
- `test_local_demo_stays_unauthenticated_without_acls`
- shared compose 443 / no host 8000 / no hardcoded `POSTGRES_PASSWORD=riskforge`
- `test_rf014_shared_acls_tls_secrets_closed`; `OPEN_LEFTOVERS == ()`

## Commands executed
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_shared_acls.py \
  tests/test_shared_compose.py \
  tests/test_shared_auth.py \
  tests/test_rf020_r0_exit.py \
  tests/test_endpoint_execution_class.py \
  tests/test_demo_portfolios.py \
  tests/test_portfolio_identity.py \
  tests/test_risk_run_api.py \
  tests/test_compose_loopback.py \
  tests/test_persistence.py \
  tests/test_api_router_decomposition.py \
  tests/test_api_v1_compatibility.py
.venv/bin/python -m ruff check \
  app/api/auth.py app/api/acl.py app/api/errors.py app/api/portfolio.py \
  app/api/risk_runs.py app/api/execution_class.py app/main.py \
  app/persistence/models.py app/persistence/sqlalchemy_repos.py \
  app/persistence/risk_run_mapping.py app/services/risk_run_service.py \
  app/services/risk_run_worker.py app/domain/models.py \
  tests/test_shared_acls.py tests/test_shared_compose.py \
  tests/test_rf020_r0_exit.py migrations/versions/005_object_owner.py
```

RED: shared ACL tests failed at boot (`RISKFORGE_API_TOKEN` required); compose file missing; RF-014 Status still IN PROGRESS. After implementation: **128 passed**, 1 known Starlette/httpx deprecation warning. Ruff: All checks passed.

## Results
- Backend required suite: **128 passed**, 1 pre-existing Starlette `TestClient` deprecation warning, 20.44s
- Frontend: n/a (UI not changed)
- QuantLib: n/a
- C++: n/a
- Build: n/a
- All tests pass (applicable/affected suites): **yes**
- Unexplained failures or skips: none
- CI is green: not started; no push

## MET vs PARTIAL vs UNMET (this gate)
- Shared object ACLs: **MET**
- Shared TLS terminator (443, API unpublished): **MET**
- Shared secret placeholders: **MET**
- Local demo unauthenticated loopback: **MET**
- OIDC/SSO: not provided (by design)
- HTTP enqueue queue-depth: named leftover, **not MET**
- Labeled-runner SLA: RF-016, **not MET**

## Why CLOSE (not KEEP OPEN)
The three reopened shared cells are on disk with fail-closed HTTP tests. Calling them unmet would ignore the IDOR 403s, Caddy 443 file, and `${POSTGRES_PASSWORD:?}` gate. CLOSE is not a rubber-stamp of R0.11.7 accepted residuals.

## Known limitations / risks
- Not OIDC/SSO/tenant IAM; token map is env-configured
- Caddy uses `tls internal` (self-signed) in the shared Compose file
- Shared compose is standalone (not an overlay) so it cannot inherit local 8000 publishes
- HTTP queued-run depth still uncapped
- `docker run -p 8000:8000` without the shared flag still serves unauthenticated API (not default Compose)

## Follow-up after independent review
Important items fixed: overlapping `RISKFORGE_API_TOKEN` no longer remaps a `TOKENS` principal; `test_shared_null_owner_is_fail_closed`; shared frontend `VITE_API_BASE_URL=same-origin`.

## Next owner
- Labeled-runner SLA (RF-016) still **not MET** — needs a registered `self-hosted, riskforge-sla` runner. Do not restore Milestone R0 COMPLETE until then.

