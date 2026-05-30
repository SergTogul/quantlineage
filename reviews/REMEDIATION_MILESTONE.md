# Milestone R0 — Core Remediation & Trustworthiness

Status: **IN PROGRESS**

Current phase: **B — Market / pricing contracts (R0.2)**  
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

## R0.2 slice status (Phase B)

| Slice | Status | Evidence |
|---|---|---|
| R0.2-A explicit snapshot path and validated demo bridge | COMPLETE | Independent re-review **APPROVE** (`reviews/r0.2-a-rereview.md`). |
| R0.2 equity future/option spots | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-equity-spots-independent-review.md`). |
| R0.2 equity option vol | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-equity-vol-independent-review.md`). |
| R0.2 what-if snapshot threading | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-what-if-snapshot-independent-review.md`). |
| R0.2 equity future/option rates and dividend yields | COMPLETE | Independent re-review **APPROVE** (`reviews/r0.2-equity-rates-divs-rereview.md`). |
| R0.2 dashboard/compare/reverse/drilldown root snapshot | COMPLETE | Independent re-review **APPROVE** (`reviews/r0.2-demo-dashboard-snapshot-rereview.md`). |
| R0.2 FX forward/option spots, vol, domestic/foreign rates | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-fx-independent-review.md`). |
| R0.2 VaR/ES/full-reval require explicit market | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-omit-market-independent-review.md`). |
| R0.2 bond/swap/IR fail-closed | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-rates-ir-independent-review.md`). |
| R0.2 hierarchy/stress/reverse require explicit market | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-hierarchy-stress-market-independent-review.md`). |
| R0.2.4 cache identity (all families) | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-terms-cache-independent-review.md`). |
| R0.2 decompose require explicit market | COMPLETE | Independent review **APPROVE** (`reviews/r0.2-decompose-market-independent-review.md`). |
| R0.2.1 typed InstrumentTerms | COMPLETE | Independent review **APPROVE**. Cache wiring APPROVE (`reviews/r0.2.1-cache-terms-independent-review.md`); `value()` still takes Position. |
| Remaining DTO mark removal | COMPLETE | Phase B APPROVE 2026-09-04 — marks stripped; RF-001 CLOSED. |

RF-001 is **CLOSED**. Production pricing requires an explicit `MarketSnapshot`; Position DTOs no longer carry live marks.

## R0.2.1 Introduce contractual trade/instrument terms — COMPLETE (2026-09-04)

`backend/app/domain/instrument_terms.py`: `terms_from_position` is an allow-list economics projection for all ten `trade_cache_key` families. Unknown types raise `TypeError`. `*Position` DTOs still carry marks. Cache and pricing `value()` are not wired. RF-001 stays open.

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

## R0.3.1 Typed as-of date — COMPLETE (2026-09-04)

Accepted type is `date | Literal["current", "t0"]`, not `date` only. ISO/`date` drives QuantLib evaluation date and the valuation cache key; labels stay labels and are never rewritten to `date.today()`. Persistence/API wire via `as_of_wire`. RF-002 CLOSED. Residual: factory/`"current"` still prices at constructor `date.today()`.

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

R0.3.5 status: COMPLETE (independent review APPROVE, `reviews/r0.3.5-independent-review.md`). Parallel full reval is the Compose `worker` process. R0.3.1 typed `as_of` COMPLETE; RF-002 CLOSED.

---

# R0.4 — Converge Market and Scenario Contracts

Related findings:

- RF-004
- RF-006
- RF-011

## R0.4.1 Typed market structures

R0.4.1-A COMPLETE (2026-09-08): typed sub-market views
(`MarketSnapshot.equity` / `.rates_market` / `.vol` / `.fx` → `app.market.markets`)
documented and tested as canonical inspection APIs; nested maps remain
MappingProxy-frozen; `curves.py` bp→decimal shifts go through
`bps_to_decimal_rate`. Flat dict storage on MarketSnapshot retained.
RF-004 / RF-011 stay IN PROGRESS.

Replace nested raw dictionaries where practical with typed domain models for:

- yield curves;
- vol surfaces;
- FX market;
- equity market.

## R0.4.2 One canonical Scenario model

R0.4.2-A COMPLETE (2026-09-09): scenario expand/collapse converts StressScenario bp fields only via `shock_units`; stress↔formal parity golden pins exact marks/`content_hash`. StressScenario wire adapters retained.

R0.4.2-B COMPLETE (2026-09-09): Independent review **APPROVE** (`reviews/r0.4.2-b-formal-scenario-engine-independent-review.md`). Engine-facing `StressEngine` / PortfolioService / attribution apply accept formal `Scenario | StressScenario` (`ScenarioLike`); formal HTTP `/risk/stress/formal/*` lifts wire → `Scenario` → engine apply (no `scenario_to_stress` on that path). Legacy `/risk/stress/*` StressScenario wire retained. Remaining for full R0.4.2 converge (not this slice): make formal HTTP the default client path, retire dual list endpoints (`/scenarios` vs `/scenarios/formal`), and any remaining what-if / compare callers that still prefer StressScenario-only wire — do not close RF-004.

R0.4.2-C COMPLETE (2026-09-09): Independent review **APPROVE** (`reviews/r0.4.2-c-formal-default-wire-independent-review.md`). `GET /risk/stress/scenarios` returns formal `ScenarioWire` (breaking vs legacy StressScenario dicts); `GET .../scenarios/formal` kept as identical JSON alias. No `/scenarios/legacy` path. Residual dual StressScenario POST bodies on custom/evaluate/compare (frontend `scenarioPayload`). RF-004 / RF-011 stay IN PROGRESS.

R0.4.2-D COMPLETE (2026-09-09): Independent review **APPROVE** (`reviews/r0.4.2-d-formal-post-wire-independent-review.md`). Primary UI POST path uses formal ScenarioWire (`/formal/evaluate/custom`, `/formal/custom`, `/formal/compare`); frontend `scenarioPayload` / `compareHedge` no longer call legacy StressScenario POSTs. Legacy custom/evaluate/compare routes retained as **deprecated** back-compat. **RF-004 CLOSED**; RF-011 stays IN PROGRESS (typed nesting + deprecated dual POST residual). Review Important deferred: parity tests use `stress_to_wire` expansion, not frontend builders.

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

R0.4.2-A COMPLETE (2026-09-09): engine-facing scenario expand/collapse
(`scenario_model` / `scenarios`) converts StressScenario bp fields through
`shock_units` (`bps_to_decimal_rate` / `decimal_rate_to_bps`); stress↔formal
parity golden pins identical `content_hash` / marks. StressScenario wire retained.

R0.4.2-B COMPLETE (2026-09-09): Independent review **APPROVE** (`reviews/r0.4.2-b-formal-scenario-engine-independent-review.md`). `StressEngine.run` /
`evaluate` / `ScenarioComparisonEngine.compare` and PortfolioService stress
entry points take `ScenarioLike`; formal custom/evaluate HTTP uses
`wires_to_scenarios` → native apply; attribution factor isolation applies
formal `Scenario` without collapse. Evidence: `reviews/r0.4.2-b-formal-scenario-engine-report.md`.

R0.4.2-C COMPLETE (2026-09-09): Independent review **APPROVE** (`reviews/r0.4.2-c-formal-default-wire-independent-review.md`). Formal ScenarioWire is the
default `GET /risk/stress/scenarios` list; `/scenarios/formal` is an identical
alias. Residual: StressScenario POST bodies on custom/evaluate/compare.
Evidence: `reviews/r0.4.2-c-formal-default-wire-report.md`.

R0.4.2-D COMPLETE (2026-09-09): Independent review **APPROVE** (`reviews/r0.4.2-d-formal-post-wire-independent-review.md`). Formal ScenarioWire is the primary
UI stress POST path (`scenarioPayload` → `/formal/evaluate/custom`; hedge →
`/formal/compare`; thin formal compare route added). Legacy StressScenario POST
routes deprecated but retained. **RF-004 CLOSED**; RF-011 remains IN PROGRESS.
Evidence: `reviews/r0.4.2-d-formal-post-wire-report.md`.

## R0.4.3 Explicit shock units

R0.4.3-A COMPLETE (2026-09-09): `app.risk.shock_units` owns bp↔decimal and relative-vol→vol-points; approximate P&L and SensitivityEngine rate bumps convert through helpers. Dual vol conventions remain documented (FactorShock relative vs FD absolute).

R0.4.3-B COMPLETE (2026-09-09): remaining risk-layer conversion call sites wired; reverse-stress `from_wire_bound` magnitude heuristic removed (**breaking**: rates `max_shock` is always the relative-style bound). RF-004 stays open for R0.4.2+.

Every factor shock must have one unambiguous internal convention.

Examples:

- equity/FX relative move: decimal fraction
- rate move: choose one internal representation and document it
- vol shift: choose decimal-vol or vol-point internal representation and document it

No magnitude heuristic may decide units.

## R0.4.4 One-pass snapshot transformation — COMPLETE (2026-09-09)

`MarketSnapshot.apply` unfreezes nested maps once, stages all `(RiskFactor, amount)` shocks with bump semantics, then a single `model_copy` / nested freeze. `bump` is the one-factor API via `apply([(f, a)])`. Mark + bump-chain id parity vs sequential bump; structural O(1) freeze/copy test (R0.4.6: lower+upper band for K≥5).

## R0.4.5 Scenario once, price many — COMPLETE (2026-09-09)

`StressEngine.run` / `evaluate` and scenario attribution create one shocked
`MarketSnapshot` per scenario via `apply_scenario`, then revalue every position
with `PricingEngine.value` on that shared snapshot. Structural monkeypatch
asserts N positions × 1 scenario → one `apply_scenario` call; stress numerical
parity retained.

## R0.4.6 RF-006 acceptance residual — COMPLETE (2026-09-09)

Structural factor×scenario evidence (monkeypatch counters, not wall-clock):
multi-factor apply `model_copy` == 1 / freeze ∈ [1,2] for K≥5; `run` /
`evaluate` apply count == S for P×S; contribution sum↔P&L + interaction residual
cited from existing `test_scenario_attribution.py`. RF-006 **CLOSED**.
Report: `reviews/r0.4.6-rf006-acceptance-report.md`. N×S full-reval cost remains RF-007.

### Exit criteria

- semantic parity tests pass;
- structural once-per-scenario assert for StressEngine position loops;
- factor count no longer causes repeated whole-snapshot copy/refreeze per factor
  (R0.4.4);
- P×S apply count == S (R0.4.6);
- contribution reconciliation pinned (existing attribution suite / R0.4.6 cite).

---

# R0.5 — Complete the Factor Model

Related findings:

- RF-005
- RF-012

## R0.5.1 Instrument capability registry — COMPLETE (2026-09-04)

`backend/app/pricing/instrument_capabilities.py` is a static ten-family table (adapter name strings, required factor kinds, sensitivities, snapshot maps). Unknown families fail closed. Not wired into `value()`. RF-005 stays open for R0.5.3.

Create a coherent registry or adapter mechanism that defines for each instrument family:

- pricing adapter;
- required market factors;
- supported sensitivities;
- factor exposure mapping.

Do not create an elaborate plugin framework.

## R0.5.2 Remove silent production fallback — COMPLETE (2026-09-04)

`QuantLibPricingEngine.value` raises `TypeError` on an unhandled instrument. Builtin is not called from this path. RF-005 stays open for the four-macro history panel.

Unsupported product should fail explicitly.

## R0.5.3 Per-factor historical observations — COMPLETE (type + production default, 2026-09-08)

`HistoricalFactorPanel` is the typed date × `RiskFactor` contract. Opt-in `HistoricalRiskEngine(factor_panel=…)` applies independent name/tenor shocks. Production `build_historical_risk_engine()` wires `create_synthetic_factor_panel` (independent columns for the documented demo universe). Bare ctor / `factor_panel=None` and labeled datasets stay `four_macro_demo`. **RF-005 CLOSED** (2026-09-09); residual contribution-trace → R0.5.5.

Replace the four-macro-only history abstraction with a typed factor panel.

Conceptually:

```text
date
RiskFactor -> observation/change
```

Support per-name and per-tenor moves.

## R0.5.4 Preserve demo compatibility — COMPLETE (2026-09-04)

Demo and synthetic history expose `projection="four_macro_demo"` with `is_per_name_per_tenor_panel=False`. Observation arrays and VaR goldens unchanged. Production VaR uses the panel via the factory (R0.5.3); these datasets remain labeled fixtures.

The existing four-column synthetic dataset may remain as:

- a documented demo projection;
- a fixture;
- a compatibility loader.

It must not be presented as full multi-asset historical factor history.

## R0.5.5 Contribution semantics — COMPLETE (2026-09-09)

`VaRAnalytics` / `ESContributionAnalytics` share `factor_panel` from `HistoricalRiskEngine` (via `PortfolioService` hist kwargs). When set, position and factor contributions use panel per-name/per-tenor paths (`approximate_position_pnls_from_panel` / panel shocked snapshots / panel factor isolation); missing required factors fail closed. `factor_panel=None` keeps four-macro `dataset.factor_observations()`. RF-005 stays CLOSED; residual contribution-trace closed here. Report: `reviews/r0.5.5-panel-contributions-report.md`.

Ensure factor contributions are calculated against the factor-complete scenario representation.

Do not allow an omitted factor to disappear into `interaction` without a reconciliation signal.

## R0.5.6 Wire capability registry into remaining dispatch — COMPLETE (slice, 2026-09-09)

`get_capability` is consulted by QuantLib/Builtin `value()`, snapshot overlay (unknown families raise; empty-marks `return {}` removed), `trade_cache_key`, and `RiskFactorEngine.calculate_typed`. QuantLib still does not call Builtin. Goldens unchanged. **RF-012 stays IN PROGRESS:** parallel `isinstance` ladders remain; adding a family is not yet one registration plus tests. Report: `reviews/r0.5.6-rf012-capability-wire-report.md`.

### Exit criteria

Two equities and two rate tenors can move independently in one historical observation.

---

# R0.6 — Rebuild Full-Revaluation Execution Around Reuse

Related findings:

- RF-006
- RF-007 (**CLOSED** pending independent review; `reviews/r0.6.9-rf007-close-gate-report.md`)
- RF-015

## R0.6.1 Baseline benchmark first — COMPLETE (2026-09-04)

`benchmarks/run_full_reval_bench.py` + `backend/tests/test_full_reval_bench.py`. Identity remains **1 trade × 120 obs** builtin vs `full_revaluation_pnl_series`. `pnl_checksum` `6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f`; `wall_ms` recorded only. Not in PR-FULL. R0.6.7 extends the same harness with a PR-safe **10×50** cash-equity acceptance payload. R0.6.8 adds reconstruction-honest European options (checksums per engine) and nightly **N=100×50**. Close scores: wall / scenarios/sec / warm vs cold / identity **MET** at 10×50; builtin vs QuantLib **MET** on the option book; N×S **PARTIAL** (N=100 nightly; N=1k **UNMET**); peak RSS **PARTIAL** (isolated per impl; process-lifetime `ru_maxrss` within the child). R0.6.9 close gate: **CLOSED** pending independent review.

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

## R0.6.2 Stream/chunk shocked scenarios — COMPLETE (2026-09-04)

`iter_shocked_snapshots` / `iter_historical_shocked_snapshots` yield one snapshot; list helpers wrap them. Full-reval loops consume the iterator. RF-007 stays open (still N×S pricing).

## R0.6.3 Reuse QuantLib structures where safe — COMPLETE (2026-09-09)

Independent review **APPROVE** (`reviews/sdd-briefs/task-1-r0.6.3-review.md`).

`QuantLibPricingEngine` now caches contract terms, swap schedules, and scalar equity/FX option QuantLib structures keyed by contract inputs and evaluation date. Scalar option paths reuse `VanillaOption` / payoff / exercise / process structures while updating `SimpleQuote` handles for spot, rates, dividends/foreign rates, and vol on every snapshot. Attached vol surfaces and snapshot curve/key-rate structures are still rebuilt/relinked from the current `MarketSnapshot` so shocked market state cannot go stale. Evidence: `backend/tests/test_quantlib_reuse.py`; focused brief suite `179 passed`; report `reviews/r0.6.3-quantlib-reuse-report.md`.

Evaluate:

- relinkable quotes;
- relinkable handles;
- cached instrument terms/schedules;
- cached curve structure where scenario semantics allow.

Do not cache stale market state.

## R0.6.4 Remove anti-cache behavior — COMPLETE (2026-09-09)

Independent review **APPROVE** (`reviews/sdd-briefs/task-2-r0.6.4-review.md`).

Unique-shock / FULL_REVALUATION loops enter `bypass_valuation_lru` so `CachedPricingEngine` does not hash, look up, or store per unique shocked snapshot. Base-snapshot valuations still use the LRU. `shocked_value` bypasses the LRU because the shocked market is unique by construction. Numerical identity vs inner/cold path at abs `1e-12`. Curve-construction cache stays enabled (equity/FX/vol bumps can hit when rate marks are unchanged). Evidence: `backend/tests/test_pricing_anti_cache.py`; brief focused suite `53 passed`; report `reviews/r0.6.4-anti-cache-report.md`.

If the valuation LRU is slower for unique shocked markets, disable it for that execution class or redesign the caching level.

## R0.6.5 Process-level scenario parallelism — COMPLETE (2026-09-09)

Independent review **APPROVE** (`reviews/sdd-briefs/task-4-r0.6.5-review.md`). Choice **B**.

Partition independent scenario blocks across worker processes when profiling shows value.

Option B: HEAVY full-reval already runs out-of-request-thread via RiskRun (`RF-015` CLOSED). Compose `backend` sets `RISKFORGE_EXTERNAL_WORKER=1` so HTTP enqueues; Compose `worker` (`python -m app.worker`) is the OS-process QuantLib partition. `POST /risk/summary?methodology=FULL_REVALUATION` and `POST /risk/var` refuse inline when the gate is on (`details.use=/risk/runs`). No unused `ProcessPoolExecutor` / multiprocessing chunking: R0.6.1 identity bench (`pnl_checksum` `6602fa69…`, `wall_ms` recorded only) does not justify in-process scenario-block multiprocessing. In-process QuantLib stays serialized by `_QL_PROCESS_LOCK`. Evidence: `backend/tests/test_r065_process_partition.py`; focused brief suite; report `reviews/r0.6.5-process-parallelism-report.md`. Intra-run scenario-block multiprocessing (option A) remains PARTIAL and may stay P1 after benches. RF-007 stays open pending acceptance benches.

## R0.6.6 Contribution reuse — COMPLETE (2026-09-09)

Independent review **APPROVE** (`reviews/sdd-briefs/task-3-r0.6.6-review.md`).

Avoid whole-book full revaluation once per factor family when the same trade/scenario P&Ls can be reused or decomposed coherently.

Full-reval ES factor contributions and scenario-attribution factor buckets reuse the already-computed joint trade/scenario P&L and attribute families from one base Δ-Γ Greek valuation. They do not apply family-isolated scenarios or reprice the book per family × observation. `interaction` = joint full-reval − sum(families). Bound: family path is O(N) base `value` calls, not O(N×S×F) extra books; scenario `apply_scenario` stays one full scenario (not × factor keys). Cash-equity family P&L matches LINEAR at abs `1e-12`; reconcile abs `1e-6` / rel `1e-8`. Evidence: `backend/tests/test_contribution_reuse.py`; focused suite including ES/VaR/attribution/anti-cache; report `reviews/r0.6.6-contribution-reuse-report.md`.

## R0.6.7 Acceptance benches — COMPLETE pending review (2026-09-09)

`benchmarks/run_full_reval_bench.py --json` now includes an `acceptance` object. PR-safe default **N=10 × S=50** (above 1×120). Each engine row records `wall_ms`, `wall_ms_cold`, `wall_ms_warm`, `peak_rss_kib`, `scenarios_per_sec` as finite numbers — pytest asserts presence/finiteness, **not** a floor. Builtin vs QuantLib at the same N×S; QuantLib skip-or-run (`RISKFORGE_REQUIRE_QUANTLIB=1` fail-closed). Identity: R0.6.1 `6602fa69…` (1×120) and `a28cf4ee6199bf40da3f2598f4241fc85fa4adc4f86bccbbd97e4938047d7537` (10×50). Close-matrix: N×S **PARTIAL**; wall **MET** at 10×50; peak RSS **PARTIAL** (process-lifetime `ru_maxrss`; QuantLib includes prior builtin); scenarios/sec **MET** at 10×50; builtin vs QuantLib **PARTIAL** (cash equity `quantity * spot`, not reconstruction); warm vs cold **MET** at 10×50; identity **MET**. N=100/1k remain **UNMET** in default PR. No `throughput` key; `check_m6_sla.py` not invoked. Not added to nightly/PR-FULL. Evidence: `backend/tests/test_full_reval_bench.py`; report `reviews/r0.6.7-acceptance-benches-report.md`. RF-007 stays **IN PROGRESS**.

## R0.6.8 Reconstruction benches + N=100 nightly — COMPLETE (2026-09-09)

Independent review **APPROVE** (`reviews/sdd-briefs/task-7-rf007-reconstruction-benches-review.md`).

`benchmarks/run_full_reval_bench.py --json` adds a nested `reconstruction` object at PR-safe **N=10 × S=50** European options (`EuropeanOptionPosition`, live spot/vol/rate/div — not cash equity `quantity * spot`). Builtin checksum `3148a41a0b3b4bb515c75d07991a96ecc186fb9d2294ccb20347df8f5322526e`; QuantLib checksum `0594ecd65f68e33a800dbf5c331ead44b1fd353dadb198591721cc445f745eef` (pinned per engine; they need not match). P&L gap recorded at option-match `rel=2e-3` (`max_rel` ~3e-13 on this host). Peak RSS is measured in a **subprocess per impl**. Nightly sibling job `full-reval-n100` runs N=100×50 when `RISKFORGE_NIGHTLY=1` (skipped in default PR; not in PR-FULL `needs:`). Cash-equity identity pins `6602fa69…` / `a28cf4ee…` unchanged. No `throughput` key; `check_m6_sla.py` not invoked. Close-matrix: N×S **PARTIAL** (N=100 nightly; N=1k **UNMET**); wall **MET**; peak RSS **PARTIAL** (isolated child still process-lifetime `ru_maxrss`); scenarios/sec **MET**; builtin vs QuantLib **MET** on the option book; warm vs cold **MET**; identity **MET**. Evidence: `backend/tests/test_full_reval_bench.py`, `backend/tests/test_nightly_full_reval_n100.py`, `backend/tests/test_nightly_ci.py`; report `reviews/r0.6.8-reconstruction-benches-report.md`.

## R0.6 close gate — CLOSED pending independent review (2026-09-09)

QA close gate **CLOSE** (`reviews/r0.6.9-rf007-close-gate-report.md`). Independent review **pending**. **RF-007 CLOSED** (not final until Task 8 review APPROVE). This is not a restamp of rejected CLOSE `970d669`.

Required direction: 6 MET, 1 PARTIAL (option B job process, not intra-run chunks — **P1 residual**). Close-gate suite **96 passed**; nightly N=100 **1 passed**. Joint scaling is O(N×S) `value` + O(N) Greeks, bounded as a HEAVY RiskRun job. Interactive default remains DELTA_GAMMA. No SLA.

Acceptance benches: N×S **PARTIAL** (10×50 + 1×120 in PR; N=100 **MET** in nightly; N=1k **UNMET**); wall **MET** at 10×50; peak RSS **PARTIAL** (isolated subprocess per impl; still process-lifetime `ru_maxrss` within that child — not MET); scenarios/sec **MET** at 10×50; builtin vs QuantLib **MET** on the European option reconstruction book (per-engine checksums; P&L gap within `rel=2e-3`); warm vs cold **MET** at 10×50; identity **MET**. Do not invent a host SLA from recorded `wall_ms`.

### Exit criteria

Full revaluation is still allowed to be expensive, but its scaling is explainable, benchmarked, bounded, and appropriate for a risk-run job.

Explainable **yes**; bounded **yes**; appropriate **yes**. **Benchmarked** at PR-safe 10×50 reconstruction (plus 1×120 / 10×50 cash-equity identity); N=100 recorded in nightly. Peak RSS still **PARTIAL** (measurement limit). N=1k **UNMET** (not a fake SLA). Close-gate **CLOSE** pending independent review.

---

# R0.7 — Rebuild Hierarchy from Reusable Trade-Level Results

Related findings:

- RF-008

## R0.7.1 Stable hierarchy identifiers — COMPLETE (2026-09-04)

Prefixed `HierarchyNode.id` aligned with `portfolio_at` via `hierarchy_node_id`. Uniqueness is structural (not fixture-only). RF-008 stays open for trade-grain artifacts and aggregate-instead-of-reprice.

Create explicit IDs for:

```text
Firm
Portfolio
Desk
Strategy
Book
Trade
```

## R0.7.2 Trade-grain calculation artifact — COMPLETE (2026-09-04)

`TradeCalculationArtifact` is the reusable per-trade type (PV, additive Greeks, stress P&L by scenario, optional historical vector). Hierarchy still full-reprices each node. RF-008 stays open for R0.7.3.

A risk run should be able to produce/reuse:

- trade PV;
- additive sensitivities;
- stress P&L by scenario;
- historical P&L vector where appropriate.

## R0.7.3 Aggregate instead of reprice — COMPLETE (opt-in consume, 2026-09-04)

`HierarchyEngine.build` / `risk_at` accept a complete `artifacts` map and sum PV / additive Greeks / stress P&L without pricing. `PortfolioService.hierarchy` produces that map (one `value` per position) and attaches `historical_pnl` once per trade. Artifact-path node VaR/ES are VaR/ES of the summed vector. Default no-artifact `build` still full-reprices. RF-008 stays open.

- additive metrics sum;
- stress sums from trade P&Ls;
- node VaR/ES computes from node scenario P&L vector;
- limits target a stable node.

## R0.7.4 Lazy drilldown

Do not return massive nested by-position payloads on every hierarchy node unless requested.

## R0.7.5 Default build uses trade artifacts — COMPLETE (2026-09-08)

Independent review **APPROVE** (`reviews/r0.7.5-default-hierarchy-artifacts-independent-review.md`). When `artifacts` is omitted, `HierarchyEngine.build` / `risk_at` build a complete trade-grain `TradeCalculationArtifact` map **once** (`pricing.value` + shared `historical_pnl_for_valuation` per position) and then use the existing artifact aggregation path. Explicit `artifacts=` maps are unchanged. Node VaR/ES remain VaR/ES of the summed historical vector. Stress filled in R0.7.6; limits stay `[]` (P1 residual with R0.7.4).

## R0.7.6 Hierarchy artifact path fills stress — COMPLETE (2026-09-09)

Independent review **APPROVE** (`reviews/r0.7.6-hierarchy-artifact-stress-independent-review.md`). **RF-008 CLOSED.**

Default producer (`HierarchyEngine._trade_artifacts`; `PortfolioService.hierarchy` delegates to `build`) attaches per-trade `stress_pnl` for `self.stress_scenarios` / `DEFAULT_SCENARIOS`: each scenario applied **once** via `apply_scenario`, then every position valued on the shocked snapshot. Nodes expose filled `stress` with parent == sum(children). Artifact-path `StressResult.scenario` uses scenario **id** (legacy `StressEngine.run` uses **name** — P&L matches). Limits stay `[]` — **P1 residual** with R0.7.4 lazy drilldown. Report: `reviews/r0.7.6-hierarchy-artifact-stress-report.md`.


### Exit criteria

Hierarchy time is driven primarily by one base calculation + aggregation, not number-of-nodes × full-risk-run.

---

# R0.8 — Make RiskRun Reproducible and Canonical

Related findings:

- RF-009 (**CLOSED**)
- RF-013 (**IN PROGRESS**; HTTP overwrite pin landed in R0.8.6; finding not CLOSED — `reviews/r0.8.6-rf013-close-gate-report.md`)
- RF-010

## R0.8.1 Deterministic RiskRun specification — COMPLETE (2026-09-04)

First-class optional `historical_dataset_id`/`version`, `as_of`, `calculation_config` on `RiskRun` with memory/SQLite round-trip. Alembic `003_risk_run_spec_fields`. RF-009 stays open for R0.8.2 factory unification.

RiskRun must reference:

- portfolio ID/version;
- market snapshot ID;
- historical dataset ID/version;
- scenario set/version;
- pricing engine/version;
- methodology;
- as-of;
- calculation config.

## R0.8.2 Same factories in API and worker — COMPLETE (2026-09-04)

`build_portfolio_service()` is the shared API/worker construction path. Enqueue persists factory-resolved (or request) spec columns. Request dataset id does not rebind the engine. RF-009 stays open for R0.8.3 / R0.8.4.

API interactive path and worker must resolve historical data/pricing config through the same dependency construction.

## R0.8.3 Server-owned persistence identity — COMPLETE (2026-09-04)

`PortfolioRepository.create` fails if the id exists; `update` fails if missing. Persist `RiskRunWorker.submit` create-if-absents or attaches the stored book (does not upsert). Legacy `save` remains an upsert for seed callers. RF-009 stays open for R0.8.4. RF-013 HTTP pin is R0.8.6.

Separate:

```text
create portfolio
update portfolio
calculate inline demo
calculate persisted portfolio
```

Do not upsert arbitrary stored portfolios because a request supplied the same ID.

## R0.8.4 Typed run requests — COMPLETE (2026-09-08)

Independent review **APPROVE** (`reviews/r0.8.4-typed-run-requests-independent-review.md`). Replaced opaque `request: dict` calculation blobs with per-`run_type` Pydantic schemas (`extra='forbid'`). Create DTO + worker submit validate the same typed body; validated JSON dump is persisted. `historical_dataset_id` rebinds the historical engine through shared factory helpers for both spec resolve and worker execution, or fails 400 if unsupported — never silently ignored. CSV identities use path-derived `file:<abspath>`. Residual Minor (execute from request blob vs persisted columns) addressed in R0.8.5.

## R0.8.5 Postgres integration tests — COMPLETE (2026-09-08)

Independent review **APPROVE** (`reviews/r0.8.5-postgres-same-spec-independent-review.md`). **RF-009 CLOSED.**

Coverage:

- **Same-spec parity (SQLite, PR-green):** interactive `resolve_run_spec` + `portfolio_service_for_spec` + `execute_run_type` vs worker `submit(execute=False)` → `poll_once` → complete for `summary` and `var` with synthetic dataset — exact payload equality.
- **Execute-from-columns (R0.8.4 residual Minor):** `_execute` uses `resolve_execute_spec` / `request_blob_for_execute` so persisted `historical_dataset_id` / version / `as_of` / `calculation_config` win over a tampered or emptied request blob; mismatch fails closed.
- **Lifecycle gaps:** SQLite parity module covers identity-on-execute. Live Postgres module (`test_postgres_risk_run_lifecycle.py`) covers save/load, run create, claim, COMPLETED lifecycle, FAILED (missing portfolio), same-spec parity, and identity protection — skip/fail rules match `test_postgres_two_worker.py`.
- **Two-worker claim:** `test_postgres_two_worker.py` (SKIP LOCKED).

### Exit criteria

The same RiskRun spec yields the same result whether executed interactively or by the worker — **met**. Residual Minor: `methodology` column does not override a conflicting request blob.

Report: `reviews/r0.8.5-postgres-same-spec-report.md`.

## R0.8.6 Canonical identity HTTP pin — COMPLETE; RF-013 stays IN PROGRESS (2026-09-09)

HTTP overwrite pin landed (`reviews/r0.8.6-rf013-close-gate-report.md`). **RF-013 remains IN PROGRESS** — independent review KEEP OPEN; do not CLOSE.

Acceptance:

- HTTP `POST /api/v1/risk/runs` and `/risk/runs` with `portfolio.id=global-macro` cannot overwrite the seeded Cross-Asset book (`GET /portfolio` + SQL). Catalog `GET /portfolios/global-macro` remains the in-code SAMPLE contract. Evidence: `backend/tests/test_portfolio_identity.py`. **MET**.
- Persisted RiskRun reproduced from IDs — **cite R0.8.5** `tests/test_same_spec_parity.py` (RF-009 CLOSED). **MET**.
- PostgreSQL pytest/integration — **cite R0.8.5** `tests/test_postgres_risk_run_lifecycle.py` (identity-on-execute included). Not duplicated. **MET**.
- Large derived payloads not unconstrained JSON — **UNMET**. PERF-016 is `risk_results.payload` unconstrained JSON (`backend/app/persistence/models.py`). R0.8.4 typed per-`run_type` request bodies are not this cell.

Residuals (keep finding IN PROGRESS): no `portfolio_version` / server-issued ids; live calculate still POSTs a full book; leftover `save` upsert for seed callers; object ACLs = RF-014.

---

# R0.9 — Separate Domain, API, and Application Contracts

Related findings:

- RF-010
- RF-013 (identity **IN PROGRESS** after R0.8.6 HTTP pin; remaining domain/API split is RF-010)

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

## R0.10.1 Classify endpoints — COMPLETE (2026-09-04)

`backend/app/api/execution_class.py` is an OpenAPI bijection (32 owned routes). Listed heavy examples are HEAVY. `classify(..., methodology="FULL_REVALUATION")` upgrades `POST /risk/summary`. Not wired to routers. RF-015 stays open for R0.10.2 / R0.10.3.

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

## R0.10.2 Dashboard batch/run result — COMPLETE (2026-09-04)

`POST /risk/dashboard` returns the prior nine payload keys from one request. `loadDashboard()` calls that path only. Classified HEAVY; OpenAPI bijection updated. RF-015 stays open for R0.10.3 (request-thread / backpressure).

Prefer one completed risk-run artifact or a coherent batch service.

## R0.10.3 Queue/backpressure — COMPLETE (refuse-gate, 2026-09-04)

When `RISKFORGE_EXTERNAL_WORKER=1` or `RISKFORGE_HEAVY_INLINE=0`, FULL_REVALUATION summary, dashboard, leftover `risk.py` HEAVY routes, and HEAVY stress / attribution / limits refuse request-thread compute (HTTP 400 `Invalid request`, `details.use=/risk/runs`). `run_type=dashboard` on `POST /risk/runs` returns the coherent batch payload (lists stay arrays). Compose `loadDashboard()` falls back to that RiskRun path on refuse. Remaining HEAVY UI POSTs addressed in R0.10.4.

Bound:

- outstanding jobs;
- worker concurrency;
- scenario count;
- portfolio size.

### Exit criteria

Large risk cannot monopolize ordinary HTTP request execution indefinitely.

## R0.10.4 Remaining HEAVY UI → RiskRun fallback — COMPLETE (2026-09-09)

Independent review **APPROVE** (`reviews/r0.10.4-heavy-ui-riskrun-fallback-independent-review.md`). Frontend `api.js` shared helper (`postHeavyOrRiskRun` / `runViaRiskRun`) mirrors `loadDashboard`: sync HEAVY POST first; on refuse (`details.use=/risk/runs`) create+poll typed RiskRun. New Backend `run_type`s (R0.8.4 schemas): `stress_evaluate`, `reverse_stress`, `reverse_stress_multi`, `stress_compare`, `query`, `attribution`, `attribution_demo`, `change_attribution`, `es`, `var_compare`. INTERACTIVE routes unchanged. **RF-015 CLOSED**.

Report: `reviews/r0.10.4-heavy-ui-riskrun-fallback-report.md`.

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
- hierarchy benchmark — COMPLETE (nightly identity, `reviews/r0.12-hierarchy-bench-independent-review.md`);
- optional QuantLib E2E — COMPLETE (`reviews/r0.12-ql-e2e-independent-review.md`; nightly job only).

## R0.12.6 Labeled-runner SLA-K1/K2 (honest residual)

RF-016 leftover. No self-hosted runner is registered (`actions/runners total_count=0`, 2026-09-09). Do **not** run `benchmarks/check_m6_sla.py` on `ubuntu-latest`. Harness + `docs/performance.md` + `benchmarks/RESULTS.md` exist; CI does not enforce host floors. Score **PARTIAL**. Do not CLOSE RF-016. Evidence: `reviews/r0.12.6-rf016-sla-k-report.md`.

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

R0.13 ROADMAP counts: COMPLETE (independent review APPROVE, `reviews/r0.13-roadmap-counts-independent-review.md`). Historical 160 tables untouched. Current gate remains recorded Phase A, not a live re-run.

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
