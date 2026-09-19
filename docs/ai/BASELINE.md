# OpenAI Risk Assistant — Baseline (T00)

Captured on branch `feature/openai-risk-assistant` before AI provider wiring. No product code was changed for this task.

## Python version

| Context | Version |
|---------|---------|
| Backend Docker image (`backend/Dockerfile`) | **Python 3.13** (`python:3.13-slim`) |
| This agent / local test run | **Python 3.12.3** |

Acceptance tests below were run with Python 3.12.3 after `pip install -r backend/requirements.txt`. CI and Compose builds target 3.13 via the Dockerfile.

## Exact test commands and results

All checks passed (2026-09-19).

```bash
cd backend
python3 -m pytest tests/test_ai_query_orchestration.py -q
# 20 passed, 2 warnings in 2.40s

python3 -m pytest -q -k "mcp or risk_query"
# 11 passed, 1834 deselected, 2 warnings in 5.62s

cd ../frontend
npm test -- --run src/components/RiskQuery.test.jsx
# 1 file, 3 tests passed in 1.47s
```

MCP-related tests live in `backend/tests/test_wave_c_mcp.py` (not `test_mcp.py`); the `-k "mcp or risk_query"` filter selects those plus risk-query orchestration/API tests.

## Service lifecycle and app lifespan wiring

### FastAPI (`backend/app/main.py`)

The `@asynccontextmanager` `lifespan` hook:

1. Calls `require_shared_auth_configured()` (shared deployments fail closed without API tokens).
2. Builds persistence via `build_persistence_wiring()` and stores repos/session factory on `app.state`.
3. Constructs a single `PortfolioService` via `build_portfolio_service()` → `app.state.portfolio_service`.
4. Starts a `RiskRunWorker` (Postgres session factory when persistence is enabled; in-memory market snapshots otherwise), attaches it to `app.state.risk_run_worker`, and wires `service.risk_run_worker` / `service.risk_run_compare`.
5. On shutdown: `worker.shutdown(wait=False)`.

HTTP handlers resolve the service through `app/api/deps.py` (`get_portfolio_service` reads `app.state`). Tests must use `TestClient(app)` so lifespan runs; `app.main.service` is a lazy alias with no module-global fallback.

There is **no AI provider construction** in lifespan yet — the OpenAI seam will be added in T07.

### Shared factory (`backend/app/services/risk_factories.py`)

`build_portfolio_service()` is the canonical constructor for the pricing + historical risk stack. It is called from:

- FastAPI lifespan (`app.main`)
- Out-of-process worker (`python -m app.worker`)

Optional kwargs allow rebinding historical dataset/engine for queued runs.

### Out-of-process worker (`backend/app/worker.py`)

Compose runs `worker` as a separate OS process from `backend` (QuantLib process partition). It reuses `build_persistence_wiring()`, `build_portfolio_service()`, and `RiskRunWorker`, polling Postgres for `QUEUED` rows. Requires `QUANTLINEAGE_DATABASE_URL`. Pair with `QUANTLINEAGE_EXTERNAL_WORKER=1` on the API so HTTP only enqueues.

### Portfolio query path (`backend/app/services/portfolio_service.py`)

- `PortfolioService` owns a `RiskQueryEngine()` instance (`self.query_engine`).
- `query(portfolio, question)` delegates to `self.query_engine.answer(question, portfolio, self)`.
- No model/provider branch in `PortfolioService.query` yet; `answer_with_model` exists on `RiskQueryEngine` for future OpenAI wiring (T08).

## Environment loading behavior (current)

**There is no `python-dotenv` or `.env` auto-load at application startup today.** Configuration is read directly from the process environment via `os.environ` / `os.getenv` at point of use.

Representative env reads:

| Area | Variables / module |
|------|-------------------|
| Database | `QUANTLINEAGE_DATABASE_URL` — `app/persistence/config.py` |
| Pricing engine | `QUANTLINEAGE_PRICING_ENGINE`, cache sizes — `app/pricing/factory.py` |
| Shared auth | `QUANTLINEAGE_SHARED_DEPLOYMENT`, `QUANTLINEAGE_API_TOKEN`, `QUANTLINEAGE_API_TOKENS` — `app/api/auth.py` |
| Worker polling | `QUANTLINEAGE_WORKER_POLL_INTERVAL`, `QUANTLINEAGE_WORKER_POLL_BATCH` — `app/worker.py` |
| MCP stdio | `QUANTLINEAGE_MCP_AUTHORIZATION` — `app/mcp.py` |
| External worker mode | `QUANTLINEAGE_EXTERNAL_WORKER` — risk run API/worker split |

Compose files inject env vars explicitly into `backend` and `worker` services. Local shared profile uses `docker compose --env-file .env.shared -f docker-compose.shared.yml` (see comments in `docker-compose.shared.yml`).

Repo templates today:

- `.env.shared.example` — Postgres password and API tokens (no OpenAI vars yet).
- **No `.env.example` yet** — planned in T02 with `OPENAI_API_KEY` and provider settings.

T02 will add `python-dotenv` with `override=False` so exported env vars are not clobbered (per GOAL.md).

## Inspected modules — brief notes

### `backend/app/risk/query.py`

- **`TOOL_CONTRACTS`**: canonical allowlist of 16 `RiskToolName` entries with service methods, required inputs, numeric sources, and provenance fields.
- **`RiskAssistantModel` protocol** + **`DeterministicRiskAssistantModel`**: offline/test adapter wrapping `RiskQueryEngine.route`.
- **`RiskQueryEngine`**: deterministic keyword/regex router; handles injection, advisory, secret, and ambiguous prompts; validates via `validate_tool_call` before executing through `execute_allowlisted_tool`.
- **`answer_with_model`**: model turn → validate → grounded tool response (or clarification/refusal); secret requests blocked before model call.
- **`validate_tool_call` / `execute_allowlisted_tool`**: shared with MCP and HTTP query paths.

### `backend/app/mcp.py`

- **`ThinMcpServer`**: in-process MCP facade; **no embedded LLM**; not imported by `app.main`.
- **`list_tools()`**: exposes `TOOL_CONTRACTS` JSON schemas only.
- **`call_tool()`**: auth → `validate_tool_call` → `execute_allowlisted_tool` on bound portfolio/service.
- Optional stdio entry: `python -m app.mcp` with JSON-RPC 2.0 (`tools/list`, `tools/call`).

### `backend/app/services/portfolio_service.py`

- Facade over pricing, VaR, stress, limits, attribution, and query engines.
- Risk query numerics always come from deterministic service methods invoked by the query/MCP layers, not from model prose.

## Compose and frontend scripts

### `docker-compose.yml` (local demo)

Services: `postgres`, `backend`, `worker`, `frontend`. Backend/worker share QuantLib image, Postgres URL, `QUANTLINEAGE_EXTERNAL_WORKER=1`. **No OpenAI or AI provider env vars** in Compose yet (T13).

### `docker-compose.shared.yml`

Adds shared-deployment auth tokens, Caddy `proxy`, internal-only backend/frontend exposes. Same worker/API split.

### `frontend/package.json` scripts

| Script | Command |
|--------|---------|
| `dev` | `vite` |
| `build` | `vite build` |
| `test` / `test:vitest` | `vitest run` |
| `test:node` | `vitest run src/lib` |
| `test:watch` | `vitest` |
| `lint` | `eslint src --max-warnings 0` |

Risk Query UI tests: `npm test -- --run src/components/RiskQuery.test.jsx`.

## Gaps for upcoming tasks

- No `backend/app/ai/` package or typed AI config (T01–T02).
- No OpenAI SDK / dotenv in `requirements.txt` (T02).
- Lifespan does not construct an OpenAI client (T07).
- `PortfolioService.query` always uses deterministic `answer`, not `answer_with_model` (T08).
- Compose and `.env.example` lack AI variables (T02, T13).
- MCP test file is `test_wave_c_mcp.py`, not `test_mcp.py` (note for T11).
