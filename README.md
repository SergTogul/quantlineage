# RiskForge

Institutional-style multi-asset portfolio and derivatives risk management MVP. Pricing is an adapter; portfolio risk, stress, limits, attribution, hierarchy and UI are application-owned.

## Architecture

- **PricingEngine interface**: QuantLib adapter (default in production) + deterministic built-in reference adapter.
- **MarketDataProvider**: immutable `MarketSnapshot` objects for equities, vols, FX and rates.
- **Risk layer**: historical/parametric VaR, Expected Shortfall, component VaR, risk factors, stress/reverse stress, limits, hierarchy and attribution.
- **Compute kernel**: Python reference kernel plus optional C++20/`ctypes` scenario kernel.
- **API**: FastAPI.
- **UI**: React/Vite risk terminal with scenario builder, reverse stress and deterministic risk query.

## Instruments

- Equities
- Equity futures
- European equity options
- Bonds
- Vanilla interest-rate swaps
- FX forwards
- European FX options

QuantLib currently handles the original equity option/bond/swap path. New product types use the reference adapter until native QuantLib implementations are added; this is isolated behind `PricingEngine`.

## Risk capabilities

- Delta, gamma, vega, DV01 and FX delta
- Risk-factor/bucket aggregation
- Historical-style VaR / Expected Shortfall
- Parametric VaR / Expected Shortfall
- Component VaR by position
- Stress and threat scenario evaluation
- Instrument-specific and multi-factor shocks
- Custom scenario builder
- Reverse stress solving
- Before/after hedge scenario comparison
- Risk limits and breaches
- Portfolio → desk → strategy → book → trade hierarchy
+ Firm → Portfolio → Desk → Strategy → Book → Trade hierarchy (position desk/strategy optional; defaults from portfolio)
- P&L attribution across position, equity, vol, rate and FX changes
- Deterministic natural-language query router ready to sit behind an LLM tool layer

## Demo data (M10)

- **Portfolios (M10.1):** in-code themes via `GET /api/v1/portfolios` (`backend/app/sample.py`).
- **Historical factors (M10.2):** packaged CSV `data/demo_historical_factors.csv` (synthetic replay — **no live vendors**). Load with `load_demo_historical_dataset()` or set `RISKFORGE_HISTORICAL_DATASET=demo|synthetic|/path/to.csv`. Details: [`data/README.md`](data/README.md).
- **Deterministic scripts (M10.3):** `python -m app.demo.run_demo_risk` (or `scripts/run_demo_risk.py`) emits byte-stable VaR/stress JSON for all demo books; frozen sample: [`data/demo_risk_artifact.json`](data/demo_risk_artifact.json).

## Main API endpoints

**Canonical prefix:** `/api/v1` (M7.6). Legacy unversioned paths remain dual-mounted
and deprecated until the published sunset — see
[`docs/api/v1_canonical_and_legacy_sunset.md`](docs/api/v1_canonical_and_legacy_sunset.md).
Multi-factor reverse-stress limitations (M3.9):
[`docs/methodology/multi_factor_reverse_stress.md`](docs/methodology/multi_factor_reverse_stress.md).

```text
GET  /api/v1/health
GET  /api/v1/portfolio
POST /api/v1/market/snapshot
POST /api/v1/risk/summary
POST /api/v1/risk/factors
POST /api/v1/risk/var
POST /api/v1/risk/hierarchy
POST /api/v1/risk/attribution
POST /api/v1/risk/attribution/demo
POST /api/v1/risk/contributors
POST /api/v1/risk/limits
POST /api/v1/risk/stress
GET  /api/v1/risk/stress/scenarios
POST /api/v1/risk/stress/evaluate
POST /api/v1/risk/stress/evaluate/custom
POST /api/v1/risk/stress/reverse
POST /api/v1/risk/stress/compare
POST /api/v1/risk/query
POST /api/v1/risk/runs
GET  /api/v1/risk/runs/{run_id}
```

Unversioned aliases (e.g. `/health`, `/risk/summary`) still work but return
`Deprecation` / `Sunset` / `Link` headers pointing at the `/api/v1` successor.
## Run backend

Requires **Python 3.12+** (`numpy>=2.3`). On macOS 13 where Homebrew Python 3.12 may not build, install via [uv](https://github.com/astral-sh/uv): `uv python install 3.12`.

```bash
cd backend
python3.12 -m venv .venv   # or: uv python install 3.12 && ~/.local/share/uv/python/.../python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
RISKFORGE_PRICING_ENGINE=quantlib uvicorn app.main:app --reload
```

For development/testing without QuantLib:

```bash
RISKFORGE_PRICING_ENGINE=builtin uvicorn app.main:app --reload
```

## Persistence (M5.1 / M5.6 / M5.7)

SQLAlchemy + Alembic live under `backend/app/persistence/`. When `RISKFORGE_DATABASE_URL` is set, FastAPI lifespan wires SQLAlchemy for portfolios, market snapshots, scenario definitions, limit definitions, and risk runs (M5.6); otherwise in-memory / sample defaults are used. Unit tests use SQLite; Compose provides Postgres; CI runs `postgres-smoke` via `scripts/smoke_postgres.sh`.

**Postgres DSN (Compose / local):**

```text
postgresql+psycopg://riskforge:riskforge@localhost:5432/riskforge
```

Inside Compose, services use host `postgres` instead of `localhost` via `RISKFORGE_DATABASE_URL`.

```bash
# Start Postgres
docker compose up -d postgres

# Apply migrations (required before API/worker against Postgres)
export RISKFORGE_DATABASE_URL=postgresql+psycopg://riskforge:riskforge@localhost:5432/riskforge
cd backend && alembic upgrade head

# Or via Compose image:
# docker compose run --rm backend alembic upgrade head

# Minimal seed / repo smoke (same script as CI postgres-smoke job)
./scripts/smoke_postgres.sh

# API + out-of-process worker + frontend (M5.7)
docker compose up -d backend worker frontend
```

**Durable worker (M5.7):** Compose `worker` runs `python -m app.worker`, claiming `QUEUED` risk runs from shared Postgres via `claim_queued` (`SELECT … FOR UPDATE SKIP LOCKED` → `RUNNING`). Compose `backend` sets `RISKFORGE_EXTERNAL_WORKER=1` so HTTP only enqueues. Without that flag (local uvicorn default), the API still executes runs in-process via `ThreadPoolExecutor`. Compose defaults to one worker for the demo; additional Postgres-backed replicas will not double-claim the same row. SQLite unit tests use a non-skip-locked FIFO claim (single-writer). Redis/RQ is not required for claim safety.

SQLite (dev / CI default when `RISKFORGE_DATABASE_URL` is unset): `sqlite:///:memory:` for tests, or set a file URL and run `alembic upgrade head`.
See `docs/adr/005-sqlalchemy-persistence.md`.

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin pytest -q

# M9.7 static analysis (also CI job lint-static-analysis)
pip install -r requirements-dev.txt   # includes ruff + mypy
ruff check app tests
mypy app

cd ../frontend
npm test
npm run lint   # eslint src --max-warnings 0

cd ../e2e
npm install && npm run install:browsers
npm test
# CI job e2e-playwright runs the same suite with Chromium (see e2e/README.md)
```

Playwright boots the builtin-engine API and Vite app, then covers dashboard smoke, Scenario Builder, Reverse Stress, Risk Query, and M8 panels. See `e2e/README.md`.

The backend native-kernel tests compile and execute C++20 with `g++` when a compiler is available. QuantLib runtime tests skip only when the QuantLib wheel is absent.

## Optional native scenario kernel

```bash
cd backend/native
g++ -std=c++20 -O3 -shared -fPIC -pthread -I include \
  src/risk_kernel_capi.cpp -o libriskkernel.so
```

Load it with `app.compute.kernel.NativeScenarioKernel`. No pybind11 is required for this MVP seam.

Optional worker count for the C++ stdlib shock-partition thread pool (M6.4;
`std::jthread` when available, else `std::thread`+join; not OpenMP):

```bash
export RISKFORGE_KERNEL_THREADS=4   # 1 = serial; unset = hardware_concurrency
```

Historical VaR **LINEAR** / **DELTA_GAMMA** approximate P&L can use the kernel behind:

```bash
export RISKFORGE_SCENARIO_KERNEL=native   # default: python (NumPy)
export RISKFORGE_SCENARIO_KERNEL_LIB=/abs/path/to/libriskkernel.so  # optional
```

`FULL_REVALUATION` never uses this kernel (full PricingEngine revaluation). See
`backend/native/README.md`. Parity tests: `backend/tests/test_historical_scenario_kernel.py`.

Reproducible scenario-aggregation microbenchmarks (Python / NumPy / ctypes / C++) live under
`benchmarks/` — see `benchmarks/README.md`. Those timings are environment-specific and are
**not** production SLAs.

## Design rule

**The pricing library prices; RiskForge manages portfolio risk.** QuantLib/OpenGamma-style analytics can be replaced or extended without rewriting the portfolio-risk workflows.

## Code intelligence (CodeGraph)

This repo can be indexed locally with [CodeGraph](https://github.com/colbymchenry/codegraph) so Cursor and other agents can query symbols, call paths, and blast radius via MCP.

```bash
# Install CLI (once): npm i -g @colbymchenry/codegraph
codegraph init    # creates .codegraph/ (local index, gitignored)
codegraph status  # index stats
codegraph query VaR
```

The SQLite index under `.codegraph/` is machine-local; re-run `codegraph init` or rely on auto-sync after cloning.
