# RiskForge Consolidated Engineering Findings

Date: 2026-09-09  
Status: leftover wave IN PROGRESS (2026-09-09) — P0/P1 code CLOSED; user rejected “accepted residual” as done. Remaining MET work: RF-014 shared ACLs/TLS/secrets, QA-024 QuantLib demo range, RF-016 labeled-runner SLA (needs a runner), RF-017 ABI close-as-MET or remaining kernel, RF-018 contracts, RF-019 tool evals.  

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

**Milestone R0 leftover wave is IN PROGRESS** (2026-09-09). “Accepted residual” is not done.

P0/P1 code paths stay CLOSED except RF-014 shared ACLs/TLS/secrets (reopened). QA-024 QuantLib demo range, RF-017 ABI close, RF-018 frontend contracts, and RF-019 tool evals are **IN PROGRESS**. RF-016 labeled-runner SLA still needs a self-hosted runner (cannot fake ubuntu-latest floors).

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
10. **RF-013 — Persistence/API identity** — **CLOSED** (R0.8.8); named residuals: seed `save`, live debug calculate POST, client id on first create

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
Status: **CLOSED** (2026-09-04). Phase B APPROVE (`reviews/r0.2-strip-dto-marks-independent-review.md`): `*Position` DTOs are economics-only (`extra='forbid'`); Builtin/QuantLib price from terms + `MarketSnapshot` via `SimpleNamespace` working views; production `value` / `value_portfolio` / `shocked_value` require an explicit snapshot; `LegacyDemoPricingAdapter` removed; ad-hoc `demo_market_snapshot` / `DemoSampleMarksSnapshotAdapter` raise `SampleMarksRemovedError`; canned demo marks live only in `_DEMO_*` snapshots. Full suite 1208 passed / 4 skipped. Residual: bond/swap `duration` remains a derived Position shortcut (not a live mark); `PortfolioService` defaults to the demo market provider unless `market_data=` is injected.

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
Status: **CLOSED** (2026-09-04). R0.3.2–R0.3.5 process-owned session + Compose worker partition APPROVE. R0.3.1 typed `as_of` APPROVE: accepted type is `date | Literal["current", "t0"]`, not `date` only. ISO/`date` drives QuantLib `Settings.evaluationDate` and the valuation cache key; labels stay labels and are never rewritten to `date.today()`. Residual: omitted/`"current"`/`"t0"` still price at the engine constructor date (`date.today()` on the factory path). That is documented label semantics, not an open process-partition item. Do not reopen for the R0.3.5 detector-substring pin.

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
- typed `MarketSnapshot.as_of: date | Literal["current", "t0"]`;
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

Evidence (R0.3.1–R0.3.5 CLOSED):

- Module-level `_QL_PROCESS_LOCK` is shared by every `QuantLibPricingEngine` instance (`backend/app/pricing/quantlib.py`).
- `tests/test_quantlib_process_state.py` requires overlapping sessions to serialize; restoring per-instance locks fails Acc 5.
- `MarketSnapshot.as_of` is `date | Literal["current", "t0"]`. ISO/`date` drives `Settings.evaluationDate` and `market_cache_key` (`|as_of:YYYY-MM-DD`); labels stay labels.
- Outermost session clears `IndexManager` histories so swap fixings do not leak.
- Process partition is the Compose `worker` OS process; in-process QuantLib stays serialized. Detector tests are not a closed contract against a later QL thread pool.
- Residual (not a reopen): factory/`"current"` still prices at constructor `date.today()`. `scenario_memo_key` still ignores `as_of` when `id` and marks match.

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
Status: **CLOSED** (2026-09-09). Independent review **APPROVE** (`reviews/r0.4.2-d-formal-post-wire-independent-review.md`). Acceptance evidence satisfied: R0.1.3 unit goldens (wrong DV01/vega/bp/% scales fail); R0.4.3-A/B `shock_units` + reverse-stress heuristic removed; R0.4.2-A expand/collapse parity; R0.4.2-B StressEngine native formal Scenario; R0.4.2-C formal list wire; **R0.4.2-D** — UI primary POST path is formal ScenarioWire (`/formal/evaluate/custom`, `/formal/custom`, `/formal/compare`); display %→fraction and bp→decimal through formal shock amounts. Snapshot-aware approximate paths from prior R0.4 slices. Residual deprecated StressScenario POST routes kept for back-compat only (not live UI) — tracked under RF-011. Dual vol conventions remain explicit conversions. Review Important: backend UI-style parity expands via `stress_to_wire` not frontend `scenarioPayload` (demo probe still matched); deferred test hardening.

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

Status: **CLOSED** (2026-09-09). Production `build_historical_risk_engine()` wires seeded `HistoricalFactorPanel` (`create_synthetic_factor_panel`) with independent per-name/per-tenor columns (NVDA≠SPY, USD 2Y≠10Y). Bare `HistoricalRiskEngine()` / `factor_panel=None` and labeled File/Synthetic datasets remain explicit `four_macro_demo` fixtures. Evidence: `reviews/r0.5.3-default-panel-independent-review.md` APPROVE; factory tests. **R0.5.5 residual addressed (2026-09-09):** `VaRAnalytics` / `ESContributionAnalytics` accept shared `factor_panel` and attribute via panel histories (fail-closed on missing required factors); four-macro path unchanged when `factor_panel=None`. Evidence: `reviews/r0.5.5-panel-contributions-report.md`. Finding stays **CLOSED** (not reopened).

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
Status: **CLOSED** (2026-09-09). R0.4.4 — one-pass `MarketSnapshot.apply` (stage all shocks, single `model_copy` / nested freeze). R0.4.5 — StressEngine / attribution scenario-once-price-many. R0.4.6 acceptance residual — structural proofs: multi-factor apply `model_copy` == 1 and freeze ∈ [1,2] for K≥5 (not O(K)); `StressEngine.run` / `evaluate` `apply_scenario` count == S for P×S (not P×S); contribution sum↔portfolio P&L + interaction residual already pinned in `test_scenario_attribution.py`. Evidence: `tests/test_market_snapshot.py::test_apply_freezes_once_not_per_factor`, `tests/test_stress.py` once-per-scenario + P×S counters, `tests/test_scenario_attribution.py` reconcile helpers / `test_single_factor_interaction_near_zero` / `test_risk_factor_contributions_reconcile_with_interaction`. Report: `reviews/r0.4.6-rf006-acceptance-report.md`. Wall-clock N×S pricing remains RF-007.

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

- exact parity with existing scenario semantics; **met** (R0.4.4 mark/id parity + stress numerical parity)
- one freeze/copy per scenario rather than per factor; **met** (`test_apply_freezes_once_not_per_factor`: `model_copy == 1`, freeze ∈ [1,2] for K≥5)
- benchmark factor count × scenario count; **met via structural counters** (P×S → S applies in `test_stress.py`; wall-clock N×S pricing is RF-007)
- zero shock and unrelated-factor invariants remain exact; **met** (existing snapshot/stress suites)
- contribution tests prove a factor cannot disappear into an unexplained `interaction` bucket; **met** (`test_scenario_attribution.py`: reconcile + `test_single_factor_interaction_near_zero`)

---

## RF-007 — Full revaluation and contribution paths reconstruct N×S QuantLib work

Status: **CLOSED** (2026-09-09). QA close gate (`reviews/r0.6.9-rf007-close-gate-report.md`); independent review **APPROVE** (`reviews/sdd-briefs/task-8-rf007-close-gate-review.md`). R0.6.1–R0.6.6 APPROVE (architecture: `reviews/sdd-briefs/task-1-r0.6.3-review.md`, `task-2-r0.6.4-review.md`, `task-3-r0.6.6-review.md`, `task-4-r0.6.5-review.md`): stream shocked snapshots; one-pass scenario market (RF-006); QuantLib scalar-option reuse via live `SimpleQuote` handles; unique-shock valuation LRU bypass; factor contributions reuse joint P&L + O(N) Δ-Γ (not O(N×S×F) extra books); HEAVY `FULL_REVALUATION` is a RiskRun / Compose `worker` OS-process job (option B; no in-process QuantLib threads). Interactive default remains `DELTA_GAMMA`. R0.6.8 reconstruction **10×50 European option** book (spot/vol/rate/div live; Task 7 APPROVE `reviews/sdd-briefs/task-7-rf007-reconstruction-benches-review.md`) plus isolated RSS per impl and nightly **N=100×50**. Close-matrix: N×S **PARTIAL** (PR 10×50 + 1×120; N=100 **MET** in nightly; N=1k **UNMET**, not a fake SLA); wall **MET** at 10×50; peak RSS **PARTIAL** (isolated subprocess per impl; still process-lifetime `ru_maxrss` within that child — measurement limit, not MET); scenarios/sec **MET** at 10×50; builtin vs QuantLib **MET** on the reconstruction option book (checksums per engine `3148a41a…` / `0594ecd6…`; P&L gap within option-match `rel=2e-3`); warm vs cold **MET** at 10×50; identity **MET** (cash-equity `6602fa69…` 1×120 and `a28cf4ee…` 10×50 unchanged). No SLA. **P1 residuals (not blocking close):** intra-run scenario-block multiprocessing (option A); peak RSS `ru_maxrss` measurement limit; N=1k / S=750/1k unrecorded.

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

Close-gate (2026-09-09, R0.6.9): required direction 6 MET, 1 PARTIAL (option B job process, not intra-run chunks — **P1**). Numerical identity **MET**. R0.6.8 reconstruction 10×50 European options: wall **MET**, scenarios/sec **MET**, warm vs cold **MET**, builtin vs QuantLib **MET** (per-engine checksums; P&L gap within `rel=2e-3`); N×S **PARTIAL** (N=100 **MET** in nightly; N=1k **UNMET**; default PR still 10×50); peak RSS **PARTIAL** (isolated subprocess per impl; still process-lifetime `ru_maxrss` within that child — not MET). **CLOSE.** Independent review pending.

---

## RF-008 — Hierarchy recomputes full risk independently at every node

Status: **CLOSED** (2026-09-09). Independent review **APPROVE** (`reviews/r0.7.6-hierarchy-artifact-stress-independent-review.md`). R0.7.1–R0.7.3, R0.7.5, R0.7.6: default and live hierarchy value each position once, fill `DEFAULT_SCENARIOS` stress via scenario-once/price-many, aggregate PV/Greeks/stress/historical vectors; node VaR/ES = VaR/ES of the summed historical vector. Acceptance evidence met (additive reconcile, VaR(sum), stable IDs, no independent full risk per trade). **P1 residuals (not blocking close):** node `limits == []` (concentration/key-rate still need artifact-aware LimitEngine); R0.7.4 lazy drilldown payload trimming.

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

Status: **CLOSED** (2026-09-08). R0.8.1–R0.8.5 APPROVE (`reviews/r0.8.5-postgres-same-spec-independent-review.md`). Per-`run_type` schemas (`extra='forbid'`); `historical_dataset_id` rebinds via shared factories or 400 (never silently ignored); CSV identity is path-derived (`file:<abspath>`). Same RiskRun spec yields exact interactive vs worker payloads for `summary`/`var` (synthetic, SQLite); execute prefers persisted first-class columns over a tampered request blob. Optional Postgres lifecycle skips without DSN (nightly-safe). Residual Minor: `methodology` column does not override a conflicting request blob (dataset/`as_of`/config do).

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
Status: **CLOSED** (2026-09-09). Independent review **APPROVE** (`reviews/sdd-briefs/task-18-rf010-composition-review.md`). R0.9.1 HTTP schemas in `app.api.schemas`; R0.9.2 `RiskEngine.calculate` returns `RiskSummary`; R0.9.3 `PortfolioService` constructed in FastAPI lifespan on `app.state`, shared with `RiskRunWorker`, HTTP Depends fail-closed 503 when missing. No DI container. **Named residual (not blocking close):** dual-use `AttributionRequest` / `RiskChangeAttributionRequest` / `WhatIfRequest` remain in domain.

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
Status: **CLOSED** (2026-09-09). Independent review of R0.4.2-G **APPROVE** (`reviews/sdd-briefs/task-20-rf011-historical-reverse-review.md`); R0.4.2-F **APPROVE** (`reviews/sdd-briefs/task-19-rf011-canonical-store-review.md`). R0.4.2-G — historical replay generates/applies canonical `Scenario` with typed `FactorShock` (live-snapshot aggregate expansion; rate bp→decimal only via `shock_units`); `MarketScenario` / `FactorChange` remain adapters like deprecated `StressScenario`. Reverse-stress `ReverseStressResult` carries the applied `Scenario` (zero / bound / converged); `required_shock` wire units unchanged; search remains one-factor-family magnitudes. Prior slices: R0.4.1-A/B/C typed market views + explicit currency; R0.4.2-C/D formal ScenarioWire HTTP; R0.4.2-E engine-facing Scenario-only; R0.4.2-F DEFAULT/THREAT templates + persistence store `Scenario`. **Named residuals (not blocking close):** deprecated StressScenario HTTP POSTs; `MarketScenario` adapter; reverse search is still one-factor-family; flat dict `MarketSnapshot` storage (typed views wrap it; no nested Pydantic rewrite). Evidence: `reviews/r0.4.2-g-historical-reverse-scenario-report.md`, `reviews/sdd-briefs/task-20-rf011-historical-reverse-report.md`.

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
Status: **CLOSED** (2026-09-09). Independent review **APPROVE** (`reviews/sdd-briefs/task-24-rf012-family-dispatch-review.md`; instance-handler fix `3857892`). R0.5.8: Builtin and QuantLib `value()` look up a frozen `terms.type` → handler **name** map after `get_capability`, then `getattr(self, name)` (existing `_bond` / `_option` methods remain; the isinstance ladder is gone). Snapshot marks live in one module (`app.pricing.snapshot_overlay`); both engines’ working views call the same `snapshot_marks_from_terms`. `position_label` fail-closes via `get_capability` and is family-keyed (cap/floor/swaption labels stay `position.id`). Adding a production family is domain terms + one registry row + overlay handler + Builtin handler + QuantLib handler + tests — not a second overlay copy, not a second `isinstance` ladder in `factors.py` / `cache.py` / `historical.py`. QuantLib still does not call Builtin. Not a plugin framework. Evidence: `reviews/r0.5.8-rf012-family-dispatch-report.md`. **Named residual (not blocking close):** discriminated Position/Terms unions in `domain/` (the type, not a dispatch ladder).

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

Status: **CLOSED** (2026-09-09). Independent review of R0.8.8 **APPROVE** (`reviews/sdd-briefs/task-23-rf013-portfolio-version-review.md`). R0.8.8: `Portfolio.version` is server-owned (create starts at 1; `update` compare-and-swap increments or fails closed; Alembic `004_portfolio_version`). `RiskRun.portfolio_version` is copied from the **stored** book at submit (attach-stored path). Overwrite `global-macro` **MET** (R0.8.6); reproduce from IDs **MET** (R0.8.5); Postgres **MET** (R0.8.5; skipped without DSN); cell 4 **MET** (R0.8.7). Version is a real stored/checked identity, not a dead column. Report: `reviews/r0.8.8-portfolio-version-report.md`. **Named residuals (not blocking close):** leftover seed `save` upsert (insert=1, overwrite bumps, no CAS); live debug calculate still POSTs a full book; object ACLs = RF-014; client-chosen id on first create-if-absent. Not a historical archive of every book revision.

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

- a request cannot overwrite `global-macro` merely by supplying that ID — **MET** (`tests/test_portfolio_identity.py` HTTP + worker pins; R0.8.3 attach-stored);
- a persisted risk run can be reproduced from IDs — **MET** (R0.8.5 `tests/test_same_spec_parity.py`; RF-009 CLOSED);
- PostgreSQL path has real pytest/integration coverage — **MET** (R0.8.5 `tests/test_postgres_risk_run_lifecycle.py`; not duplicated here);
- large derived payloads are not blindly duplicated as unconstrained JSON where a structured/reference model is better — **MET** (R0.8.7: `parse_result_payload` gates `add_result` / `complete` on a known `result_type` → existing domain/API result model, `extra='forbid'`; unknown type and extra keys fail closed. Physical JSON column remains; unconstrained `dict[str, Any]` writes are rejected. R0.8.4 typed **request** bodies are not this cell);
- `portfolio_id` / `portfolio_version` is a real stored identity — **MET** (R0.8.8: create stores version 1 ignoring client; `update` CAS; RiskRun header copies stored version at submit; SQL column pins in `tests/test_portfolio_identity.py`).

---

## RF-014 — API/deployment boundary lacks production workload, input, and access controls

Priority: **P1**  
Risk types: SECURITY, AVAILABILITY, OPERABILITY  
Confidence: HIGH  
Status: **IN PROGRESS** (2026-09-09). Local-demo required direction remains MET. Shared-profile **object ACLs**, **TLS/reverse-proxy**, and **secret management** were papered as accepted residuals — reopened to MET them. Not production OIDC.

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

The repository clearly differentiates (`BUILD_NOTES.md` “Local vs shared vs not production-like”):

```text
local demo
shared/internal deployment
production-like deployment
```

Missing auth is not called a vulnerability for strict loopback use, but public exposure is blocked by configuration and documentation.

Close-gate scores (2026-09-09, `reviews/r0.11.7-rf014-close-gate-report.md`): local-demo loopback / finite numbers / payload caps / sanitization **MET**; shared-token gate **MET** for authentication only. Object ACLs / TLS / secrets **UNMET** — accepted R0 residuals, not MET. HTTP enqueue queue-depth and Compose demo DB password remain named leftovers, not MET.

---

## RF-015 — Interactive UI fans out redundant synchronous risk calculations

Status: **CLOSED** (2026-09-09). Independent review **APPROVE** (`reviews/r0.10.4-heavy-ui-riskrun-fallback-independent-review.md`). R0.10.1–R0.10.4: HEAVY routes refuse when the gate is on; `run_type=dashboard` RiskRun returns the coherent batch; Compose `loadDashboard()` and all other live risk-terminal HEAVY UI POSTs (stress evaluate / reverse / reverse-multi / compare / query / attribution / attribution-demo / change-attribution / ES / VaR-compare) fall back via shared `postHeavyOrRiskRun` → typed RiskRun poll on refuse (`details.use=/risk/runs`). Gate-off stays direct sync POST. INTERACTIVE scenario GETs, `/limits/drilldown`, LINEAR summary, and `/factors` stay sync (not converted).

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
Status: **CLOSED** (2026-09-09). Independent review **APPROVE** (`reviews/sdd-briefs/task-26-rf016-close-gate-review.md`). QA close gate (`reviews/r0.12.7-rf016-close-gate-report.md`). R0.1.6 QuantLib hard-gate; R0.12.1–R0.12.5 APPROVE; nightly QuantLib E2E + hierarchy identity APPROVE. Required PR-FAST / PR-FULL (including QuantLib hard-gate) / NIGHTLY Postgres two-worker / larger full-reval / QuantLib E2E are **MET**. Labeled-runner SLA-K1/K2 is an **accepted residual** (not MET): no labeled runner; SLA-K1/K2 not CI-enforced (`actions/runners total_count=0`; do not run `check_m6_sla.py` on `ubuntu-latest`). QA-024 demo-artifact range check remains a leftover residual (not MET). Not a production SLA rollout.

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

Close-gate scoring (R0.12.7): PR-FAST **MET**; PR-FULL QuantLib hard-gate / native compile-parity / frontend / semantic API / Playwright **MET**. NIGHTLY Postgres two-worker **MET**; larger full-reval samples **MET** (sample + N=100 identity, not host SLA); QuantLib E2E **MET** (nightly only). Labeled-runner SLA-K1/K2 (`check_m6_sla.py`) **PARTIAL** / **accepted residual** — harness and reference-host evidence exist; no labeled runner is registered; SLA-K1/K2 not CI-enforced; do not invent `ubuntu-latest` floors. QA-024 demo-artifact range check remains a leftover residual (not MET).

### Acceptance evidence

A broken QuantLib installation cannot produce a green "full" CI run. — **MET** (R0.1.6 `backend-quantlib-hard-gate` is a required `pr-full` need; `RISKFORGE_REQUIRE_QUANTLIB`; no `requirements-no-ql` fallback; no `continue-on-error`). Labeled-runner SLA-K1/K2 and QA-024 range remain named residuals, not MET.

---

## RF-017 — Native kernel boundary needs ABI hardening, but more C++ is not the current priority

Priority: **P2**  
Risk types: PERFORMANCE, MAINTAINABILITY, NATIVE_SAFETY  
Confidence: HIGH  
Status: **IN PROGRESS** (2026-09-09). ABI work landed; leftover wave will CLOSE only when ABI/validation/contiguous buffers are scored MET (not “deferred because we refused C++ VaR”).

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
Status: **IN PROGRESS** (2026-09-09). `npm ci` and version pins exist; leftover is request-boundary percent/bp assertions and a centralized OpenAPI contract. Not a TypeScript rewrite.

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
Status: **IN PROGRESS** (2026-09-09). Deterministic APIs are stable. Leftover: JSON-schema tool allowlist, injection/ambiguity evals. LLM still must not invent numbers.

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
Status: **IN PROGRESS** (2026-09-09). Prior COMPLETE stamp was dishonest while leftovers were unmet. FINDINGS remains the backlog.

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

**Milestone R0 leftover wave IN PROGRESS** (2026-09-09). Net-new feature development stays paused until RF-014 shared ACLs/TLS/secrets, QA-024 range, RF-017/018/019 are MET. Labeled-runner SLA still needs a self-hosted runner.

R0 required, and now records:

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
