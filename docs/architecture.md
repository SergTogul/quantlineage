# QuantLineage Architecture

QuantLineage is organized around one product boundary:

> Pricing adapters produce instrument values. QuantLineage owns portfolio risk, scenario state, aggregation, persistence, API workflow, UI presentation, and deterministic AI orchestration.

## System Shape

```text
Domain models
  Portfolio / Position / Trade / MarketSnapshot / StressScenario / RiskRun
        |
        v
PricingEngine interface <-------------------------------+
  QuantLibPricingEngine                                  |
  BuiltinPricingEngine                                   |
        |                                                |
        v                                                |
PortfolioService -----------------------------------+    |
        |                                           |    |
        v                                           |    |
Risk engines                                       API routers
  sensitivities                                     /api/v1/*
  VaR / ES / contributors                               |
  stress / reverse stress                               v
  scenario attribution                              React risk terminal
  hierarchy / limits / attribution
        |
        v
Optional native scenario kernel
  LINEAR / DELTA_GAMMA aggregation only
```

Persistence is a separate boundary under `backend/app/persistence/`. When `QUANTLINEAGE_DATABASE_URL` is configured, FastAPI wires SQLAlchemy repositories and a Postgres-backed risk-run worker. Without it, the app uses in-memory/sample defaults for local development and unit tests.

## Dependency Direction

Allowed dependency direction:

- `backend/app/domain/` defines portable models and must not import FastAPI, React, QuantLib runtime objects, or SQLAlchemy sessions.
- `backend/app/interfaces/` defines seams such as `PricingEngine`.
- `backend/app/pricing/` implements pricing adapters behind those seams.
- `backend/app/market/` creates and transforms immutable market snapshots.
- `backend/app/risk/` consumes domain models, market snapshots, and pricing interfaces to calculate portfolio risk.
- `backend/app/services/` orchestrates risk workflows and persistence-backed run execution.
- `backend/app/api/` exposes versioned FastAPI routes and DTO wiring; it does not implement quant formulas.
- `frontend/` displays API results and must not duplicate pricing or risk calculations.
- `backend/native/` contains pure numerical kernels and must not depend on QuantLib.

## Core Boundaries

### Pricing

`PricingEngine` is the only valuation contract used by risk code. `QuantLibPricingEngine` is the intended production pricing adapter; `BuiltinPricingEngine` is a deterministic reference and fallback. Risk engines request values through the interface, so QuantLib can be extended without rewriting portfolio risk workflows.

### Market State

`MarketSnapshot` is immutable and copy-on-write. Shocks, scenario application, and bump-and-revalue paths create new snapshots through `bump`, `apply`, or `shock_snapshot`. Nested curve and volatility-surface payloads are recursively frozen to prevent accidental mutation of shared market state.

### Risk

Portfolio risk engines calculate sensitivities, VaR/ES, stress, reverse stress, limits, hierarchy, and attribution from domain models and market snapshots. They do not own instrument pricing formulas. FULL_REVALUATION risk paths reprice shocked snapshots through `PricingEngine`; approximate modes may use deterministic Greek aggregation.

### API

The canonical public prefix is `/api/v1`. Legacy unversioned routes remain dual-mounted with deprecation headers until the published sunset. API routes bind request/response models, dependencies, and error handling; methodology and pricing stay below the service/risk layers.

### Persistence And Workers

SQLAlchemy repositories persist JSON-serializable domain payloads only. QuantLib handles, pricing processes, and in-memory engine objects are never stored. Risk runs use a domain lifecycle (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`); the Compose worker claims queued rows from Postgres with `SKIP LOCKED` when configured.

### UI

The React terminal is presentation and workflow. It calls `/api/v1` endpoints, displays returned results, and handles loading/error/user interaction states. It must not reimplement VaR, pricing, stress, or optimization formulas.

### AI Orchestration

Natural-language risk query code is deterministic today. It selects tool contracts backed by `PortfolioService`, executes those tools, and formats grounded results. A future external LLM loop must preserve the same rule: tool selection and narration only, no model-computed risk numbers.

## Ownership Map

| Area | Owner | Typical paths |
|---|---|---|
| Architecture, contracts, ADRs | Lead Architect | `docs/`, `backend/app/domain/`, `backend/app/interfaces/` |
| Quant pricing | Quant Pricing Engineer | `backend/app/pricing/` |
| Market data and curves | Market Data & Curves Engineer | `backend/app/market/`, `backend/app/risk/factor_types.py` |
| Portfolio risk | Portfolio Risk Engineer | `backend/app/risk/var.py`, `historical.py`, `hierarchy.py`, `attribution.py`, `limits.py` |
| Stress and scenarios | Stress & Scenario Engineer | `backend/app/risk/stress.py`, `scenario_model.py`, `reverse_stress*.py` |
| Native performance | C++ Performance Engineer | `backend/native/`, `backend/app/compute/` |
| Backend/API | Backend/API Engineer | `backend/app/api/`, `backend/app/services/`, `backend/app/persistence/` |
| Frontend | Frontend/Risk UX Engineer | `frontend/` |
| AI orchestration | AI Orchestration Engineer | `backend/app/risk/query.py` |
| QA and validation | QA & Quant Validation Engineer | `backend/tests/`, `frontend/**/*.test.*`, `e2e/` |
| DevOps/platform | DevOps/Platform Engineer | `.github/`, `docker-compose.yml`, build/test tooling |

## Architectural Decisions

The decision record index lives at [`docs/adr/README.md`](adr/README.md). The current ADR set records decisions already evidenced in code/docs; it does not speculate about future choices.
