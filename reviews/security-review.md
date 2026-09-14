# QuantLineage Security Review

## Executive Summary

Security posture rating: 5/10

Deployment assumption:
Current repository is a **local/demo development application** without authentication, tenancy, or a documented production security boundary. README, `docs/known_limitations.md`, and architecture docs describe a reproducible MVP risk terminal, not a multi-user internet service. Compose nonetheless publishes Postgres (`5432`), FastAPI (`8000`), and a static frontend (`5173`) with hardcoded demo database credentials and no bind-address restriction. Docker Compose `ports:` mappings typically listen on all host interfaces (`0.0.0.0`), so a `docker compose up` on a shared network is a realistic accidental remote exposure. ROADMAP Workstream 7 (“API Productionization”) is marked complete but covers versioning, typed models, and the error envelope — not authentication, authorization, or workload isolation. That documentation gap is a deployment-boundary ambiguity, not a hidden production auth system.

Review scope:
Authorized defensive review of the QuantLineage repository as of 2026-09-03. Inspected application source (`backend/`, `frontend/`, `backend/native/`), tests, Docker/Compose, CI, requirements, persistence/migrations, ADRs, and AI/query orchestration. No application source was modified. No exploits were developed. Safe local checks: repository search, Pydantic/JSON non-finite acceptance via the backend venv, and `npm audit --omit=dev` (0 production vulnerabilities reported). `pip-audit` is not installed in this checkout and was not added.

Finding counts:
- Critical: 0
- High: 5
- Medium: 5
- Low: 0

Top security risks:
1. No authentication or authorization on any HTTP route, including OpenAPI (`/docs`) and async risk-run results.
2. Client-controlled portfolios and methodology flags can trigger unbounded synchronous revaluation, hierarchy VaR-per-node, FULL_REVALUATION historical paths, and queued worker jobs.
3. Persistence-enabled `POST /risk/runs` upserts the request `portfolio.id`, so the seeded demo book (`global-macro`) can be overwritten without any ownership check.
4. Compose publishes Postgres on host port 5432 with the documented demo password, alongside an unauthenticated API on 8000.
5. The out-of-process worker constructs `HistoricalRiskEngine()` with the synthetic RNG default, while the API DI path loads the demo CSV — queued run results can silently disagree with interactive VaR.

## Threat Model

### Assets

- Portfolio / trade payloads submitted in request bodies and, when `QUANTLINEAGE_DATABASE_URL` is set, persisted in `portfolios` / `trades`.
- Market snapshot JSON (`market_snapshots` data blob) and in-code/DI default marks.
- Risk results: VaR/ES, stress, reverse stress, hierarchy, limits, attribution, and named `risk_results` payloads.
- Risk-run lifecycle rows (`QUEUED` / `RUNNING` / `COMPLETED` / `FAILED`) and `error_message`.
- Limit and scenario definition rows seeded from in-code defaults.
- Demo historical factor CSV (`data/demo_historical_factors.csv`) and any path supplied via `QUANTLINEAGE_HISTORICAL_DATASET`.
- Application integrity: pricing adapters, native scenario kernel, worker claim protocol.
- Risk-calculation integrity: methodology, units, historical dataset identity, QuantLib evaluation-date isolation.
- Service availability: CPU/memory of uvicorn, worker processes, native thread pool, and Postgres.
- Secrets: only documented demo DSNs were found; `.env` is gitignored. No production API keys, JWTs, or cloud credentials were identified in the tree.

### Trust Boundaries

- Browser (Vite origin `localhost:5173` or Compose nginx on published 5173) → FastAPI on `:8000`.
- FastAPI → SQLAlchemy/Postgres when `QUANTLINEAGE_DATABASE_URL` is set; otherwise in-memory repos.
- FastAPI → in-process `ThreadPoolExecutor` risk-run worker, or enqueue-only API + `python -m app.worker` process (`QUANTLINEAGE_EXTERNAL_WORKER=1`).
- Python risk engines → `PricingEngine` (QuantLib or builtin). QuantLib `Settings.evaluationDate` is process-global and serialized by an adapter `RLock`.
- Python historical VaR (LINEAR / DELTA_GAMMA only) → optional C++ `ctypes` kernel when `QUANTLINEAGE_SCENARIO_KERNEL=native`.
- Operator environment → process: `QUANTLINEAGE_*` env vars, including database URL, historical CSV path, kernel library path, and worker poll settings.
- Future LLM adapter → deterministic tool executor (`RiskQueryEngine.answer_with_model`). **Not wired to HTTP today.**

No server-side fetch of client-supplied URLs was found (no SSRF surface). No live market-data vendor client exists.

### Entry Points

- HTTP: dual-mounted routers at legacy paths and `/api/v1` (`backend/app/main.py`). Methods: GET health/portfolio/demo catalogs/scenario lists/risk-run status; POST for essentially all risk, stress, market-snapshot, attribution, limits, query, and run-create operations.
- JSON bodies: full `Portfolio` (discriminated positions), `StressScenario` lists, formal `ScenarioWire`, `MarketSnapshot` (attribution), `RiskRunCreateRequest.request` (`dict[str, Any]`), NL `question`.
- Query parameters: `methodology`, `observations` on `/risk/var/compare` (`ge=1, le=5000`).
- FastAPI default docs: `/docs`, `/redoc`, `/openapi.json`.
- Environment variables and Compose files (database URL, demo Postgres password, historical dataset path, kernel selection).
- CLI / worker: `python -m app.worker`, `python -m app.demo.run_demo_risk`, benchmark/native compile scripts (not HTTP).
- CSV historical loader (env or explicit path; not an upload endpoint).
- Native FFI: `quantlineage_portfolio_scenarios` via ctypes from Historical VaR when native kernel is enabled.

### Threat Actors

- Unauthenticated network user, if Compose/uvicorn is reachable beyond loopback (LAN/VPN/mis-bound ports).
- Local process user on the same workstation (always in scope for a demo API with no auth).
- Malicious or malformed portfolio/scenario/market JSON supplier (UI, script, or future integration).
- Accidental internal misuse (wrong units, huge books, FULL_REVALUATION compare).
- Compromised npm/PyPI dependency (frontend `"latest"` ranges increase this residual).
- Prompt-injection source: **not currently an HTTP threat** because no external LLM is configured or mounted; relevant only if `answer_with_model` is later wired to a real provider.

## Production Exposure Blockers

These items should prevent deployment outside a trusted, loopback-only environment:

1. No authentication, session, API key, or network allowlist on FastAPI (`backend/app/main.py`, all `backend/app/api/*.py` routers).
2. No object-level authorization: `GET /risk/runs/{run_id}` returns any run; persistence upserts are keyed by client `portfolio.id`.
3. Compose publishes Postgres `5432:5432` with a well-known demo password and FastAPI `8000:8000` without TLS or host binding to localhost.
4. Unbounded, CPU-heavy risk endpoints are synchronous (or queue without backpressure) and can exhaust the host.
5. No documented production deployment model (bind address, reverse proxy, secret management, tenant isolation, request limits). Workstream 7 “productionization” does not include these controls.

If none of the above is accepted as a blocker for a strictly local demo on loopback, the application is still not safe to expose on a LAN or the public internet.

## Findings

## SEC-001 — No authentication or authorization on the HTTP API

Severity: HIGH
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-306

Location:
- backend/app/main.py:72-93
- backend/app/api/risk.py:31-141
- backend/app/api/stress.py:54-215
- backend/app/api/risk_runs.py:25-74
- backend/app/api/portfolio.py:14-39
- backend/app/api/errors.py:21-28 (401/403 codes exist; no caller issues them)

Attack / failure precondition:
The API process is reachable to anyone other than a fully trusted local user. That includes Compose default published ports, `uvicorn --host 0.0.0.0` in `backend/Dockerfile`, or any host firewall that allows :8000. This is a production exposure blocker for remote/multi-user use. It is **not** scored CRITICAL solely because auth is absent: the product is documented as a local demo.

Evidence:
No `HTTPBearer`, OAuth2, session cookie, API-key dependency, or user model exists under `backend/app/`. Routers depend on `get_portfolio_service` / worker / demo loaders only. FastAPI is constructed as `FastAPI(title="QuantLineage API", ...)` with default `/docs` enabled. CORS is limited to Vite origins (`allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"]`, `allow_credentials=True`) which is appropriate for local UI, not a substitute for authentication. Error mapping includes `unauthorized` / `forbidden` / `rate_limited` codes that are unused by routes.

Impact:
Confidentiality: any caller can read demo portfolios, compute and retrieve risk results, and poll risk-run payloads. Integrity: any caller can enqueue runs and, with persistence, mutate stored portfolios (see SEC-003). Availability: any caller can invoke expensive engines (see SEC-002). In a future multi-user deployment this is a full missing security boundary, including IDOR on `run_id` / `portfolio_id`.

Exploitability:
Send unauthenticated HTTP requests to `/api/v1/*` or legacy dual-mount paths. No token is required. CSRF is not applicable (no cookie session).

Recommendation:
Before any non-loopback deployment, add an authentication boundary (at minimum a deployment-time shared secret or reverse-proxy auth) and deny-by-default authorization on every mutating and result-read route. Disable or protect `/docs` in non-dev. Do not treat Workstream 7 complete as “production-ready API security.”

Verification:
Unauthenticated requests to `/api/v1/risk/var` and `/api/v1/risk/runs/{id}` return 401. Authenticated-but-unauthorized callers cannot read another principal’s runs. OpenAPI is not anonymously readable in the production profile.

Effort:
L

Suggested roadmap area:
M7 API Productionization (authN/Z residual; versioning work is already done)

--------------------------------------------------

## SEC-002 — Client-controlled portfolios can force unbounded expensive risk computation

Severity: HIGH
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-770

Location:
- backend/app/domain/models.py:286-289 (`Portfolio.positions` has no `max_length`)
- backend/app/domain/models.py:781-783 (`CustomStressRequest.scenarios` unbounded)
- backend/app/domain/models.py:864-867 (`ScenarioComparisonRequest` two portfolios + scenario list)
- backend/app/api/risk.py:48-90 (`POST /risk/var`, `/es`, `/var/compare` with `observations` up to 5000)
- backend/app/api/stress.py:93-215 (custom stress, reverse, compare)
- backend/app/risk/historical.py:142-162 (`full_revaluation_pnl_series`: one full portfolio reprice per observation)
- backend/app/risk/es.py:119-156 (FULL_REVALUATION ES: additional isolated reprice per factor family per observation)
- backend/app/risk/hierarchy.py:107-250 (`_node` runs VaR + stress + limits at every firm/portfolio/desk/strategy/book/**trade** node)
- backend/app/services/risk_run_worker.py:203-252 (enqueue with no queue-depth cap)
- backend/app/main.py:72-78 (no request-size, concurrency, or timeout middleware)

Attack / failure precondition:
Unauthenticated (SEC-001) or any local client can POST JSON. No Starlette `max_request_size`, SlowAPI, or worker admission control was found. Reverse-stress search is iteration-capped (`DEFAULT_MAX_ITERATIONS = 40` in `backend/app/risk/reverse_stress.py`), so reverse stress is costly but not unbounded in loop count.

Evidence:
Almost every risk route accepts a full `Portfolio` body and immediately calls `PortfolioService` on the request thread (except `/risk/runs`, which queues). `Portfolio.positions` is an unconstrained list. `POST /risk/var?methodology=FULL_REVALUATION` reprices the book once per historical observation (demo CSV default 750). `POST /risk/es?methodology=FULL_REVALUATION` then reprices again per factor family per observation. `POST /risk/var/compare` runs LINEAR, DELTA_GAMMA, **and** FULL_REVALUATION; `observations` is bounded `le=5000` on that route only — other routes use the process dataset size with no client cap. `POST /risk/hierarchy` builds a full tree and calls `_metrics` + `_stress` + `_limits` **per node**, including one node per trade. `POST /risk/stress/custom` and `/stress/evaluate/custom` accept arbitrary scenario lists, each a full revaluation. `POST /risk/runs` accepts unlimited queued jobs (`max_workers=2` only serializes execution; it does not reject overload). Uvicorn in Docker has no `--limit-concurrency` / `--timeout-keep-alive` hardening.

Impact:
Availability: one request can consume CPU for a long period (QuantLib under the process RLock serializes other pricing). Memory: large position arrays, scenario lists, and hierarchy response trees. Integrity of service: other interactive users (or the demo UI `loadDashboard` fan-out of nine POSTs) stall. This is an availability finding, not RCE.

Exploitability:
POST a large `positions` array and/or `methodology=FULL_REVALUATION` to `/api/v1/risk/var`, `/risk/es`, `/risk/var/compare?observations=5000`, `/risk/hierarchy`, or `/risk/stress/evaluate/custom` with many scenarios. Repeat `POST /api/v1/risk/runs` to fill Postgres/in-memory queues.

Recommendation:
Enforce server-side caps: max positions, max scenarios, max nested market maps, max concurrent risk jobs, request body size, and a cheaper default than per-trade VaR in hierarchy for HTTP. Reject or async-only FULL_REVALUATION above a small book. Add 429 when the worker queue exceeds a limit.

Verification:
Requests exceeding the chosen position/scenario caps return 422/413. A FULL_REVALUATION compare at the observation cap cannot be enlarged via other endpoints. Queue depth tests show 429 after N outstanding runs. Hierarchy HTTP does not perform a full Historical VaR at every trade node unless explicitly requested.

Effort:
M

Suggested roadmap area:
M7 API Productionization / M9 Engineering Quality (workload limits)

--------------------------------------------------

## SEC-003 — Persistence path upserts portfolios by client-supplied id

Severity: HIGH
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-639

Location:
- backend/app/services/risk_run_worker.py:240-243
- backend/app/persistence/sqlalchemy_repos.py:55-80
- backend/app/domain/models.py:286-287, 1357-1389 (`Portfolio.id` and `RiskRunCreateRequest` allow client ids)
- backend/app/sample.py:11-12 (seeded id `global-macro`)
- backend/app/persistence/wiring.py:46

Attack / failure precondition:
`QUANTLINEAGE_DATABASE_URL` is set (Compose backend/worker default). Caller can POST `/api/v1/risk/runs` (no auth; SEC-001).

Evidence:
`RiskRunWorker.submit` saves the request portfolio through `SqlAlchemyPortfolioRepository.save` whenever a session factory is configured. `save` loads by primary key and **replaces name/hierarchy fields and all trades**. The HTTP body supplies `portfolio.id`. Seeded default id is the cross-asset book `global-macro`. There is no owner field, If-Match, or “create vs update” distinction. `GET /portfolio` then returns whatever was last saved under the default id. In-memory mode skips this SQL upsert (only an in-process run cache is used).

Impact:
Integrity: demo or tenant books can be replaced with attacker-chosen positions, after which dashboard loads and subsequent risk runs use the poisoned book. Confidentiality is secondary (attacker already sent the data). In a future multi-user system this is classic IDOR / mass assignment of identity. Availability: replacing a small demo book with a huge book amplifies SEC-002.

Exploitability:
`POST /api/v1/risk/runs` with `"portfolio": {"id": "global-macro", ...}`. No special privileges. Subsequent `GET /api/v1/portfolio` reflects the new trades.

Recommendation:
Treat HTTP-submitted portfolios as run-scoped snapshots, not upserts of the canonical book; or require an explicit admin import API with immutable ids. If upsert remains, authenticate and authorize per id, and never accept client ids that collide with seeded system portfolios without a dedicated replace operation.

Verification:
POST a run whose `portfolio.id` equals the seed id with a distinct trade set; `GET /portfolio` must remain the original seed (or return 409). A second user’s id must be unreachable. Database row `portfolios.id = global-macro` unchanged unless an authorized replace API is used.

Effort:
S

Suggested roadmap area:
M5 Persistence & Risk-Run Platform / M7 API Productionization

--------------------------------------------------

## SEC-004 — Compose publishes Postgres and API with hardcoded demo credentials

Severity: HIGH
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-798

Location:
- docker-compose.yml:2-16, 18-26, 32-40, 45-48
- backend/app/persistence/config.py:17-18
- backend/Dockerfile:9 (`--host 0.0.0.0`)
- README.md:139-145 (documents the same DSN)
- .github/workflows/ci.yml:86-91 (CI service; not a production secret)

Attack / failure precondition:
Someone runs `docker compose up` (documented demo path) on a host whose published ports are reachable. Compose `ports: ["5432:5432"]` / `["8000:8000"]` / `["5173:80"]` do not specify `127.0.0.1:`. Demo user/password are the well-known pair documented in README (not an accidentally leaked production secret). No `REDACTED_SECRET_FOUND`: this is an intentional sample DSN that **does** work.

Evidence:
`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` are set to the demo identity. Backend and worker `QUANTLINEAGE_DATABASE_URL` embeds the same values. Postgres is published to the host. The API image listens on all interfaces. There is no `USER` directive in `backend/Dockerfile` or `frontend/Dockerfile` (containers run as root). No TLS. `.gitignore` excludes `.env`, but Compose does not require an env file to start with these defaults.

Impact:
Confidentiality/integrity of the Postgres volume (`quantlineage_pgdata`): anyone who can reach :5432 can read/alter portfolios, snapshots, and risk results using the documented password. Combined with SEC-001, :8000 is a second unauthenticated entry to the same data. This is a production exposure blocker if Compose is treated as “how we run QuantLineage,” not only a laptop loopback demo.

Exploitability:
Connect to host:5432 with the documented demo DSN, or call the published API. No credential guessing required.

Recommendation:
Bind published ports to `127.0.0.1` by default; do not publish Postgres at all except for explicit local debugging. Require a non-default password via env file that is not committed. Split “demo compose” from any future “deploy compose.” Run the API as a non-root user and terminate TLS at a proxy.

Verification:
Default Compose YAML maps `127.0.0.1:8000:8000` (and does not publish 5432). Starting Compose without a local secret file fails closed. Scanning the host from another LAN machine cannot open 5432/8000.

Effort:
S

Suggested roadmap area:
M9 Engineering Quality / DevOps (deployment hardening)

--------------------------------------------------

## SEC-005 — Compose worker uses a different historical dataset than the API

Severity: HIGH
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-345

Location:
- backend/app/api/deps.py:38-43
- backend/app/worker.py:70
- backend/app/risk/historical.py:181-194 (`dataset or SyntheticHistoricalDataset(...)`)
- backend/app/risk/historical_data.py:215-238 (`create_historical_dataset` default `"demo"`)
- docker-compose.yml:25, 32-40

Attack / failure precondition:
`QUANTLINEAGE_EXTERNAL_WORKER=1` (Compose `backend`) so HTTP only enqueues; `python -m app.worker` executes runs. Operator or UI treats `GET /risk/runs/{id}` COMPLETED payloads as the system of record. No malicious input is required beyond using the documented Compose path.

Evidence:
API process-wide `portfolio_service` injects `HistoricalRiskEngine(dataset=create_historical_dataset())`. `create_historical_dataset()` reads `QUANTLINEAGE_HISTORICAL_DATASET` and **defaults to the packaged demo CSV**. The worker entrypoint builds `PortfolioService(..., HistoricalRiskEngine())` with **no dataset argument**, so the engine falls back to `SyntheticHistoricalDataset(seed=7, observations=750)` — a different source than the file replay, even when observation counts match. Interactive `POST /risk/var` therefore need not equal a `run_type=var` completed payload for the same book. This is silent: both results look like plausible VaR.

Impact:
Integrity of persisted risk results and any downstream limit/attribution decisions based on runs. Confidentiality/availability not directly affected. This is a security-integrity issue because the platform presents both numbers as deterministic engine output.

Exploitability:
Use Compose as documented: compute VaR via the API, enqueue the same portfolio as a var run, compare payloads. No exploit code required.

Recommendation:
Construct the worker `PortfolioService` with the same `create_historical_dataset()` (and pricing factory) as API DI. Persist dataset id / content hash on `RiskRun` and refuse to complete if they diverge. Add a regression test that worker and API engines share dataset identity.

Verification:
With Compose worker, `POST /api/v1/risk/var` and a completed `run_type=var` for the same portfolio match within existing numerical tolerances. `RiskRun.pricing_engine_version` / dataset id fields are populated and asserted in tests.

Effort:
S

Suggested roadmap area:
M5 Persistence & Risk-Run Platform / M10 Demo Data & Reproducibility

--------------------------------------------------

## SEC-006 — Financial scalars accept non-finite JSON and unbounded magnitudes

Severity: MEDIUM
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-20

Location:
- backend/app/domain/models.py:107-114 (`EquityPosition.quantity` / `price`: unconstrained `float`)
- backend/app/domain/models.py:131-139 (`EuropeanOptionPosition.spot` / `strike` unconstrained; `maturity_years` / `volatility` only `gt=0`)
- backend/app/domain/models.py:173-177 (`FXForwardPosition.notional_base` unconstrained)
- backend/app/api/scenario_wire.py:33-38 (`FactorShockWire.amount` unconstrained)
- backend/app/domain/models.py:786-790 (`ReverseStressRequest.max_shock` / `target_loss_pct` only `gt=0`)

Attack / failure precondition:
Client can POST JSON. Python `json.loads` (used by Starlette) accepts the non-standard tokens `NaN`, `Infinity`, and `-Infinity`. Confirmed with the backend venv: unconstrained `float` fields accept `nan`/`inf`; `Field(gt=0)` **rejects NaN** but **accepts +Infinity**.

Evidence:
Pydantic v2 `float` does not imply finite. `Field(gt=0)` is true for `inf`, so `maturity_years: inf` and `volatility: inf` pass. Equity spot/price/quantity and European option spot/strike have no positivity or finiteness checks (unlike several FX/IR fields that use `gt=0`). Hypothesis property tests explicitly disable NaN/Inf (`backend/tests/test_quant_properties.py`) but **API tests do not reject** those payloads. Native kernel tests document that NaN **propagates** (`test_native_nan_propagates_like_python`). Extreme notionals and `inf` maturities can produce non-finite or pathological QuantLib/builtin values that still serialize as JSON numbers or fail into SEC-008 error strings.

Impact:
Integrity: risk metrics can become NaN/Inf or silently absurd while still looking like a completed report. Availability: `inf` tenors / huge notionals can make pricing extremely slow or crash native/NumPy paths. Not a demonstrated RCE.

Exploitability:
POST `{"quantity": NaN, "price": Infinity}` on an equity position, or `maturity_years` / `max_shock` of `Infinity`, to `/api/v1/risk/var` or reverse-stress routes.

Recommendation:
Use a finite constrained float (e.g. `Annotated[float, AfterValidator(math.isfinite)]`) plus documented magnitude caps per instrument. Reject NaN/Inf at the API boundary with 422. Add negative tests for non-standard JSON numbers.

Verification:
`NaN` / `Infinity` bodies return 422 on all portfolio-bearing routes. Property tests and API tests share the same finite bounds. Sample demo payloads still pass.

Effort:
S

Suggested roadmap area:
M7 API Productionization / M1 Quant Foundation (input contracts)

--------------------------------------------------

## SEC-007 — Dual rate-shock units and a magnitude heuristic can silently mis-scale scenarios

Severity: MEDIUM
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-682

Location:
- backend/app/domain/models.py:691-705 (`StressScenario.rates_shift_bps`)
- backend/app/api/scenario_wire.py:28-38 (`FactorShockWire.amount`: RateZero “0.0001 = +1bp”)
- backend/app/risk/scenario_model.py:69-75, 273-275 (formal amount is decimal; legacy dict stores bp)
- backend/app/risk/reverse_stress.py:37-66 (`RATES_BP_SCALE = 1000.0`; `from_wire_bound` treats `max_shock > 1` as bp)
- frontend/src/lib/risk.mjs:322-323 (UI converts percent → relative and leaves rates as bp — correct for **legacy** custom stress only)

Attack / failure precondition:
Caller uses the formal scenario wire, reverse-stress `max_shock`, or mixes bp vs decimal without reading comments. No authentication required.

Evidence:
Three different rate conventions exist on external surfaces:

1. Legacy HTTP `StressScenario.rates_shift_bps`: 100 means +100bp.
2. Formal `FactorShockWire.amount` for `factor_type=rate`: 0.0001 means +1bp (absolute decimal).
3. Reverse-stress `max_shock` default `0.80` is a **relative-style** bound that the engine maps to 800bp via `RATES_BP_SCALE = 1000` (not 10000). Values `> 1` are reinterpreted as already-in-bp (`100` → 100bp). There is no unit field on the request; `max_shock=1.0` vs `1.01` changes interpretation.

The UI Scenario Builder correctly divides equity/vol/FX percents by 100 and sends `rates_shift_bps` unchanged to `/stress/evaluate/custom`. The same operator posting `amount: 100` on `/stress/formal/custom` intending “+100bp” applies a 100.0 decimal rate shock. Results remain numerically finite and look like a real stress P&L.

Impact:
Integrity of stress, reverse-stress, and any limits/threat labels derived from them. This is an input-contract / unit-confusion issue with a security-integrity angle because untrusted JSON chooses the scale. It is not a QuantLib formula bug.

Exploitability:
POST formal shocks with `amount` in bp, or reverse-stress `factor=rates` with `max_shock` on the wrong side of the `> 1` heuristic.

Recommendation:
Put an explicit unit enum on every shock (`bp` | `decimal` | `relative`) and fail closed on missing units. Remove the `max_shock > 1` heuristic. Align `RATES_BP_SCALE` with the documented 1bp = 1e-4 decimal convention or stop accepting a single `max_shock` for mixed families.

Verification:
Golden tests: formal `amount: 0.01` and legacy `rates_shift_bps: 100` produce the same curve shock. Reverse-stress `max_shock` for rates rejects ambiguous values or requires `shock_unit`. A payload with `amount: 100` on a rate factor returns 422 unless unit=bp is set and documented.

Effort:
M

Suggested roadmap area:
M3 Stress & Scenario / M7 API Productionization (wire contracts)

--------------------------------------------------

## SEC-008 — Failed risk runs return raw exception strings to clients

Severity: MEDIUM
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-209

Location:
- backend/app/services/risk_run_worker.py:331-336
- backend/app/api/risk_runs.py:64-69
- backend/app/api/errors.py:114-167 (sync unhandled errors are opaque; this path is not)

Attack / failure precondition:
A run fails during `execute_run_type` (bad marks, QuantLib error, DB issue, oversized book). Caller can `GET /api/v1/risk/runs/{run_id}` (UUID from the 202 response, or guess; no auth).

Evidence:
The worker catches `Exception`, sets `err_msg = str(exc) or type(exc).__name__`, and `svc.fail(run_id, msg)`. `RiskRunView` exposes `error_message`. By contrast, `register_exception_handlers` returns a fixed `"An unexpected error occurred"` for unhandled **HTTP** exceptions and tests assert opacity (`backend/tests/test_api_error_model.py`). Sync `ValueError` on create still returns `detail=str(exc)` as the 400 message (run_type validation), which is less sensitive but inconsistent.

Impact:
Confidentiality / hardening: filesystem paths, SQL fragments, QuantLib internals, or instrument identifiers can appear in API JSON and logs (`logger.exception` already records the traceback server-side). Not a direct data-dump of other tenants beyond what the exception string contains.

Exploitability:
Submit a run that triggers a pricing/persistence exception and read `error_message` on GET.

Recommendation:
Store a stable error code internally; return a sanitized message to clients. Log the full exception server-side only. Keep the M7.5 opaque 500 behavior for this path too.

Verification:
Forced worker failures return `code`/`message` without paths, SQL, or exception class internals. Tests parallel `test_m75_unhandled_500_shape` for `GET /risk/runs/{id}` FAILED bodies.

Effort:
XS

Suggested roadmap area:
M7 API Productionization (error model completeness)

--------------------------------------------------

## SEC-009 — Frontend runtime dependencies are declared as “latest”; image build uses npm install

Severity: MEDIUM
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-1104

Location:
- frontend/package.json:15-19
- frontend/Dockerfile:3-5
- backend/requirements.txt:1-11 (major-capped ranges, not fully pinned)
- backend/Dockerfile:3-4

Attack / failure precondition:
A future `npm install` (local or Docker frontend build) resolves `react` / `react-dom` / `vite` / `@vitejs/plugin-react` to a new major that is not what `package-lock.json` currently records. CI frontend job uses `npm ci` (good); **the frontend Docker image does not**.

Evidence:
`package.json` sets those four runtime packages to `"latest"`. Lockfile currently pins react 19.2.8 and vite 8.2.2, and `npm audit --omit=dev` reported 0 vulnerabilities at review time. `frontend/Dockerfile` runs `npm install` after copying `package*.json`, which can update the lockfile resolution versus `npm ci`. Backend pins with `>=x,<next-major` and CI/Docker `pip install -r requirements.txt` without hashes. No packages are installed from git URLs. No `curl | bash` installers in app Dockerfiles.

Impact:
Supply-chain / reproducibility: a rebuild can pull a compromised or breaking “latest” frontend toolchain into the nginx image. Residual, not a currently verified CVE in the locked tree.

Exploitability:
Requires a malicious or broken publish on npm (or a developer running `npm install` without noticing lockfile drift), then a rebuild/deploy of the frontend image.

Recommendation:
Pin exact frontend versions in `package.json`; use `npm ci` in Docker; consider pip hashes or a lockfile for Python. Keep CI on `npm ci`.

Verification:
`npm ci` is the only install path in Docker and CI. `package.json` has no `"latest"`. Rebuilding twice yields the same `npm ls` top-level versions.

Effort:
S

Suggested roadmap area:
M9 Engineering Quality

--------------------------------------------------

## SEC-010 — Runtime images run as root, bind all interfaces, and lack resource limits

Severity: MEDIUM
Confidence: HIGH
Category: Security
Status: OPEN

CWE:
CWE-250

Location:
- backend/Dockerfile:1-9
- frontend/Dockerfile:1-8
- docker-compose.yml:1-51 (no `mem_limit`, `pids_limit`, `read_only`, `cap_drop`, `user:`)

Attack / failure precondition:
Compose or the backend image is used as a long-lived service (even locally). Combined with SEC-001/002, a crash or fork bomb in the container is a host-capacity incident.

Evidence:
Backend image is `python:3.13-slim` (repo documents Python 3.12+) with `CMD uvicorn ... --host 0.0.0.0 --port 8000`. No `USER`. Frontend multi-stage build ends as `nginx:alpine` copying `dist` only — good reduction of Node toolchain in the final image — but still default root nginx and no custom `nginx.conf` (no security headers, no API reverse-proxy). Compose does not drop capabilities or set ulimits. Worker command is the same image. This is hardening, not a standalone RCE.

Impact:
Availability and blast radius after another finding is exploited: root in-container, no cgroup caps in Compose, API reachable on all interfaces. Frontend container cannot reach backend by Compose DNS unless the browser uses host `localhost:8000` (baked `VITE_API_BASE_URL` default in `frontend/src/api.js`) — a deployment footgun, not XSS.

Exploitability:
Requires deploying these files as-is. No extra exploit step.

Recommendation:
Non-root `USER`, bind to loopback behind a proxy, Compose `127.0.0.1` port maps, memory/PID limits, read-only rootfs where possible, security headers on nginx. Keep compilers out of the API image (already true).

Verification:
`docker inspect` shows non-root user; ports bound to 127.0.0.1; cgroup memory limit present; nginx returns CSP/nosniff on `/`.

Effort:
M

Suggested roadmap area:
M9 Engineering Quality / DevOps

## Native / FFI Assessment

The C++ kernel (`backend/native/include/risk_kernel.hpp`, `risk_kernel_capi.cpp`) is a flat double-buffer Δ-Γ aggregator. The C ABI does **not** check null pointers or that `n_exposures`/`n_shocks` match caller buffer bytes; out-of-bounds reads/writes would follow from a mismatched C call.

The Python wrapper (`backend/app/compute/kernel.py:107-116`) builds `eflat`/`sflat`/`O` from the same Python lists it passes as counts, so the in-tree ctypes path is internally consistent. Historical VaR maps the **portfolio-aggregate** Greeks to a **single** `Exposure` and one `Shock` per observation (`backend/app/risk/historical.py:29-64`) — HTTP clients never pass raw native arrays. Default `QUANTLINEAGE_SCENARIO_KERNEL` is `python`; Compose does not enable native. `QUANTLINEAGE_KERNEL_THREADS` is parsed with an upper bound of 4096. `FULL_REVALUATION` never calls the kernel.

No HTTP-reachable memory-corruption finding is asserted. Residual risk is: operator-enabled native mode plus a future wrapper that passes client lengths unchecked; huge observation counts then become large `ctypes` allocations (availability), not currently a demonstrated write-primitive. Native tests cover NaN propagation and ABI parity, not adversarial size mismatch from FastAPI.

## API Security Assessment

- AuthN/Z: absent (SEC-001). IDOR on `run_id` is inherent until principals exist; UUIDs reduce casual guessing but not insider/LAN access.
- Validation: strong structural typing (discriminated `Position`, unique position ids, several `gt=0` fields, `extra=forbid` on risk-run models). Weak on cardinality, finiteness, and units (SEC-002, SEC-006, SEC-007).
- CORS: explicit localhost Vite origins + `allow_credentials=True`. Not `*`. Frontend `fetch` does not set `credentials: 'include'`. Acceptable for the demo; would need revisit for cookie auth.
- CSRF: not applicable without cookie/session auth.
- Debug: no extra debug routes; FastAPI `/docs` is on by default.
- Errors: sync unhandled exceptions are opaque (good). Validation errors return Pydantic `details` (expected). Risk-run failures leak `str(exc)` (SEC-008).
- Rate/resource limits: none (SEC-002). `var/compare` `observations` cap is the only notable numeric HTTP bound.
- Mass assignment: clients set `Portfolio.id`, run `request` dict, optional `limits` on drilldown (evaluation input, not persisted limits). Persisted upsert is SEC-003.
- SSRF: none found.
- Dual-mount: legacy + `/api/v1` share handlers; deprecation headers on legacy only. Doubles the unauthenticated surface until sunset.

## Dependency / Supply Chain Assessment

- Python: PyPI ranges with upper major bounds (`fastapi>=0.128,<1`, `QuantLib>=1.43,<2`, etc.). No git installs. `pip-audit` was not present; not installed for this review. Residual: unpinned minors.
- npm: lockfile present; CI uses `npm ci`. Runtime `"latest"` + Docker `npm install` is SEC-009. `npm audit --omit=dev` at review time: 0 production vulnerabilities.
- Native: compiled from in-repo C++ with documented `g++` flags; no third-party native package download in the API image.
- Docker bases: `python:3.13-slim`, `postgres:16-alpine`, `node:22-alpine` (build), `nginx:alpine`. Floating tags, not digests — hardening note.
- No `curl | bash` application installers.

## AI Security Assessment

HTTP `POST /api/v1/risk/query` calls `PortfolioService.query` → `RiskQueryEngine.answer` (keyword router) only (`backend/app/api/risk.py:128-133`, `backend/app/services/portfolio_service.py:274`). Numbers in the answer string are formatted from deterministic tool payloads (`_format_answer`).

`answer_with_model` implements a one-turn tool loop: enum-constrained `RiskToolName`, allowlisted `_execute_tool`, and **ignores** `proposed_answer` when building the user-visible answer (`backend/app/risk/query.py:201-249`, tests in `backend/tests/test_ai_query_orchestration.py`). No live LLM provider, API key, or network client exists. ADR 006 is reflected in code.

No concrete prompt-injection or tool-exfiltration vulnerability is exploitable on the current HTTP surface. Future wiring of `answer_with_model` to an external model must not place raw portfolios/secrets in prompts without a data-handling policy, must keep the tool allowlist, and must continue to ignore model-invented numbers (hardening, not a current finding).

## Security Test Gaps

Highest-value missing **security** tests (not ordinary unit coverage):

- Unauthenticated access is currently the happy path; no test will fail if auth is added incorrectly later — add a “production profile” test once auth exists.
- Non-finite JSON (`NaN` / `Infinity`) on `POST /risk/var` and option spots/strikes.
- Oversized `positions` / `scenarios` / hierarchy books expected to 413/422.
- Persistence: POST run with `portfolio.id == global-macro` must not clobber seed (SEC-003).
- Worker vs API dataset identity (SEC-005).
- FAILED risk-run body must not contain exception strings (SEC-008).
- Formal vs legacy rate-shock goldens (SEC-007).
- Native: wrapper rejects length mismatch if the C ABI is ever exposed more directly.
- No authorization/IDOR tests (blocked on missing auth).

Ordinary missing tests (e.g. more instrument goldens) are out of scope as security findings.

## Informational / Hardening Notes

- Consider security headers (CSP, `X-Content-Type-Options`, HSTS behind TLS) on the nginx frontend image; none are configured.
- Disable or gate `/docs`, `/redoc`, `/openapi.json` outside local dev.
- Pin Compose/API listen address to loopback even for demos; document “not for LAN.”
- `QUANTLINEAGE_HISTORICAL_DATASET` may be a filesystem path (operator-controlled, not an HTTP upload). Do not later accept client paths without a jail.
- `QUANTLINEAGE_DB_ECHO` can log SQL; avoid in shared deployments.
- Worker `logger.exception` and API unhandled handler log exceptions; keep portfolio-sized payloads out of log formatters.
- `frontend/src/api.js` defaults `VITE_API_BASE_URL` to `http://localhost:8000`; Compose frontend does not proxy `/api`. Fine for local browser-to-host API; wrong for a remote UI origin.
- React UI uses text interpolation (including query answers and scenario names); no `dangerouslySetInnerHTML` in `frontend/src`. `frontend/runtime-dist/index.html` uses `innerHTML` but is not the Vite app Docker artifact.
- Dual-mount until 2027-03-02 (`legacy_deprecation.py`) extends the unauthenticated surface.
- Python 3.13 Docker vs documented 3.12+ — image drift, not a vuln by itself.
- Reverse-stress iteration cap (40) and coordinate-descent cap are good availability controls; keep them if HTTP remains synchronous.
- QuantLib `RLock` around `_session` (ADR 007) prevents cross-request evaluation-date contamination inside one process; concurrent FULL_REVALUATION will serialize (availability, by design).

## Positive Security Decisions

- Opaque HTTP 500 envelope (`backend/app/api/errors.py:114-167`) with a dedicated test that strings must not leak.
- Typed FastAPI bodies with discriminated unions and unique position-id validation.
- Risk-run create models use `extra=forbid`.
- CORS allowlist is localhost Vite, not `*`.
- SQLAlchemy `select`/`session.get` parameterization; claim path uses bound `limit` and `FOR UPDATE SKIP LOCKED` on Postgres — no string-built SQL with user input found.
- No `pickle`, `yaml.load`, `eval`, `exec`, or `shell=True` on application request paths. `subprocess` is confined to tests/benchmarks with fixed compiler argument lists.
- No user-controlled server-side URL fetch; no live market vendor.
- `.gitignore` includes `.env`; no committed `.env` or cloud keys found.
- MarketSnapshot is frozen (including nested maps) to reduce accidental shared-state mutation.
- QuantLib evaluation date is locked per pricing call; native kernel does not touch QuantLib globals.
- Native kernel is opt-in; Python constructs matching buffers; FULL_REVAL stays in Python.
- AI HTTP path is deterministic; tool names are an Enum; model-proposed numeric text is not used when the unused `answer_with_model` path runs in tests.
- Persistence stores JSON domain dumps, not QuantLib handles (ADR 005).
- Demo historical data is a packaged CSV, not an upload endpoint.

## Final Assessment

1. Is QuantLineage reasonably safe for local development?
   Yes, on a trusted workstation with the API bound to loopback and Postgres not published to the LAN. The codebase shows several mature defensive choices (typed models, opaque 500s, no unsafe deserialization, QuantLib locking). Treat Compose’s default published ports as **not** “local-only” unless rebound.

2. What prevents public/multi-user deployment?
   SEC-001 through SEC-004: no auth, unbounded compute, persistence upsert-by-id, and demo credentials on published ports. Missing tenant model, TLS, request limits, and a real secret story. Workstream 7 completion does not close this.

3. Which findings can affect risk-result integrity?
   SEC-003 (poisoned stored book), SEC-005 (worker vs API historical dataset), SEC-006 (NaN/Inf/extreme marks), SEC-007 (rate unit / `max_shock` heuristic). Ordinary quant limitations (approximate VaR, reverse-stress not global) are documented methodology, not extra security findings.

4. Which findings can crash or exhaust the service?
   SEC-002 (primary), amplified by SEC-001 and SEC-010. Native kernel crashes are not shown as HTTP-reachable if the Python wrapper remains the only caller. QuantLib errors may fail runs (SEC-008) rather than process-abort; extreme inputs (SEC-006) may still abort native/NumPy in edge cases.

5. What are the first 3 security items that should be fixed?
   1. Bind Compose/API to loopback, unpublish Postgres, rotate away from the committed demo password pattern (SEC-004) — smallest change, blocks accidental LAN exposure.
   2. Stop upserting HTTP portfolios onto canonical ids; align worker `HistoricalRiskEngine` with `create_historical_dataset()` (SEC-003, SEC-005).
   3. Add workload caps (positions/scenarios/concurrency) and finite float validation on the HTTP boundary (SEC-002, SEC-006). Authentication (SEC-001) is the first **product** blocker for any shared deployment and should be scheduled immediately after these demo-integrity/availability fixes if the API will leave localhost.
