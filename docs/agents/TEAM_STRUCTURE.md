# RiskForge Subagent Team Structure

## Recommended team

RiskForge benefits from specialist subagents because pricing, market data, portfolio risk, scenario analytics, native performance, API work, UI, AI orchestration, and numerical validation have different failure modes. The goal is not maximum agent count; it is clear ownership and controlled handoffs.

### 1. Lead Architect / Orchestrator
Coordinates the team, decomposes milestones, protects module boundaries, approves interface changes, integrates cross-cutting work, and maintains ADRs.

### 2. Quant Pricing Engineer
Owns instrument models, QuantLib adapters, pricing conventions, valuation, and instrument-level Greeks.

### 3. Market Data & Curves Engineer
Owns immutable market snapshots, yield curves, projection curves, FX spots, dividend curves, volatility surfaces, risk-factor identifiers, and scenario shock application to market data.

### 4. Portfolio Risk Engineer
Owns portfolio aggregation, historical/parametric VaR, Expected Shortfall, component/marginal/incremental risk, factor aggregation, and risk change attribution.

### 5. Stress & Scenario Engineer
Owns hypothetical/historical scenario libraries, custom scenario builder semantics, reverse stress, threat classification, hedge comparison, scenario contribution, and stress governance.

### 6. C++ Performance Engineer
Owns performance profiling, native scenario kernels, C API/ctypes boundary, concurrency, deterministic equivalence tests, and reproducible benchmarks.

### 7. Backend/API Engineer
Owns FastAPI routers, application services, DTOs, validation, persistence integration, risk-run lifecycle, consistent errors, and OpenAPI examples.

### 8. Frontend/Risk UX Engineer
Owns the React/Vite terminal, risk dashboards, scenario builder, hierarchy/drill-down, heatmaps, hedge comparison, loading/error states, and frontend tests.

### 9. AI Orchestration Engineer
Owns deterministic tool schemas, natural-language routing, tool selection, guardrails, and evaluation suites. The agent never implements numerical risk calculations in prompts or model output.

### 10. QA & Quant Validation Engineer
Owns cross-module validation, golden/reference tests, property-based tests, invariants, regression suites, integration/E2E tests, and numerical tolerance policy.

### 11. DevOps / Platform Engineer
Owns environment reproducibility, Docker, CI, dependency/build checks, lint/type checks, native compiler setup, and test matrix automation.

## Dependency map

```text
                         Lead Architect
                              |
          +-------------------+-------------------+
          |                   |                   |
      Market Data        Quant Pricing       Portfolio Risk
          |                   |                   |
          +---------+---------+---------+---------+
                    |                   |
              Stress/Scenario       Backend/API
                    |                   |
                    +---------+---------+
                              |
                         Frontend/Risk UX
                              |
                       AI Orchestration

C++ Performance works underneath Risk/Scenario compute only.
QA & Quant Validation reviews every quantitative boundary.
DevOps/Platform supports all lanes but owns no business logic.
```

## Parallel work that is safe

- Market-data improvements and frontend shell work can proceed independently if API contracts are frozen.
- QuantLib instrument adapters and C++ pure numerical kernels can proceed independently.
- QA can build invariant/property tests while feature agents implement.
- DevOps can build CI and reproducible environments in parallel with feature work.

## Work that should be serialized

- Define `RiskFactor` model before bucketed risk and factor-level scenarios.
- Define curve/surface representation before key-rate DV01 and vol-bucket risk.
- Define scenario schema before API/UI scenario-builder changes.
- Complete deterministic risk APIs before AI orchestration.
- Complete reference computation before native optimization.

