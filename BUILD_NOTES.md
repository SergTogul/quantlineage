# Verification

Final verification in the execution sandbox:

- Backend pytest: **32 passed, 1 skipped**. The skip is QuantLib-runtime-specific because the QuantLib wheel is unavailable in this sandbox.
- Frontend unit tests: **10 passed**.
- Python compileall: passed.
- Native C++20 kernel: compiled and executed successfully with `g++`.
- C++ benchmark workload: 50,000 exposures x 1,000 scenarios executed in 44 ms in this sandbox run (environment-specific, not a production benchmark claim).
- Repo-root harness : `benchmarks/run_scenario_bench.py` — see `benchmarks/README.md` and `benchmarks/RESULTS.md` ( parallel `std::thread` shock partitions; ~2× vs serial at 10k×1k / 4 threads on the capture host — not a production SLA).
- FastAPI live smoke: `/health`, `/portfolio`, `/risk/var`, `/risk/stress/evaluate` passed.
- Service was stopped after smoke testing; port 8000 is not left listening.
- `npm run build`: blocked because Vite is not installed locally and external npm registry access is unavailable in this sandbox. `npm test` succeeds because the unit suite uses Node's built-in test runner.

## Documentation package (Workstream 12)

Recruiter/interviewer-facing documentation now lives in:

- `README.md` for the project entry point, demo path, architecture summary, and limitations.
- `docs/architecture.md` for system boundaries, dependency direction, and ownership.
- `docs/adr/README.md` for the ADR index/status.
- `docs/methodology/README.md` for VaR/ES, stress, reverse stress, pricing scope, and AI guardrails.
- `docs/performance.md` for the scoped scenario-kernel performance claim and non-claims.
- `docs/known_limitations.md` for the limitations catalog.

This is a documentation-only package. It does not change risk, pricing, API, frontend, persistence, or native-kernel behavior.

## Static analysis CI (2026-09-02, DevOps)

- Backend: `pip install -r requirements-dev.txt` then `ruff check app tests` and `mypy app` (config in `backend/pyproject.toml`).
- Frontend: `npm run lint` (`eslint.config.js`; `--max-warnings 0`).
- CI: `.github/workflows/ci.yml` job `lint-static-analysis`.
- Staged: not full-strict — see ROADMAP for ignored Ruff rules and mypy `disable_error_code` debt list.
- Follow-up `8d7a6f2`: lint CI installs numpy (mypy `numpy.typing`); Historical VaR kernel tests keep absolute `TOL` / `assert_allclose` imports.

## Frontend Vitest / RTL / MSW (2026-09-02, QA)

- Dual-run: `cd frontend && npm test` → `test:node` (lib helpers) + `test:vitest` (components).
- Harness: `vite.config.js` `test` block; `src/test/setup.js` (jest-dom + MSW lifecycle); `src/test/mswServer.js` (fixed API fixtures).
- Watch: `npm run test:watch`. Lib `*.test.mjs` remain on node:test until migrated.

## Playwright E2E CI (2026-09-02, DevOps/QA)

- Local: `cd e2e && npm install && npm run install:browsers && npm test` (Chrome channel; `backend/.venv`).
- CI: `.github/workflows/ci.yml` job `e2e-playwright` — backend pip (QuantLib optional), frontend + e2e `npm ci`, `npm run install:browsers:ci`, `CI=true npm test`.
- Config: when `CI` is set, use Playwright Chromium + `python -m uvicorn` if `.venv` is absent.

## Postgres CI smoke (2026-09-02, DevOps)

### Local Compose (green)

```bash
docker compose up -d postgres
# Default Compose publishes bind to loopback only (127.0.0.1).
export RISKFORGE_DATABASE_URL=postgresql+psycopg://riskforge:riskforge@localhost:5432/riskforge
# PATH must include backend/.venv (alembic, sqlalchemy, psycopg[binary])
./scripts/smoke_postgres.sh
```

Result: **exit 0**. Alembic applied `001_initial_persistence` → `002_risk_run_domain_fields`; seed wiring asserted portfolio + snapshot + scenarios + limits. Idempotent second run also exit 0. Script path works from repo root and from `backend/` (as GHA `working-directory: backend` does).

### GitHub-hosted runners (green)

- `.github/workflows/ci.yml` job `postgres-persistence-smoke` uses a `postgres:16-alpine` service + the same URL/script.
- Green runner evidence is recorded in `ROADMAP.md`: https://github.com/SergTogul/riskforge-mvp/actions/runs/33712643872.
- The Postgres smoke remains the CI proof for the durable persistence path; unit tests use SQLite or in-memory repos for speed.

## Risk-run queue / worker residual (2026-09-03)

- RiskForge does **not** ship Redis/RQ in the MVP. The accepted queue mechanism is `risk_runs` rows in Postgres, claimed by `python -m app.worker` via `SELECT ... FOR UPDATE SKIP LOCKED` and transitioned `QUEUED -> RUNNING`.
- Redis/RQ was evaluated as optional ops/fair-scheduling infrastructure, not as a claim-safety requirement. Adding it without priority, tenancy, retries, or observability semantics would be empty ceremony.
- Compose still ships one worker for the demo. Additional Postgres-backed worker replicas are safe from double-claim; SQLite remains a single-writer/unit-test fallback without `SKIP LOCKED`.
- API submit semantics remain stable: `POST /risk/runs` returns a queued acceptance snapshot, while `GET /risk/runs/{id}` reports current status/results.

### QuantLib install path (CI)

- Main `backend` job: `pip install -r requirements.txt` (includes QuantLib); on failure, strip QuantLib line and continue with builtin (`RISKFORGE_PRICING_ENGINE` detected via import).
- `postgres-smoke` does not require QuantLib; same install fallback so persistence proof is independent of the QL wheel.

## Nightly / labeled runner (R0.12.4)

Heavier checks live in `.github/workflows/nightly.yml` (`schedule` daily 06:00 UTC + `workflow_dispatch`). They are **not** on `pull_request` and must **not** be added to PR-FULL `needs:`.

What actually runs (not echo-only):

- Native benchmark binary: compile `backend/native/src/benchmark.cpp` and run `10k × 1k` (`--threads 4 --json`) asserting `impl` / `checksum` identity (not SLA-K1/K2; `check_m6_sla.py` is not run on `ubuntu-latest`), then `benchmarks/run_scenario_bench.py --workload 1k_x_1k`.
- Postgres two-worker claim: GHA `postgres:16-alpine` service + `scripts/smoke_postgres.sh` + `RISKFORGE_NIGHTLY=1 pytest tests/test_postgres_two_worker.py`.
- Larger FULL_REVALUATION sample: `RISKFORGE_NIGHTLY=1 pytest tests/test_nightly_full_reval_sample.py` (120 observations).
- QuantLib critical E2E (`quantlib-e2e`): mandatory `pip install -r requirements.txt` (no no-ql fallback) + `import QuantLib`, then Playwright `tests/r0-critical-journey.spec.ts` with `RISKFORGE_PRICING_ENGINE=quantlib` and `RISKFORGE_REQUIRE_QUANTLIB=1`. Missing QuantLib **fails** when `RISKFORGE_NIGHTLY=1` (no skip-green). PR `e2e-playwright` stays builtin.
- Hierarchy identity (`hierarchy-benchmark`): `benchmarks/run_hierarchy_bench.py --json` on a 64-trade / 94-node book. Asserts `impl`, `n_positions`, `n_nodes`, `market_value`, additive reconciliation, and SHA-256 checksum. Wall time is recorded, not SLA-gated (`check_m6_sla.py` is not run; a positive throughput reading is not an SLA).

Local Docker/Postgres is **optional** for laptop pytest. `tests/test_postgres_two_worker.py` skips when `CI` and `RISKFORGE_NIGHTLY` are unset and `RISKFORGE_DATABASE_URL` is missing or unreachable. When `RISKFORGE_NIGHTLY` is set, a missing or unreachable DSN **fails**. When `CI` is set and a postgresql DSN is offered, an unreachable DSN **fails** (no skip-green). `CI` plus an unset DSN still skips so PR `backend-pytest` is not broken. That skip does **not** apply to PR `postgres-persistence-smoke`, which is unchanged. To run the two-worker test locally:

```bash
docker compose up -d postgres
export RISKFORGE_DATABASE_URL=postgresql+psycopg://riskforge:riskforge@localhost:5432/riskforge
./scripts/smoke_postgres.sh
cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_postgres_two_worker.py
```

## Local Compose resource expectations (R0.11.6)

Default `docker compose up` (Postgres 16 + API + one risk-run worker + nginx frontend) is a laptop demo, not a capacity SLA. Budget about **2 CPU cores and 2–3 GiB RAM** for idle/light dashboard traffic with the packaged books. FULL_REVALUATION, large `observations` counts, or enabling the native scenario kernel can use more CPU on the API/worker; Postgres stays small for the seeded demo schema. Images drop to a non-root `USER` where practical (backend `riskforge`, frontend `nginx`); Compose still publishes only on loopback (R0.11.1).

## Local vs shared vs not production-like (R0.11.5)

Three deployment profiles, not a production IAM story:

| Profile | How it is selected | Auth |
|---|---|---|
| **Local demo** | Default. Compose publishes `127.0.0.1` only. `RISKFORGE_BIND` unset or in `{127.0.0.1, localhost, ::1}`. `RISKFORGE_SHARED_DEPLOYMENT` unset. | None. Laptop `uvicorn` / default Compose stay unauthenticated. |
| **Shared / non-loopback** | Set `RISKFORGE_SHARED_DEPLOYMENT=1`, or set `RISKFORGE_BIND` to a non-loopback address (e.g. `0.0.0.0`). | Fail closed: process refuses to boot without `RISKFORGE_API_TOKEN`. `/api` and dual-mount routes require `Authorization: Bearer <token>` (401 otherwise). `/health`, `/docs`, `/redoc`, `/openapi.json` stay open. |
| **Not production-like** | Anything beyond the shared-token gate. | Not provided. No OIDC/SSO, no object ACLs, no in-app TLS, no secret manager, no tenant isolation. Demo DB password and unpublished-Postgres leftovers remain. Do not treat this repo as internet-ready. |

In-container `uvicorn --host 0.0.0.0` (backend Dockerfile) is not a host publish. Default Compose still binds host ports to loopback and does **not** set the shared flag. Operators who publish the API beyond loopback must set `RISKFORGE_SHARED_DEPLOYMENT=1` (or `RISKFORGE_BIND=0.0.0.0`) **and** `RISKFORGE_API_TOKEN`.

```bash
# Shared profile example (still not production-like):
export RISKFORGE_SHARED_DEPLOYMENT=1
export RISKFORGE_API_TOKEN='replace-me'
# curl -H "Authorization: Bearer $RISKFORGE_API_TOKEN" http://127.0.0.1:8000/api/v1/portfolio
```

## Interactive vs heavy endpoints (R0.10.1)

Classification contract only (`backend/app/api/execution_class.py`). No job platform, no numerical-method change, no extra auth.

- **Interactive:** completed-run `GET /risk/runs/{run_id}`, lightweight `POST /risk/summary` (default LINEAR / DELTA_GAMMA), small `POST /risk/factors` and `POST /risk/limits/drilldown`, health / portfolio catalog, scenario-definition GETs, `POST /market/snapshot`.
- **Heavy (not interactive-only):** FULL_REVALUATION-bearing compute (`POST /risk/var`, `/es`, `/var/compare`), `POST /risk/hierarchy`, `POST /risk/stress/reverse/multi`, `POST /risk/what-if`, large scenario eval (`/stress/evaluate` and custom/formal variants), contribution (`/contributors`, `/change-attribution`, `/es`). Other synchronous compute POSTs (stress, attribution, limits, query, `POST /risk/runs` enqueue) are also HEAVY in the map.
- `methodology=FULL_REVALUATION` upgrades methodology-bearing routes (including summary) to HEAVY.
- Dual-mount `/api/v1` shares the same class. This map does not enqueue or reject requests; R0.10.2/R0.10.3 own batching and backpressure.

## Dashboard batch (R0.10.2)

`POST /risk/dashboard` (dual-mounted at `/api/v1/risk/dashboard`) returns the UI payload keys `{portfolio, summary, stress, threats, contributors, limits, factors, varReport, hierarchy, attribution}` from one request. `loadDashboard()` calls that path only. Classified HEAVY (includes hierarchy / VaR / evaluate). Sequential existing service methods — not a RiskRun job platform; work still runs on the request thread (R0.10.3).

## Performance reporting

The current performance report is intentionally scoped:

- Formal claim: native C++20 `ctypes` scenario-kernel relative SLA on workload `10k_x_1k`, documented in `docs/performance.md` and `benchmarks/RESULTS.md`.
- Verification command: `backend/.venv/bin/python benchmarks/check_m6_sla.py`.
- Non-claims: HTTP endpoint latency, queued risk-run latency, FULL_REVALUATION acceleration, QuantLib pricing speedup, and multi-tenant capacity planning.
