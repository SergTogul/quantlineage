# Milestone R0 — Core Remediation & Trustworthiness

Status: **IN PROGRESS**

Current phase: **A — Safety nets (R0.1)**  
Branch: `r0-core-remediation`  
Date: 2026-09-03

This milestone is inserted **before any net-new RiskForge feature development**.

Its purpose is not to redesign the entire repository. It is to remove the correctness, architecture, reproducibility, and execution-model risks identified by the independent architecture, performance, security, and QA reviews.

Source of truth:

- `FINDINGS.md`
- original reports under `reviews/`

## Gate Rule

Do not resume normal feature roadmap work until:

1. every P0 root finding in `FINDINGS.md` is CLOSED;
2. every P1 root finding is CLOSED or explicitly accepted with written technical rationale;
3. the full verification matrix at the end of this milestone passes.

P2 findings can remain in the backlog if they do not undermine the repaired path.

---

# R0 Baseline Verification (2026-09-03, local macOS)

Recorded on branch `r0-core-remediation`. Existing tests were not weakened.

The builtin suite below is the **pre-insertion** baseline (659). The QuantLib suite was re-run **after** R0.1 test files landed (688, includes new goldens).

Host: Darwin 22.6.0 · Python 3.12 (`backend/.venv`) · QuantLib **1.43** · numpy 2.5.2 · pytest 9.1.1 · Node v22.14.0 · g++/Apple clang present.

| Check | Result | Notes |
|---|---|---|
| Backend pytest `RISKFORGE_PRICING_ENGINE=builtin` | **659 passed**, 1 Starlette/httpx deprecation warning, 48.00s | Before new R0.1 test files |
| Backend pytest `RISKFORGE_PRICING_ENGINE=quantlib` `RISKFORGE_REQUIRE_QUANTLIB=1` | **688 passed**, **0 skipped**, 63.79s | After R0.1.1–R0.1.6 test/CI helper insertion |
| Ruff `ruff check app tests` | exit 0 | staged rule set |
| mypy `mypy app` | exit 0 | staged `disable_error_code` list |
| Frontend `npm test` | **74 passed** (8 files) | vitest |
| Frontend `npm run lint` | exit 0 | `--max-warnings 0` |
| Frontend `npm run build` | OK (vite; 27 modules) | |
| Native `g++` `native/tests/kernel_test.cpp` | **risk_kernel_ok** | `-std=c++20 -O2 -pthread -I native/include` |
| Native pytest `tests/test_native_kernel.py` | **8 passed**, 38.33s | compile + parity |
| PostgreSQL smoke | **BLOCKED (environment)** | Docker daemon not available on this host |
| Playwright E2E | **12 passed**, 1.1m | local Chrome channel; builtin pricing |

```bash
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest -q --tb=line
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib RISKFORGE_REQUIRE_QUANTLIB=1 .venv/bin/python -m pytest -q --tb=line
cd backend && .venv/bin/ruff check app tests && .venv/bin/mypy app
cd frontend && npm test && npm run lint && npm run build
cd backend && g++ -std=c++20 -O2 -pthread -I native/include native/tests/kernel_test.cpp -o /tmp/kernel_test && /tmp/kernel_test
```

Environment blockers (not treated as code failures):

- Docker is not running, so Compose/Postgres smoke and worker lifecycle were not executed here.
- Playwright uses the local Google Chrome channel when `CI` is unset.

## R0.1 task status (Phase A)

| Task | Status | Evidence |
|---|---|---|
| R0.1.1 Exact VaR goldens | COMPLETE | `backend/tests/test_var_es_golden.py`; rereview APPROVE |
| R0.1.2 Exact ES goldens | COMPLETE | same file; n=101 engine ES99 membership |
| R0.1.3 Approximate P&L unit goldens | COMPLETE | `backend/tests/test_approx_pnl_units_golden.py`; exact swap KR DV01=2150 |
| R0.1.4 Full-revaluation one-trade golden | COMPLETE | equity identity + option FULL≠LINEAR |
| R0.1.5 QuantLib global-state regression | COMPLETE | overlapping sessions contaminate Settings; RF-002 remains OPEN until R0.3 |
| R0.1.6 CI QuantLib hard gate | COMPLETE | job `backend-quantlib-hard-gate`; local 688 passed / 0 skipped |

No structural risk-engine refactoring started during R0.1.

## Phase A Completion Record

Completed:
- Exact VaR/ES goldens (RF-003)
- Approximate P&L unit goldens (partial RF-004 test net)
- Full-revaluation shocked-PV − base-PV goldens
- QuantLib process-state regression (exposes RF-002; does not fix it)
- CI QuantLib hard gate (partial RF-016)

Root findings closed:
- RF-003

Tests added:
- `backend/tests/test_var_es_golden.py`
- `backend/tests/test_approx_pnl_units_golden.py`
- `backend/tests/test_full_reval_golden.py`
- `backend/tests/test_quantlib_process_state.py`
- `backend/tests/test_quantlib_gate.py`
- `backend/tests/quantlib_gate.py`

Test results:
- backend builtin baseline: 659 passed
- QuantLib hard-gate: 688 passed, 0 skipped
- frontend: 74 passed; lint/build OK
- native: risk_kernel_ok; 8 pytest passed
- E2E: 12 passed
- PostgreSQL: BLOCKED (no Docker daemon)

Benchmarks:
- none in Phase A (correctness-only)

Known limitations:
- RF-002 still unsafe under overlapping QuantLib sessions (pinned by test)
- RF-004 production paths still split; units are now golden-tested
- RF-016 remaining tiers (Postgres nightly, PR-FULL matrix) deferred to R0.12

Remaining blockers:
- Docker/Postgres smoke not runnable on this host

Next phase:
- R0.2 Separate trade economics from market state (brief: `reviews/r0.2-architecture-brief.md`)

---

# R0.1 — Establish Quantitative Safety Nets

Related findings:

- RF-003
- RF-004
- RF-002
- RF-016

## R0.1.1 Exact VaR golden distributions

Add tiny deterministic P&L distributions with hand-computable answers.

Pin:

- VaR 95
- VaR 99
- loss/profit sign
- quantile/interpolation convention
- all-positive P&L
- all-negative P&L
- zero distribution
- tiny sample behavior

Acceptance:

A mutation that reverses the VaR tail or changes the percentile index must fail.

## R0.1.2 Exact Expected Shortfall goldens

Pin:

- tail membership
- threshold convention
- exact ES mean
- ES/VaR sign convention

Acceptance:

A mutation that averages the wrong side of the distribution must fail.

## R0.1.3 Approximate P&L unit goldens

Create deterministic one-factor examples for:

- equity delta
- gamma
- vega per vol point
- DV01 per bp
- key-rate DV01
- FX delta

Acceptance:

Tests fail if:

- DV01 is ×100;
- vega is ÷100;
- percentage/fraction is confused;
- bp/decimal is confused.

## R0.1.4 Full-revaluation one-trade golden

For a simple instrument and one or more explicit shocked snapshots:

```text
scenario P&L = shocked PV - base PV
```

Pin exact/toleranced values.

## R0.1.5 QuantLib global-state regression

Create a test using two QuantLib engine instances and different evaluation dates.

It must prove either:

- process-global serialization is safe;

or expose the current race before R0.3 fixes it.

## R0.1.6 CI QuantLib hard gate

Create a full CI job where:

- QuantLib installation is mandatory;
- import failure fails the job;
- QuantLib golden tests cannot `skip` to green.

### Exit criteria

No structural risk-engine refactoring starts until R0.1 is green.

---

# R0.2 — Separate Trade Economics from Market State

Related findings:

- RF-001
- RF-004
- RF-011
- RF-012

## R0.2.1 Introduce contractual trade/instrument terms

Production trade models should contain contractual economics such as:

- identifier
- instrument type
- quantity/notional
- currency
- strike
- maturity
- pay/receive
- contract multiplier
- fixed rate where contractual

Do not use trade models as the authoritative source of:

- live spot
- volatility
- current yield
- market swap rate
- FX spot
- market curves

## R0.2.2 Make MarketSnapshot authoritative

All production risk pricing must explicitly receive a market context.

Target:

```python
PricingEngine.value(trade, market_snapshot)
```

No-market pricing may remain only as an explicit demo/reference convenience, not as the production risk path.

## R0.2.3 Remove last-writer-wins snapshot construction

`PositionMarketDataProvider` must not be the canonical production market provider.

If needed, retain a clearly named demo adapter that seeds one snapshot from sample data with validation for conflicts.

## R0.2.4 Cache identity

Cache keys must be based on:

```text
trade economics
+ market snapshot identity/content
+ pricing configuration
+ as_of / relevant conventions
```

Do not hash duplicated trade-local market marks.

## R0.2.5 Mixed-market regression

Add a test proving multiple USD instruments with different market needs cannot overwrite one shared rate entry silently.

### Exit criteria

- Every production risk method prices from an explicit market.
- Base trade objects remain unchanged when market changes.
- One shared factor has one value per snapshot.

---

# R0.3 — Own QuantLib State Explicitly

Related findings:

- RF-002
- RF-007

## R0.3.1 Typed as-of date

Replace unconstrained/current snapshot date semantics with a real typed `date`.

## R0.3.2 Process-owned QuantLib session

Create a process-level QuantLib ownership boundary.

It must control:

- `Settings.evaluationDate`;
- index/fixing state;
- any other mutable QuantLib singleton state.

Do not rely on independent per-engine locks.

## R0.3.3 Fixing isolation

Prevent one valuation from leaving fixing history that affects another valuation.

## R0.3.4 Backdated valuation test

Price the same trade on two explicit as-of dates and prove the chosen snapshot date drives QuantLib.

## R0.3.5 Concurrency architecture

Document and implement:

- in-process QuantLib calls serialized by process-owned state;
- parallel full revaluation partitioned by **process** when needed;
- native pure kernels remain QuantLib-free.

### Exit criteria

Two concurrent/request-equivalent valuation contexts cannot contaminate one another.

---

# R0.4 — Converge Market and Scenario Contracts

Related findings:

- RF-004
- RF-006
- RF-011

## R0.4.1 Typed market structures

Replace nested raw dictionaries where practical with typed domain models for:

- yield curves;
- vol surfaces;
- FX market;
- equity market.

## R0.4.2 One canonical Scenario model

Converge:

- legacy stress scenarios;
- historical scenarios;
- formal typed scenarios

onto one engine-facing representation:

```text
Scenario
  id
  name
  category
  shocks: FactorShock[]
  metadata
```

Keep legacy wire adapters only during the migration.

## R0.4.3 Explicit shock units

Every factor shock must have one unambiguous internal convention.

Examples:

- equity/FX relative move: decimal fraction
- rate move: choose one internal representation and document it
- vol shift: choose decimal-vol or vol-point internal representation and document it

No magnitude heuristic may decide units.

## R0.4.4 One-pass snapshot transformation

Apply all scenario shocks to a staging market object and freeze once.

Do not perform one deep immutable copy per factor.

## R0.4.5 Scenario once, price many

Stress/scenario execution creates one shocked snapshot per scenario and reuses it across positions.

### Exit criteria

- semantic parity tests pass;
- unit tests pin conversions;
- factor count no longer causes repeated whole-snapshot copy/refreeze per factor.

---

# R0.5 — Complete the Factor Model

Related findings:

- RF-005
- RF-012

## R0.5.1 Instrument capability registry

Create a coherent registry or adapter mechanism that defines for each instrument family:

- pricing adapter;
- required market factors;
- supported sensitivities;
- factor exposure mapping.

Do not create an elaborate plugin framework.

## R0.5.2 Remove silent production fallback

QuantLib production mode must not silently switch to builtin pricing for an unknown instrument.

Unsupported product should fail explicitly.

## R0.5.3 Per-factor historical observations

Replace the four-macro-only history abstraction with a typed factor panel.

Conceptually:

```text
date
RiskFactor -> observation/change
```

Support per-name and per-tenor moves.

## R0.5.4 Preserve demo compatibility

The existing four-column synthetic dataset may remain as:

- a documented demo projection;
- a fixture;
- a compatibility loader.

It must not be presented as full multi-asset historical factor history.

## R0.5.5 Contribution semantics

Ensure factor contributions are calculated against the factor-complete scenario representation.

Do not allow an omitted factor to disappear into `interaction` without a reconciliation signal.

### Exit criteria

Two equities and two rate tenors can move independently in one historical observation.

---

# R0.6 — Rebuild Full-Revaluation Execution Around Reuse

Related findings:

- RF-006
- RF-007
- RF-015

## R0.6.1 Baseline benchmark first

Record current performance for:

```text
N = 10, 100, 1k
S = 50, 750, 1k where practical
```

Capture:

- wall time
- RSS
- scenarios/sec
- builtin vs QuantLib
- cache hit/miss

## R0.6.2 Stream/chunk shocked scenarios

Do not materialize all shocked markets when not required.

## R0.6.3 Reuse QuantLib structures where safe

Evaluate:

- relinkable quotes;
- relinkable handles;
- cached instrument terms/schedules;
- cached curve structure where scenario semantics allow.

Do not cache stale market state.

## R0.6.4 Remove anti-cache behavior

If the valuation LRU is slower for unique shocked markets, disable it for that execution class or redesign the caching level.

## R0.6.5 Process-level scenario parallelism

Partition independent scenario blocks across worker processes when profiling shows value.

## R0.6.6 Contribution reuse

Avoid whole-book full revaluation once per factor family when the same trade/scenario P&Ls can be reused or decomposed coherently.

### Exit criteria

Full revaluation is still allowed to be expensive, but its scaling is explainable, benchmarked, bounded, and appropriate for a risk-run job.

---

# R0.7 — Rebuild Hierarchy from Reusable Trade-Level Results

Related findings:

- RF-008

## R0.7.1 Stable hierarchy identifiers

Create explicit IDs for:

```text
Firm
Portfolio
Desk
Strategy
Book
Trade
```

## R0.7.2 Trade-grain calculation artifact

A risk run should be able to produce/reuse:

- trade PV;
- additive sensitivities;
- stress P&L by scenario;
- historical P&L vector where appropriate.

## R0.7.3 Aggregate instead of reprice

- additive metrics sum;
- stress sums from trade P&Ls;
- node VaR/ES computes from node scenario P&L vector;
- limits target a stable node.

## R0.7.4 Lazy drilldown

Do not return massive nested by-position payloads on every hierarchy node unless requested.

### Exit criteria

Hierarchy time is driven primarily by one base calculation + aggregation, not number-of-nodes × full-risk-run.

---

# R0.8 — Make RiskRun Reproducible and Canonical

Related findings:

- RF-009
- RF-013
- RF-010

## R0.8.1 Deterministic RiskRun specification

RiskRun must reference:

- portfolio ID/version;
- market snapshot ID;
- historical dataset ID/version;
- scenario set/version;
- pricing engine/version;
- methodology;
- as-of;
- calculation config.

## R0.8.2 Same factories in API and worker

API interactive path and worker must resolve historical data/pricing config through the same dependency construction.

## R0.8.3 Server-owned persistence identity

Separate:

```text
create portfolio
update portfolio
calculate inline demo
calculate persisted portfolio
```

Do not upsert arbitrary stored portfolios because a request supplied the same ID.

## R0.8.4 Typed run requests

Replace `dict[str, Any]` calculation request blobs with discriminated typed run-request schemas.

## R0.8.5 Postgres integration tests

Add pytest/integration coverage for:

- save/load;
- run create;
- worker claim;
- status lifecycle;
- failed run;
- two-worker claim safety;
- portfolio identity protection.

### Exit criteria

The same RiskRun spec yields the same result whether executed interactively or by the worker.

---

# R0.9 — Separate Domain, API, and Application Contracts

Related findings:

- RF-010
- RF-013

## R0.9.1 Split transport schemas

Move HTTP request/response models into API schema modules.

## R0.9.2 Typed risk results

Replace generic result dictionaries where a stable typed domain/application result is appropriate.

## R0.9.3 Explicit application composition

Replace process-global orchestration objects with application/lifespan composition.

## R0.9.4 Keep refactor bounded

Do not introduce:

- service locator frameworks;
- DI containers;
- unnecessary repository interfaces;
- one-file-per-class churn.

### Exit criteria

Domain logic can be tested without importing FastAPI transport schemas.

---

# R0.10 — Interactive vs Heavy Calculation Contract

Related findings:

- RF-015
- RF-007
- RF-008

## R0.10.1 Classify endpoints

Cheap/interactive examples:

- completed run retrieval;
- lightweight summary;
- small factor drilldown.

Heavy/risk-run examples:

- FULL_REVALUATION;
- large hierarchy;
- reverse multi-factor;
- expensive what-if;
- large scenario evaluation;
- heavy contribution analysis.

## R0.10.2 Dashboard batch/run result

Stop loading a dashboard by launching many overlapping calculations against the same book.

Prefer one completed risk-run artifact or a coherent batch service.

## R0.10.3 Queue/backpressure

Bound:

- outstanding jobs;
- worker concurrency;
- scenario count;
- portfolio size.

### Exit criteria

Large risk cannot monopolize ordinary HTTP request execution indefinitely.

---

# R0.11 — Close the Deployment and Input Boundary

Related findings:

- RF-014
- RF-018

## R0.11.1 Safe local defaults

Compose defaults:

- API bound to loopback;
- frontend bound appropriately;
- Postgres not published externally unless explicitly enabled.

## R0.11.2 Finite financial numbers

Reject:

- NaN;
- +Infinity;
- -Infinity;
- clearly invalid maturities;
- invalid FX pair shapes;
- pathological request sizes.

## R0.11.3 Workload limits

Define configurable max:

- positions;
- scenarios;
- observations;
- reverse-stress iterations;
- queued runs;
- request body size.

## R0.11.4 Error sanitization

Failed risk runs must not expose raw internal exception strings as the public contract.

## R0.11.5 Shared deployment auth gate

If a non-loopback/shared deployment profile is supported, require:

- authentication;
- object authorization;
- TLS/reverse proxy boundary;
- secret management.

Do not overbuild enterprise auth for the local demo profile.

## R0.11.6 Container/dependency hardening

- non-root runtime where practical;
- pin frontend runtime/build dependencies;
- deterministic `npm ci`;
- document resource expectations.

### Exit criteria

`docker compose up` is safe by default for a local development machine and clearly not presented as internet-ready without the shared-deployment profile.

---

# R0.12 — Production-Relevant Verification Matrix

Related findings:

- RF-016
- RF-018
- RF-017

## R0.12.1 PR-FAST

Run:

- backend deterministic unit suite;
- VaR/ES goldens;
- pricing goldens;
- high-value properties;
- frontend unit tests;
- frontend lint.

## R0.12.2 PR-FULL

Mandatory:

- QuantLib installed and exercised;
- complete backend suite;
- native compile/parity;
- frontend tests;
- frontend production build;
- semantic API tests;
- critical Playwright flow;
- Ruff/mypy/ESLint using documented current strictness.

## R0.12.3 Critical E2E journey

Create one defensible workflow:

```text
load persisted/demo portfolio
→ inspect VaR/ES
→ create stress scenario
→ execute
→ inspect contributors
→ add hypothetical hedge
→ rerun
→ verify changed risk
```

Capture/assert request units where percent/bp conversion matters.

## R0.12.4 Nightly / labeled runner

- Postgres two-worker test;
- larger FULL_REVALUATION sample;
- native benchmark SLA;
- scenario-application benchmark;
- hierarchy benchmark;
- optional QuantLib E2E.

## R0.12.5 Native ABI safety

Add explicit ABI/version/error/length validation before expanding native use.

### Exit criteria

A "green full CI" means the production-relevant QuantLib, native, frontend build, API, and persistence paths actually executed.

---

# R0.13 — Documentation and Roadmap Reconciliation

Related findings:

- RF-020

## R0.13.1 Preserve history

Do not erase completed historical milestones.

Document that independent review created a new remediation milestone.

## R0.13.2 Make status conservative

Do not use COMPLETE for a workstream whose acceptance criteria are contradicted by an open P0/P1 root finding.

## R0.13.3 Update known limitations

Explicitly document:

- synthetic/approximate historical data;
- fast approximate VaR vs full revaluation;
- full-revaluation scale;
- local-demo security boundary;
- QuantLib concurrency model;
- native kernel scope.

## R0.13.4 Current test/benchmark evidence

Record reproducible current commands and results, not stale counts.

---

# P2 Work That Does Not Block R0

These findings stay visible but should not delay closure of the core milestone unless touched by related work.

## Native micro-optimization

Related: RF-017

Do not pursue SIMD/thread-pool tuning until profiling after RF-005/RF-007.

## Frontend TypeScript migration

Related: RF-018

Not required solely for optics. Consider only after API schemas stabilize.

## AI routing expansion

Related: RF-019

Deferred until deterministic tools are stable.

---

# R0 Final Exit Checklist

Milestone R0 is COMPLETE only when:

## Correctness

- [ ] exact VaR/ES goldens pass
- [ ] approximate P&L unit goldens pass
- [ ] full-revaluation one-trade goldens pass
- [ ] market snapshot is authoritative
- [ ] trade-local marks cannot override production market state
- [ ] historical observations can represent per-factor moves
- [ ] scenario contribution reconciliation is defensible

## QuantLib

- [ ] snapshot as-of drives evaluation date
- [ ] process-global state is safely owned
- [ ] fixing contamination test passes
- [ ] QuantLib is mandatory in full CI

## Execution

- [ ] scenario apply is one-pass
- [ ] full-revaluation benchmark recorded
- [ ] hierarchy reuses trade-level results
- [ ] heavy computations use risk-run execution at meaningful scale
- [ ] dashboard does not launch redundant full calculations

## Persistence / runs

- [ ] RiskRun captures deterministic input identities
- [ ] API and worker use the same historical dataset/config
- [ ] client cannot overwrite a stored portfolio by choosing its ID
- [ ] Postgres worker lifecycle tests pass

## Security / operability

- [ ] local Compose defaults are loopback-safe
- [ ] Postgres is not publicly mapped by default
- [ ] non-finite financial inputs rejected
- [ ] workload limits enforced
- [ ] failed runs do not expose raw internal errors
- [ ] shared deployment requires auth/authorization

## QA / CI

- [ ] backend full suite passes
- [ ] QuantLib hard-gate passes
- [ ] frontend tests pass
- [ ] frontend production build passes
- [ ] native compile/parity passes
- [ ] Postgres integration passes
- [ ] critical E2E workflow passes
- [ ] static analysis passes at documented strictness

## Documentation

- [ ] `FINDINGS.md` statuses updated
- [ ] `ROADMAP.md` includes Milestone R0
- [ ] known limitations match reality
- [ ] benchmark/test claims are current and reproducible

Only after this checklist is complete should normal net-new feature development resume.
