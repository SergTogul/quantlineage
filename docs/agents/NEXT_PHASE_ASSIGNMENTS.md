# Recommended Next Workstream Assignments

## Workstream: Make the current prototype production-grade enough for serious portfolio demos

### Task 1 — Reproducible local/CI environment
**Owner:** DevOps / Platform Engineer

- Install QuantLib reproducibly.
- Make backend QuantLib tests run without skip.
- Make `npm install`, `npm test`, and `npm run build` pass.
- Add one-command dev startup.
- Add CI matrix.

### Task 2 — Typed risk-factor model
**Owner:** Market Data & Curves Engineer

- Implement typed equity/rate/vol/FX risk factors.
- Update immutable snapshot shock/diff APIs.
- Add serialization and property tests.

**Blocks:** tasks 4 and 5.

### Task 3 — Complete QuantLib pricing coverage
**Owner:** Quant Pricing Engineer

- Replace reference pricing for equity futures, FX forwards, FX options.
- Add golden and finite-difference sensitivity tests.

### Task 4 — Curves and surfaces
**Owner:** Market Data & Curves Engineer

- USD discount/projection curves.
- Key tenors.
- Equity/FX volatility surfaces.
- Tests for interpolation/bumping.

### Task 5 — Full-revaluation VaR and bucketed risk
**Owner:** Portfolio Risk Engineer

- LINEAR / DELTA_GAMMA / FULL_REVALUATION modes.
- Key-rate DV01.
- Vol-bucket and FX risk.
- Component/marginal/incremental VaR and ES contribution.

### Task 6 — Stress v3
**Owner:** Stress & Scenario Engineer

- Typed factor shocks.
- Historical crisis presets.
- Reverse stress against explicit loss/limit thresholds.
- Contribution by hierarchy/factor.

### Task 7 — API contracts
**Owner:** Backend/API Engineer

- Versioned `/api/v1` routers.
- `/risk/what-if`.
- consistent errors.
- OpenAPI examples.
- stable DTOs for factors/scenarios/attribution.

### Task 8 — Independent quant validation
**Owner:** QA & Quant Validation Engineer

- Golden QuantLib cases.
- Hypothesis properties.
- reconciliation tests.
- full-revaluation vs approximation comparisons.
- API critical-path tests.

### Task 9 — Risk terminal integration
**Owner:** Frontend/Risk UX Engineer

- Factor heatmaps.
- scenario builder.
- risk drill-down.
- before/after hedge.
- P&L explain.
- production build + tests.

### Task 10 — Native performance pass
**Owner:** C++ Performance Engineer

Only after Task 5 has a stable reference implementation:
- profile;
- optimize scenario aggregation / VaR-tail hot paths;
- equivalence tests;
- reproducible benchmarks.

### Task 11 — AI orchestration
**Owner:** AI Orchestration Engineer

Only after Tasks 7 and 9 stabilize:
- deterministic tool schemas;
- tool selection/router;
- grounded explanations;
- eval suite.

### Task 12 — Workstream integration
**Owner:** Lead Architect / Orchestrator

- review handoffs;
- resolve interface conflicts;
- update ADRs;
- run full verification;
- close workstream only if Definition of Done passes.

