# RiskForge Consolidated Engineering Findings

Date: 2026-09-03  
Status: R0 IN PROGRESS — Phase B (R0.2-A APPROVE; RF-001 still open)  
Inputs:

- `architecture-review.md`
- `performance-review.md`
- `security-review.md`
- `qa-review.md`

This file consolidates the independent reviews by **root cause**, not by reviewer finding count.

The four reports contain 81 formal findings in total:

- Architecture: 27
- Performance: 19
- Security: 10
- QA: 25

Those findings are collapsed here into **20 root findings**.

## Priority Model

### P0 — Correctness / architectural blockers

Must be resolved before RiskForge should be trusted as the foundation for additional product features. These findings can cause materially incorrect risk results, cross-request contamination, non-reproducible runs, or an execution architecture that cannot support the stated product model.

### P1 — Production-quality blockers

Must be resolved before the current platform should be considered production-style or before major additional surface area is layered on top. These include API/persistence ownership, workload controls, asynchronous execution, CI gates, and deployment/security boundaries.

### P2 — Hardening / maintainability

Important but not allowed to distract from P0/P1 remediation. These can be completed after the core remediation gate unless they are touched naturally by a P0/P1 change.

---

# Executive Summary

## Finding counts

- P0: 9
- P1: 7
- P2: 4
- Total root findings: 20

## Recommended engineering decision

**Pause net-new feature development.**

Create and complete **Milestone R0 — Core Remediation & Trustworthiness** before continuing the feature roadmap.

The current repository is a strong MVP with unusually broad test coverage, real QuantLib integration, deterministic demo data, a credible pricing seam, native parity tests, and good separation of the native numerical kernel from business logic.

The reviews nevertheless converge on six foundational problems:

1. Trade economics and market state are not fully separated.
2. QuantLib process-global state is not safely owned by the valuation context.
3. VaR/ES correctness is not pinned by exact hand-computable golden distributions.
4. Historical factor modeling remains a four-macro approximation rather than a true per-factor panel.
5. Full revaluation, scenario application, and hierarchy execution do not scale with the target model.
6. Risk runs, persistence, HTTP contracts, and deployment boundaries are not yet the canonical source of truth.

## Top 10 root findings

1. **RF-001 — Trade economics and market state are mixed**
2. **RF-003 — VaR/ES exact semantics are not independently proven**
3. **RF-002 — QuantLib global state and as-of date are not process-owned**
4. **RF-004 — Approximate risk uses split sensitivity/P&L paths and ambiguous units**
5. **RF-005 — Historical VaR broadcasts four macro factors across a multi-asset book**
6. **RF-006 — Scenario application repeatedly copies/refreezes whole snapshots**
7. **RF-007 — Full revaluation and contribution paths are N×S reconstruction loops**
8. **RF-008 — Hierarchy recomputes full risk independently at every node**
9. **RF-009 — API and worker risk runs can use different historical datasets**
10. **RF-013 — Persistence/API identity is not yet canonical and client IDs can overwrite books**

---

# Cross-Cutting Root Causes

## A. Market ownership is not singular

Several findings are different manifestations of the same architectural issue: contractual trade data and market observables are both present on position models, then a snapshot is derived from positions. That produces last-writer-wins market state, makes cache keys depend on duplicated marks, forces market overlays back into trade copies, and makes some approximate risk paths ignore a supplied snapshot.

## B. There is more than one risk-calculation path

RiskForge currently has analytical Greeks, bump/revalue sensitivities, reference/builtin pricing, QuantLib pricing, macro historical P&L approximations, full revaluation, and native approximations. The seams are reasonable individually, but units and market ownership are not yet guaranteed to be identical across all paths.

## C. Scenario representation and application are fragmented

Legacy `StressScenario`, historical `MarketScenario`, formal typed `Scenario`, and raw factor changes coexist. Snapshot transforms live partly in the domain model and can repeatedly deep-copy immutable data.

## D. Expensive risk is recomputed instead of reused

Dashboard endpoints, hierarchy nodes, contribution paths, reverse stress, and full revaluation repeatedly reconstruct the same valuations/scenarios. The native kernel is not the dominant bottleneck for the paths that are currently slow.

## E. Persistence is adjacent to, not authoritative for, live calculations

The live UI/API still commonly POSTs a whole portfolio. Risk runs and stored snapshots do not yet define a canonical `(portfolio, market snapshot, methodology, dataset)` calculation identity.

## F. Test breadth is stronger than test semantic depth for VaR/ES

Pricing tests are strong. VaR/ES tests are broad but do not yet pin exact quantile direction, interpolation, tail selection, and approximate P&L units with tiny hand-computable distributions.

---

# Root Findings

## RF-001 — Trade economics and market state are mixed

Priority: **P0**  
Risk types: CORRECTNESS, ARCHITECTURE, MAINTAINABILITY  
Confidence: HIGH  
Status: **IN PROGRESS** (R0.2-A APPROVE; equity spots+option vol fail closed; what-if reuses one snapshot; equity future/option r/q fail closed with aggregate demo yields seeded; dashboard/compare/reverse/drilldown thread one root snapshot. Remaining: other families, terms split, engine omitted-`market=` inference.)

Source findings:

- ARCH-001
- ARCH-004
- ARCH-008
- ARCH-012
- QA-002

### Root cause

Position objects contain both contractual economics and market observables such as spot, volatility, yield, market swap rate, and FX marks. `PositionMarketDataProvider` then reconstructs market state by iterating the portfolio.

That makes the position simultaneously:

- a trade;
- a source of market data;
- a fallback market;
- part of the pricing cache identity.

### Why it matters

A single USD bond and USD swap can carry inconsistent rates; one shared key can overwrite another during snapshot construction. Stress/full-revaluation then operates on the collapsed state.

The architecture also makes it possible for one risk path to use the supplied `MarketSnapshot` while another uses marks embedded in the trade.

### Required direction

Introduce an explicit split:

```text
Trade / InstrumentTerms
    contractual economics only

MarketSnapshot
    authoritative observable market state
```

Pricing must require a market context for production risk calculations.

A demo-only adapter may create a snapshot from sample marks, but this must not remain the production market path.

### Acceptance evidence

- Two trades referencing the same market factor cannot define two competing values for that factor.
- Pricing on snapshot A vs B changes only because the supplied market changes.
- No production risk method calls pricing without an explicit market.
- Cache identity separates trade economics from snapshot identity.
- Regression test proves a mixed USD book cannot last-writer-win.

### Dependencies

None. This is the primary architecture dependency for several other fixes.

---

## RF-002 — QuantLib global state and as-of date are not safely process-owned

Priority: **P0**  
Risk types: CORRECTNESS, CONCURRENCY, ARCHITECTURE  
Confidence: HIGH  
Status: **IN PROGRESS** (R0.1.5 regression documents the gap; fix is R0.3)

Source findings:

- ARCH-002
- QA-012
- QA-004 (test-gate aspect)
- PERF-011 (lifecycle aspect)

### Root cause

QuantLib has process-global settings and fixing history. The current adapter sets evaluation date using wall-clock/current behavior and protects calls with an engine-instance lock. Multiple engine instances can therefore fail to serialize access to process-global QuantLib state.

Snapshot `as_of` is not the authoritative QuantLib evaluation date.

### Why it matters

Concurrent requests or worker activity can contaminate another valuation's evaluation date/fixings. Backdated risk runs cannot be reproduced reliably if wall-clock date participates.

### Required direction

Create an explicit process-owned QuantLib valuation session:

- one process-level lock/session boundary;
- typed `MarketSnapshot.as_of: date`;
- evaluation date driven from valuation context;
- fixing history isolated/cleared or process-isolated;
- process-level parallelism for independent QuantLib full-revaluation partitions.

### Reviewer disagreement resolved

The performance review described QuantLib as protected by an `RLock`; the architecture review showed that the lock is instance-scoped while QuantLib state is process-global.

**Final assessment:** treat this as unresolved and unsafe until a regression test creates two engine instances and proves isolation.

### Acceptance evidence

- Two QuantLib engines cannot race evaluation date.
- Backdated valuation uses snapshot `as_of`, never `date.today()`.
- Repeated valuation leaves no fixing contamination.
- Parallel full-revaluation design uses processes or another demonstrated-safe ownership model.

---

## RF-003 — VaR and ES exact statistical semantics are not independently proven

Priority: **P0**  
Risk types: CORRECTNESS, TEST_GAP  
Confidence: HIGH  
Status: **CLOSED**

Evidence:
- `backend/tests/test_var_es_golden.py`
- Hand-computable cases A–G (VaR 95/99, all-positive, all-negative, zero, n=1, n=2, n=4)
- ES tail membership: n=21 at 95% (VaR=19, ES=19.5 vs strict `>` =20); HistoricalRiskEngine n=101 (VaR99=19, ES99=99.5 vs 100)
- Independent review recomputed goldens without `np.quantile`; rereview **APPROVE** (`reviews/r0.1-rereview.md`)
- Focused suite: 29 passed; broader quant regression: 157 passed; full QuantLib suite: 688 passed, 0 skipped

Source findings:

- QA-001
- QA-003
- QA-009
- QA-010
- QA-006 (contribution meaning)
- PERF-017 (quantile implementation should remain methodology-defined)

### Root cause

Most VaR/ES tests assert ordering, non-negativity, determinism, or that methodologies differ. They do not use enough tiny hand-computable P&L distributions where the exact expected VaR/ES is obvious.

A wrong loss/profit tail, wrong percentile, wrong interpolation rule, or incorrect ES tail mean can remain green.

### Why it matters

This is the highest-value test gap in the repository. Large test count does not compensate for missing exact statistical goldens.

### Required direction

Before risk-engine refactoring, add tiny deterministic golden cases that pin:

- P&L → loss conversion;
- VaR 95 / 99;
- interpolation/quantile convention;
- ES tail membership and mean;
- all-positive P&L behavior;
- all-negative P&L behavior;
- exact full-revaluation `shocked PV - base PV`;
- component/contributor methodology labeling.

### Acceptance evidence

Mutation-style tests would fail if:

- loss tail is reversed;
- percentile index is off by one;
- ES averages the wrong tail;
- sign is flipped;
- P&L is treated as return incorrectly.

This safety net must land **before** structural risk-engine changes.

---

## RF-004 — Approximate risk uses split Greek/P&L pipelines and insufficiently pinned units

Priority: **P0**  
Risk types: CORRECTNESS, ARCHITECTURE, TEST_GAP  
Confidence: HIGH  
Status: **IN PROGRESS** (R0.1.3 unit goldens; production unification is R0.2/R0.4)

Source findings:

- ARCH-008
- ARCH-012
- QA-002
- QA-003
- QA-008
- QA-018
- SEC-007

### Root cause

Analytical pricing Greeks, bump/revalue sensitivities, historical approximate P&L, UI scenario conversion, and scenario wire units do not all flow through one authoritative convention.

Examples of exposed risk:

- vol decimal vs vol point;
- rate decimal vs bp;
- percent vs fraction;
- long/short and payer/receiver signs;
- a supplied market snapshot ignored by one path;
- heuristic conversion of rate shock magnitudes.

### Required direction

Define a single unit/convention contract and one authoritative risk-factor shock representation.

Approximate historical P&L must be independently golden-tested from typed factors.

Bump/revalue should become the reference risk sensitivity path where practical, even if analytical Greeks remain as optimized implementations with parity tests.

### Acceptance evidence

Tests must fail for:

- DV01 ×100;
- vega ÷100;
- 100 bp interpreted as 100%;
- UI `20%` sent as `20` instead of `0.20`;
- pricing on trade-local marks when a different snapshot was supplied.

---

## RF-005 — Historical risk is a four-macro broadcast, not a factor-complete multi-asset model

Priority: **P0**  
Risk types: CORRECTNESS, METHODOLOGY, ARCHITECTURE  
Confidence: HIGH

Source findings:

- ARCH-007
- ARCH-006 (factor coverage aspect)
- PERF-007
- QA-006

### Root cause

Historical observations are represented by four aggregate series:

- equity
- volatility
- rates
- FX

Those moves are then broadcast to every corresponding name/factor.

### Why it matters

This is acceptable as a documented demo approximation, but it cannot support credible per-name multi-asset historical VaR, factor contributions, key-rate structures, or cross-asset historical scenarios.

It also means the native 5-column exposure kernel is optimized around the current approximation rather than the target factor model.

### Required direction

Introduce a per-factor observation panel keyed by typed `RiskFactor`.

Keep the current four-column dataset as an explicitly documented projection/demo dataset if useful.

### Acceptance evidence

- NVDA and SPX can have different historical returns on the same date.
- USD 2Y and USD 10Y can have different moves.
- factor contributions trace to actual factor histories.
- missing factor history has explicit behavior.
- historical methodology metadata says whether data is real, synthetic, transformed, or approximated.

---

## RF-006 — Scenario application copies/refreezes whole snapshots repeatedly

Priority: **P0**  
Risk types: PERFORMANCE, ARCHITECTURE, CORRECTNESS  
Confidence: HIGH

Source findings:

- PERF-001
- PERF-005
- PERF-012
- ARCH-004
- QA-005

### Root cause

A multi-factor scenario is applied as repeated immutable `bump()` operations. Each bump copies/refreezes nested snapshot structures. Stress helpers can also rebuild the same shocked scenario per trade.

Measured reviewer evidence showed extreme growth as factor count increases.

### Required direction

Apply an entire scenario in one staged transformation:

```text
base immutable snapshot
→ mutable staging representation
→ apply all typed shocks
→ validate
→ freeze once
→ new immutable snapshot
```

Create the shocked snapshot once per scenario, not once per trade.

### Acceptance evidence

- exact parity with existing scenario semantics;
- one freeze/copy per scenario rather than per factor;
- benchmark factor count × scenario count;
- zero shock and unrelated-factor invariants remain exact;
- contribution tests prove a factor cannot disappear into an unexplained `interaction` bucket.

---

## RF-007 — Full revaluation and contribution paths reconstruct N×S QuantLib work

Priority: **P0**  
Risk types: PERFORMANCE, OPERABILITY, ARCHITECTURE  
Confidence: HIGH

Source findings:

- PERF-002
- PERF-006
- PERF-008
- PERF-009
- PERF-010
- PERF-011
- PERF-013
- SEC-002

### Root cause

Full-revaluation paths loop through scenarios and trades in Python, repeatedly rebuilding QuantLib curves, engines, instruments, and processes. Contributions can multiply this work by factor families. The generic pricing LRU has near-zero hit rate on unique shocked snapshots.

### Required direction

Use a measured execution architecture:

1. stream/chunk scenarios;
2. build scenario market state once;
3. reuse instrument structures or relinkable market handles where safe;
4. parallelize QuantLib scenario partitions by process, not in-process threads;
5. move large full-revaluation jobs to `RiskRun`;
6. keep interactive LINEAR / DELTA_GAMMA as the fast default;
7. remove/disable caches that make unique-shock workloads slower.

### Acceptance evidence

Benchmark and record:

- N trades × S scenarios;
- wall time;
- peak RSS;
- scenarios/sec;
- built-in vs QuantLib;
- warm vs cold;
- identical numerical results to the pre-change golden suite.

Do not set a fake universal SLA until benchmark environments are controlled.

---

## RF-008 — Hierarchy recomputes full risk independently at every node

Priority: **P0**  
Risk types: PERFORMANCE, ARCHITECTURE, OPERABILITY  
Confidence: HIGH

Source findings:

- ARCH-011
- PERF-003
- PERF-019
- ARCH-015 (limit-scope aspect)

### Root cause

Hierarchy is currently label-based portfolio slicing. Each hierarchy node reconstructs a sub-portfolio and recomputes VaR, stress, limits, and sometimes sensitivities.

### Required direction

Compute trade-grain results once per run:

- valuation;
- additive Greeks;
- scenario P&L vector;
- historical P&L vector where methodology supports it.

Then:

- aggregate additive metrics up the hierarchy;
- compute node VaR/ES from aggregated P&L vectors, not repricing;
- evaluate limits against explicit stable hierarchy-node IDs;
- lazily fetch expensive details for drilldown.

### Acceptance evidence

- additive metrics exactly reconcile;
- node VaR equals VaR computed from the node's aggregated scenario P&L vector;
- stable node IDs exist;
- a hierarchy request does not execute one independent full risk run per trade.

---

## RF-009 — Risk-run reproducibility differs between API and worker execution

Priority: **P0**  
Risk types: CORRECTNESS, REPRODUCIBILITY, OPERABILITY  
Confidence: HIGH

Source findings:

- SEC-005
- ARCH-009
- QA-009 (reproducibility aspect)

### Root cause

The API dependency path and out-of-process worker can construct historical risk engines from different historical datasets/defaults.

A queued risk run can therefore produce a different result from the same interactive request even when the portfolio is identical.

### Required direction

A `RiskRun` must capture or reference all deterministic calculation inputs:

```text
portfolio_id + version
market_snapshot_id
historical_dataset_id/version
scenario_set_id/version
pricing engine/version
methodology
as_of
calculation configuration
```

API and worker must resolve the same identifiers through the same factories/repositories.

### Acceptance evidence

Interactive and worker calculations with the same run specification produce the same result within explicit tolerance.

---

## RF-010 — Domain entities, risk results, HTTP DTOs, and orchestration are overly coupled

Priority: **P1**  
Risk types: ARCHITECTURE, MAINTAINABILITY  
Confidence: HIGH

Source findings:

- ARCH-003
- ARCH-009
- ARCH-014
- ARCH-019

### Root cause

`domain/models.py` contains trade/domain models, market snapshot, risk outputs, hierarchy data, and request/response bodies. `PortfolioService` is a process-wide orchestrator owning many engines. `RiskEngine.calculate` returns an untyped dictionary.

### Required direction

Separate:

```text
domain/
application/
api/schemas/
persistence/
```

Use typed calculation result models.

Use FastAPI lifespan/application composition rather than a module-global service singleton.

Do not split files merely for aesthetics; split ownership and contracts.

### Acceptance evidence

- domain package has no FastAPI transport responsibilities;
- versioned API schemas can change without changing domain entities;
- result types are typed;
- service composition is explicit and testable.

---

## RF-011 — Scenario and market-data models remain fragmented or untyped

Priority: **P1**  
Risk types: ARCHITECTURE, CORRECTNESS, MAINTAINABILITY  
Confidence: HIGH

Source findings:

- ARCH-005
- ARCH-013
- ARCH-020
- QA-016
- QA-017

### Root cause

Three scenario forms coexist, while curves and volatility surfaces use nested untyped dictionaries. Some pricing defaults are currency-specific/hardcoded.

### Required direction

- One canonical typed `Scenario` with typed factor shocks.
- Typed curve/surface models.
- Typed currency and FX-pair semantics.
- Legacy HTTP scenario type only as a temporary adapter.
- Explicit equity-currency/rate selection.

### Acceptance evidence

- historical, stress, custom, reverse, persistence, and API all converge on the same typed factor model;
- invalid FX pairs/market shapes fail validation;
- currency-specific rate selection is explicit.

---

## RF-012 — Instrument capabilities are duplicated across isinstance ladders and can silently fall back

Priority: **P1**  
Risk types: ARCHITECTURE, CORRECTNESS, MAINTAINABILITY  
Confidence: HIGH

Source findings:

- ARCH-006
- ARCH-012
- QA-011
- QA-013

### Root cause

Pricing, market overlays, snapshot construction, and risk-factor extraction each dispatch independently on concrete instrument types. The QuantLib adapter can silently fall back to builtin behavior for unknown product types.

### Required direction

Introduce a small instrument capability/adapter registry defining:

- pricing implementation;
- required market factors;
- supported sensitivities;
- risk-factor extraction;
- fallback policy.

Unknown production instruments should fail explicitly rather than silently changing methodology.

### Acceptance evidence

Adding a new instrument requires one coherent adapter registration plus tests, not edits to parallel ladders across many packages.

---

## RF-013 — Persistence and HTTP identity are not canonical; client IDs can overwrite stored portfolios

Priority: **P1**  
Risk types: INTEGRITY, ARCHITECTURE, SECURITY  
Confidence: HIGH

Source findings:

- ARCH-010
- SEC-003
- QA-015
- PERF-016

### Root cause

The live risk API still accepts whole portfolio payloads while persistence is a parallel path. Risk-run submission can persist/upsert a client-supplied portfolio ID and replace an existing stored book.

### Required direction

Make persisted immutable/versioned identities canonical for production-style runs:

```text
portfolio_id / portfolio_version
market_snapshot_id
risk_run_id
```

Separate create vs update semantics. Server controls ownership/versioning.

Keep an explicit inline/debug calculation endpoint only for tests/demo tooling.

### Acceptance evidence

- a request cannot overwrite `global-macro` merely by supplying that ID;
- a persisted risk run can be reproduced from IDs;
- PostgreSQL path has real pytest/integration coverage;
- large derived payloads are not blindly duplicated as unconstrained JSON where a structured/reference model is better.

---

## RF-014 — API/deployment boundary lacks production workload, input, and access controls

Priority: **P1**  
Risk types: SECURITY, AVAILABILITY, OPERABILITY  
Confidence: HIGH  
Status: **IN PROGRESS** (R0.11.1 loopback APPROVE; R0.11.2 finite scalars APPROVE; R0.11.3 workload caps APPROVE; R0.11.4 sanitization APPROVE; R0.11.6 container pins APPROVE; remaining R0.11.5 auth)

Source findings:

- SEC-001
- SEC-002
- SEC-004
- SEC-006
- SEC-008
- SEC-010
- QA-021
- ARCH-024
- ARCH-025

### Root cause

The application is legitimately a local/demo system, but Compose can publish FastAPI and Postgres beyond loopback. No authentication/authorization exists, expensive risk payloads are not consistently capped, numeric scalars can accept non-finite/extreme values, and runtime containers are not hardened for shared deployment.

### Required direction

For the current demo profile:

- bind API/frontend services to loopback by default;
- do not publish Postgres to host unless explicitly requested;
- remove demo credential patterns from any shared deployment profile;
- validate finite financial numbers;
- cap positions/scenarios/history/work queue;
- sanitize stored/returned exception strings.

For any non-local/shared profile:

- authentication;
- authorization/object ownership;
- TLS/reverse-proxy boundary;
- request and concurrency limits;
- non-root runtime;
- documented secret-management model.

### Acceptance evidence

The repository clearly differentiates:

```text
local demo
shared/internal deployment
production-like deployment
```

Missing auth is not called a vulnerability for strict loopback use, but public exposure is blocked by configuration and documentation.

---

## RF-015 — Interactive UI fans out redundant synchronous risk calculations

Priority: **P1**  
Risk types: PERFORMANCE, OPERABILITY, API  
Confidence: HIGH

Source findings:

- PERF-004
- PERF-010
- PERF-015
- ARCH-017
- QA-014

### Root cause

Dashboard loading invokes many independent endpoints, repeatedly POSTing the entire portfolio and recalculating overlapping metrics. Heavy methods are available synchronously even though a risk-run model already exists.

### Required direction

Define execution classes:

### Interactive

- cheap summary
- existing completed-run retrieval
- lightweight drilldown

### RiskRun / async

- FULL_REVALUATION
- hierarchy at material scale
- full contribution analysis
- reverse multi-factor
- expensive what-if
- large scenario sets

Return one coherent dashboard/run result rather than nine independent calculations where practical.

### Acceptance evidence

A dashboard load does not execute redundant full valuations of the same book and snapshot.

---

## RF-016 — CI/test gates do not fully prove production-relevant execution paths

Priority: **P1**  
Risk types: TEST_GAP, CI, OPERABILITY  
Confidence: HIGH  
Status: **IN PROGRESS** (R0.1.6 QuantLib hard-gate; R0.12.1–R0.12.3 APPROVE; R0.12.5 native ABI APPROVE; R0.12.4 nightly sibling workflow APPROVE. Remaining: labeled-runner SLA-K1/K2, hierarchy benchmark, QuantLib E2E. Not CLOSED.)

Source findings:

- QA-004
- QA-007
- QA-014
- QA-015
- QA-019
- QA-020
- QA-024
- QA-021

### Root cause

The local review ran QuantLib successfully, but CI can still pass if QuantLib is skipped. PostgreSQL is mostly a smoke path, E2E uses builtin pricing, several API tests assert shape/status more than financial semantics, and static-analysis success uses staged relaxations.

### Required direction

Establish explicit tiers:

### PR-FAST
Deterministic core unit/golden/property tests.

### PR-FULL
- QuantLib import is mandatory;
- QuantLib golden suite;
- native compile/parity;
- frontend test/build;
- semantic API contract tests;
- critical Playwright path.

### NIGHTLY
- PostgreSQL worker concurrency;
- larger full-revaluation samples;
- benchmark/SLA on labeled runner;
- optional QuantLib E2E/demo range check.

### Acceptance evidence

A broken QuantLib installation cannot produce a green "full" CI run.

---

## RF-017 — Native kernel boundary needs ABI hardening, but more C++ is not the current priority

Priority: **P2**  
Risk types: PERFORMANCE, MAINTAINABILITY, NATIVE_SAFETY  
Confidence: HIGH  
Status: **IN PROGRESS** (R0.12.5 ABI version/length/null fail-closed APPROVE. Remaining: contiguous NumPy path, per-call thread setup; do not expand native VaR/QuantLib.)

Source findings:

- ARCH-016
- ARCH-022
- PERF-007
- PERF-014
- PERF-018
- QA-025

### Root cause

The C API lacks an explicit version/error channel and trusts caller lengths. Some thread setup/object packing overhead exists.

At the same time, the reviews agree that the native kernel is not the dominant bottleneck for current product Historical VaR.

### Required direction

- ABI version;
- status/error return;
- explicit shape/length validation;
- direct contiguous NumPy buffer path if native remains useful;
- avoid per-call thread creation for tiny workloads;
- only extend the native kernel after the per-factor historical model is defined and profiling shows value.

### Decision

**Do not move VaR business logic or QuantLib pricing into C++ merely to chase speed.**

---

## RF-018 — Frontend contracts and dependency reproducibility need hardening

Priority: **P2**  
Risk types: MAINTAINABILITY, SUPPLY_CHAIN, UI_CORRECTNESS  
Confidence: HIGH

Source findings:

- ARCH-017
- ARCH-021
- SEC-009
- QA-008

### Root cause

The frontend is untyped JavaScript, API request shaping is manual, and runtime dependencies use broad/latest declarations. Unit conversions can be correct in helpers but insufficiently protected at the click/request boundary.

### Required direction

- pin runtime/build dependencies consistent with lockfile;
- use deterministic `npm ci` for builds;
- add generated or centralized API contracts after API schemas stabilize;
- add request-body assertions for percent/bp conversions;
- consider TypeScript only if it materially improves maintained API contracts—do not migrate solely for appearance.

---

## RF-019 — AI routing is intentionally deterministic but remains a narrow prototype

Priority: **P2**  
Risk types: MAINTAINABILITY, AI_GUARDRAILS  
Confidence: HIGH

Source findings:

- ARCH-018
- Security review AI assessment
- QA AI assessment

### Root cause

Natural-language routing is currently substring/keyword based over a small deterministic tool set. This is safe relative to allowing an LLM to calculate risk, but it is not yet a mature intent/tool contract layer.

### Required direction

Do not work on this during R0 unless a remediation change breaks the interface.

When the deterministic risk APIs stabilize:

- explicit tool schemas;
- robust intent parsing;
- parameter validation;
- tool allowlisting;
- no generated financial arithmetic;
- evaluation cases for ambiguity and injection.

### Decision

AI remains **after** deterministic risk remediation.

---

## RF-020 — Documentation and roadmap status overstate completion

Priority: **P2**  
Risk types: DOCUMENTATION, PROCESS  
Confidence: HIGH  
Status: **IN PROGRESS** (R0 row in ROADMAP; known_limitations aligned; agent TASKS.md pointers removed. Residual: stale suite counts in old ROADMAP baselines. Current gate is the recorded Phase A baseline, not a live matrix.)

Source findings:

- ARCH-023
- ARCH-027
- QA-019

### Root cause

Roadmap/agent documentation can mark workstreams complete while review findings demonstrate material residual architecture debt. Some agent instructions still refer to missing/obsolete task files.

### Required direction

- Make `FINDINGS.md` the authoritative review backlog.
- Add Milestone R0 before feature milestones.
- Keep completed historical milestones intact, but explicitly record residual remediation.
- Update benchmark/test counts from reproducible current runs.
- Treat `docs/known_limitations.md` as the truth source for product claims until limitations are closed.

---

# Priority Backlog

## P0 — Must close before feature development

| ID | Root finding | Primary owner |
|---|---|---|
| RF-001 | Trade vs market ownership | Architecture / Quant |
| RF-002 | QuantLib process state and as-of | Quant / Architecture |
| RF-003 | Exact VaR/ES statistical goldens | Quant QA |
| RF-004 | Unified sensitivity/P&L units and market path | Quant |
| RF-005 | Per-factor historical risk model | Quant / Market Data |
| RF-006 | One-pass scenario/snapshot transformation | Market Data / Performance |
| RF-007 | Full-revaluation execution architecture | Quant / Performance |
| RF-008 | Hierarchy from reusable trade-level P&Ls | Risk / Performance |
| RF-009 | Risk-run dataset/input reproducibility | Backend / Risk |

## P1 — Production-quality blockers

| ID | Root finding | Primary owner |
|---|---|---|
| RF-010 | Domain/API/application separation | Architecture / Backend |
| RF-011 | One scenario model + typed market structures | Architecture / Quant |
| RF-012 | Instrument capability registry / no silent fallback | Quant / Architecture |
| RF-013 | Canonical persisted IDs and safe portfolio ownership | Backend |
| RF-014 | Deployment/auth/input/workload boundaries | Security / Backend |
| RF-015 | Dashboard/risk-run execution split | Backend / Frontend / Performance |
| RF-016 | Production-relevant CI/test gates | QA |

## P2 — Hardening / deferred

| ID | Root finding | Primary owner |
|---|---|---|
| RF-017 | Native ABI and targeted kernel hardening | C++ |
| RF-018 | Frontend contracts/dependency reproducibility | Frontend |
| RF-019 | AI routing maturity | AI / Backend |
| RF-020 | Documentation/roadmap truth | Documentation |

---

# Dependency-Aware Fix Order

1. **RF-003** — build exact VaR/ES safety net before refactoring.
2. **RF-004** — pin unit conventions and snapshot-aware approximate risk.
3. **RF-001** — separate trade economics from market state.
4. **RF-002** — bind QuantLib state to valuation context/as-of.
5. **RF-011** — type market structures and converge scenario models enough to support the next steps.
6. **RF-012** — unify instrument capability dispatch and forbid silent production fallback.
7. **RF-005** — replace macro broadcast history with per-factor observations.
8. **RF-006** — one-pass snapshot/scenario application.
9. **RF-007** — rework full-revaluation execution after market/scenario semantics are stable.
10. **RF-008** — aggregate hierarchy from reusable trade-level P&Ls.
11. **RF-009** — make worker/API run inputs identical.
12. **RF-010** — split transport/domain/application contracts around the now-stable core.
13. **RF-013** — make persistence IDs canonical and protect portfolio identity.
14. **RF-015** — move heavy work behind `RiskRun` and collapse dashboard fan-out.
15. **RF-014** — finish deployment boundary, workload, auth, and input controls.
16. **RF-016** — make all repaired paths hard CI gates.
17. **RF-017 / RF-018 / RF-020** — hardening.
18. **RF-019** — AI expansion only after deterministic tools stabilize.

---

# Quick Wins

These are useful early changes but must not replace structural remediation.

- Add exact tiny VaR/ES golden distributions. `RF-003`
- Add historical approximate P&L unit goldens. `RF-004`
- Make QuantLib mandatory in a full CI job. `RF-016`
- Pin frontend dependency versions and use `npm ci`. `RF-018`
- Bind Compose API/frontend to loopback and stop publishing Postgres by default. `RF-014`
- Add finite-number validation and request-size/workload caps. `RF-014`
- Remove/disable the valuation LRU for unique full-revaluation shock workloads when benchmarking proves it is slower. `RF-007`
- Add native ABI length validation. `RF-017`

---

# Explicit Non-Priorities

Do not use the review as justification to add:

- microservices;
- Kubernetes;
- Kafka/event buses;
- an elaborate distributed queue;
- a second C++ business layer;
- custom numerical libraries that duplicate QuantLib/NumPy;
- exotic Greeks before core factor risk is trustworthy;
- more AI features before deterministic risk contracts stabilize.

---

# Release / Development Gate

Net-new product feature development should remain paused until **Milestone R0** is complete.

At minimum, R0 requires:

- all P0 findings CLOSED;
- all P1 findings CLOSED or explicitly accepted with written rationale;
- full backend test suite passing;
- QuantLib hard-gate suite passing;
- frontend tests/build passing;
- native parity tests passing;
- PostgreSQL/risk-run integration passing;
- critical E2E workflow passing;
- benchmark results recorded for scenario application, full revaluation, and hierarchy;
- README/known limitations/roadmap aligned with reality.

P2 work may be deferred only when it is genuinely unrelated to the repaired path and does not undermine reproducibility or security.

See `REMEDIATION_MILESTONE.md` for the executable work plan.
