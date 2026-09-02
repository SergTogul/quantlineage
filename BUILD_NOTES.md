# Verification

Final verification in the execution sandbox:

- Backend pytest: **32 passed, 1 skipped**. The skip is QuantLib-runtime-specific because the QuantLib wheel is unavailable in this sandbox.
- Frontend unit tests: **10 passed**.
- Python compileall: passed.
- Native C++20 kernel: compiled and executed successfully with `g++`.
- C++ benchmark workload: 50,000 exposures x 1,000 scenarios executed in 44 ms in this sandbox run (environment-specific, not a production benchmark claim).
- Repo-root harness (M6.1/M6.2/M6.4): `benchmarks/run_scenario_bench.py` — see `benchmarks/README.md` and `benchmarks/RESULTS.md` (M6.4 parallel `std::thread` shock partitions; ~2× vs serial at 10k×1k / 4 threads on the capture host — not a production SLA).
- FastAPI live smoke: `/health`, `/portfolio`, `/risk/var`, `/risk/stress/evaluate` passed.
- Service was stopped after smoke testing; port 8000 is not left listening.
- `npm run build`: blocked because Vite is not installed locally and external npm registry access is unavailable in this sandbox. `npm test` succeeds because the unit suite uses Node's built-in test runner.

## M9.7 Static analysis CI (2026-09-02, DevOps)

- Backend: `pip install -r requirements-dev.txt` then `ruff check app tests` and `mypy app` (config in `backend/pyproject.toml`).
- Frontend: `npm run lint` (`eslint.config.js`; `--max-warnings 0`).
- CI: `.github/workflows/ci.yml` job `lint-static-analysis`.
- Staged: not full-strict — see ROADMAP M9.7 for ignored Ruff rules and mypy `disable_error_code` debt list.
- Follow-up `8d7a6f2`: lint CI installs numpy (mypy `numpy.typing`); Historical VaR kernel tests keep absolute `TOL` / `assert_allclose` imports.

## M9.2 / M9.10 Playwright E2E CI (2026-09-02, DevOps/QA)

- Local: `cd e2e && npm install && npm run install:browsers && npm test` (Chrome channel; `backend/.venv`).
- CI: `.github/workflows/ci.yml` job `e2e-playwright` — backend pip (QuantLib optional), frontend + e2e `npm ci`, `npm run install:browsers:ci`, `CI=true npm test`.
- Config: when `CI` is set, use Playwright Chromium + `python -m uvicorn` if `.venv` is absent.

## M9.9 / M5.1 Postgres CI smoke (2026-09-02, DevOps)

### Local Compose (green)

```bash
docker compose up -d postgres
export RISKFORGE_DATABASE_URL=postgresql+psycopg://riskforge:riskforge@localhost:5432/riskforge
# PATH must include backend/.venv (alembic, sqlalchemy, psycopg[binary])
./scripts/smoke_postgres.sh
```

Result: **exit 0**. Alembic applied `001_initial_persistence` → `002_risk_run_domain_fields`; seed wiring asserted portfolio + snapshot + scenarios + limits. Idempotent second run also exit 0. Script path works from repo root and from `backend/` (as GHA `working-directory: backend` does).

### GitHub-hosted runners (blocked — not green-proved)

- `.github/workflows/ci.yml` job `postgres-smoke` uses `postgres:16-alpine` service + same URL/script.
- This checkout had **no `git remote`**, no GitHub Actions history, and **`gh` was not installed** — cannot record a runner URL/conclusion.
- M9.9 remains open until a push produces a green Actions run and the URL is recorded in `ROADMAP.md`.

### QuantLib install path (CI)

- Main `backend` job: `pip install -r requirements.txt` (includes QuantLib); on failure, strip QuantLib line and continue with builtin (`RISKFORGE_PRICING_ENGINE` detected via import).
- `postgres-smoke` does not require QuantLib; same install fallback so persistence proof is independent of the QL wheel.
