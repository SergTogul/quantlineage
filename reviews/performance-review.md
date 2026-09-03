# RiskForge Performance Review

Date: 2026-09-03  
Owner: C++ / Senior Performance Engineering (review-only)  
Scope: Independent performance review of the RiskForge repository. Production code was not modified. Temporary diagnostics were not committed.

**Host (this session):** Intel Core i7-7700HQ @ 2.80 GHz (4C/8T), macOS 13.7.8, Python 3.12.14, NumPy 2.5.2, QuantLib 1.43, Apple clang 14.0.3. Absolute times are laptop-specific and are **not** a production throughput claim.

---

## Executive Summary

RiskForge can already run **LINEAR / DELTA_GAMMA Historical VaR on 10k–100k trades × ~1k aggregated scenarios** on the current approximate path. That path prices once, sums Greeks, then applies four factor series in NumPy (`O(N + S)` after aggregation). Measured: **10 000 equities × 750 scenarios in 30 ms** after warmup.

It **cannot** efficiently execute the other target: **1k–100k trades × 100–10k full-revaluation or per-name scenario workloads**. Three architectural bottlenecks dominate:

1. **Shocked-snapshot construction is `O(F² × S)`** because each typed factor bump deep-copies and re-freezes the whole `MarketSnapshot`. Measured: **500 names × 50 scenarios = 108 s** before any pricing.
2. **Full revaluation is a Python `N × S` loop** that rebuilds QuantLib curves, surfaces, processes, and instruments on every `value()` call. Valuation LRU **misses 100%** on unique shocked markets and made the 9-trade × 750-obs QuantLib full-reval **slower** (1.96 s vs 1.30 s).
3. **Hierarchy recomputes VaR + stress + limits on every node.** Measured: **100 trades / 118 nodes / 250 obs = 895 ms**. At 10k–100k trades this is a multi-minute synchronous HTTP job, not a dashboard call.

The C++ kernel meets its scoped SLA on this host (**SLA-K1 128×, SLA-K2 1.57×** on `10k_x_1k`). That SLA does **not** describe product Historical VaR: the wired path aggregates to **one** exposure, then NumPy already finishes `1 × 750` in **0.016 ms**. Native acceleration is aimed at nested-loop `E × S` work the product currently avoids.

**Bottom line:** treat LINEAR/Δ-Γ as the scalable MVP risk path; treat FULL_REVALUATION, hierarchy, threat attribution, and ES factor isolation as correctness features that need a different execution architecture before 1k+ names or 1k+ shocked markets.

Finding counts:

- Critical: 3
- High: 7
- Medium: 6
- Low: 3

---

## Observed Execution Architecture

```text
HTTP POST (sync)  ──► PortfolioService
                        ├─ summary      → HistoricalRiskEngine.calculate
                        ├─ var/es/contrib → VaRAnalytics._position_pnls (per trade)
                        ├─ stress/evaluate → StressEngine (shocked_value per trade)
                        ├─ hierarchy    → HierarchyEngine._node per tree node
                        ├─ limits       → risk.calculate + stress + KR sensitivities
                        └─ reverse      → binary search / ray+CD × full reprice

PricingEngine.value(position, market)     # one trade, one snapshot
  QuantLib: session RLock → rebuild curve/surface/process/instrument → NPV
  CachedPricingEngine: SHA256(trade JSON + snapshot content_hash)

LINEAR / Δ-Γ:
  value_portfolio once → sum Greeks → NumPy (or optional native 1×S)

FULL_REVALUATION:
  historical_shocked_snapshots(base, S)   # materialize S MarketSnapshot copies
  for s in S:
      value_portfolio(N)                  # N QuantLib reconstructions
```

Native C++ (`portfolio_scenarios_flat_into`) only implements

`δ·eq + ½γ·eq² + ν·vol + DV01·rates + fxΔ·fx`

and is **not** used for FULL_REVALUATION (correct). ADR 007 serializes QuantLib with an `RLock`; in-process threads do not parallelize QL pricing.

Related product docs (not duplicated here): `docs/performance.md`, `benchmarks/README.md`, `benchmarks/RESULTS.md`, `docs/adr/007-quantlib-concurrency.md`.

---

## Measurements Performed

| Workload | Kind | Result |
|---|---|---|
| Official `10k_x_1k` kernel bench | **Measured** | python 4088 ms; numpy 6.7 ms†; cpp_ctypes 31.1 ms (**131×**); cpp_ctypes_t4 16.9 ms (**1.84×** vs serial); cpp_header 20.7 ms; cpp_header_t4 7.6 ms |
| `benchmarks/check_m6_sla.py` | **Measured** | **PASS** SLA-K1 **128.42×** (floor 50×); SLA-K2 **1.57×** (floor 1.3×) |
| Demo book (9 trades) warm LINEAR/Δ-Γ summary | **Measured** | **0.75 ms** builtin |
| Same, first call (cold) | **Measured** | 302 ms (import/warmup; not steady-state) |
| Demo book warm FULL_REVAL 750 obs | **Measured** | builtin **715 ms**; QuantLib **1301 ms**; QL+LRU **1959 ms**, `hits=0, misses=6768` |
| Dashboard 9 endpoints, serial, warm, 9 trades | **Measured** | **167 ms** builtin |
| 10k equities × 750 Δ-Γ | **Measured** | **29.9 ms** |
| `MarketSnapshot.apply` F sequential equity bumps | **Measured** | F=50: 14 ms; F=200: 186 ms; F=500: **1141 ms**; F=1000: **3704 ms** |
| `historical_shocked_snapshots` S=50 | **Measured** | F=50: 1.2 s; F=200: **19.3 s**; F=500: **107.6 s** |
| Hierarchy 100 trades / 118 nodes / 250 obs | **Measured** | **895 ms** |
| Hierarchy JSON, 50 trades | **Measured** | **167 KB** |
| Stress `shocked_value` vs shock-once, 9 trades | **Measured** | **4.0×** slower per-position |
| NumPy `1×750` Δ-Γ series | **Measured** | **0.016 ms** |
| QuantLib one equity option vs builtin | **Measured** | **0.132 ms vs 0.006 ms** (~22×) |
| `np.quantile` vs `np.partition` on 10⁷ | **Measured** | 94 ms vs 45 ms (irrelevant at S≤10k) |
| 10k Pydantic `EquityPosition` construct | **Measured** | **81 ms** |
| ES FULL_REVAL n=30, S=20 | **Measured** | 91 ms (includes 4× factor isolation) |

† NumPy harness uses algebraic strength reduction `O(E+S)`, not nested `O(E×S)`.

Native `libriskkernel` is **not** installed under `backend/native/` in this checkout. The bench built a temporary copy. Product default remains `RISKFORGE_SCENARIO_KERNEL=python` (NumPy).

Commands executed (review-only):

```bash
OMP_NUM_THREADS=1 backend/.venv/bin/python benchmarks/run_scenario_bench.py \
  --workload smoke --workload 1k_x_1k --workload 10k_x_1k \
  --threads 4 --parallel-compare --iters 1 --json

backend/.venv/bin/python benchmarks/check_m6_sla.py

# Plus inline product-path timings against SAMPLE_PORTFOLIO and synthetic equity books.
# Temporary diagnostic script was deleted and not committed.
```

---

## Performance Strengths

- LINEAR/Δ-Γ Historical VaR is **aggregated then vectorized**. Ten-thousand-trade books are already interactive on this path.
- Native kernel has a real reference, ABI parity tests, a documented SLA, and honest non-claims in `docs/performance.md`.
- QuantLib concurrency is handled correctly (process-global `Settings` behind `RLock`; native kernel does not touch QL).
- Scenario application is immutable (no in-place mark corruption). Cache keys bind `content_hash`, so stale marks are not the main risk — **miss cost** is.
- Risk-run worker + Postgres `SKIP LOCKED` is the right place to put heavy jobs; it is just not what the dashboard uses today.
- Additive stress/hierarchy reconciliation is exact at the trade P&L layer once those P&Ls exist.

---

## Critical Findings

## PERF-001 — Sequential snapshot apply is `O(F² × S)`

**Severity:** CRITICAL  
**Hot path:** Full revaluation / historical shocked snapshots / stress apply

**Evidence:**

- `MarketSnapshot.bump` / `apply` in `backend/app/domain/models.py` (`apply` loops `bump`; each `bump` `model_copy` + recursive freeze of all nested maps).
- `historical_shocked_snapshots` expands **one shock per name** (`expand_aggregate_change`), then `apply`.
- Measured apply of F equity-spot shocks: 14 ms (50), 186 ms (200), 1141 ms (500), **3704 ms (1000)**.
- Measured snapshot generation S=50: **1.2 s (F=50), 19.3 s (F=200), 107.6 s (F=500)**.

**Observed behavior:** A parallel equity move is not one copy of the spots dict. It is F independent bumps, each copying spots, vols, curves, and vol surfaces and re-freezing them.

**Impact:** Snapshot construction **dominates** FULL_REVAL before QuantLib runs. Estimate (not measured at this size): F=1 000 names × S=1 000 ≈ **1 hour** of copies; F=1 000 × S=10 000 is **not viable**. Unique underlyings, not trade count, drive this cost.

**Recommendation:** Apply a scenario in **one copy**: mutate a staging dict of spots/vols/rates/curves/surfaces, freeze once, assign a new id. For homogeneous relative equity/vol/FX shocks, scale whole maps in NumPy/C++ rather than per-key Python bumps.

**Validation benchmark:** `historical_shocked_snapshots` wall time and peak RSS for F ∈ {50,200,1000,5000} × S ∈ {50,750,1000}; checksum of `content_hash` / `diff` vs current apply.

**Numerical parity requirement:** `content_hash` and `diff` vs current sequential `apply` within exact float equality for the same ordered shocks (spots multiplicative, rates additive).

**Estimated effort:** M  
**Dependencies:** Market Data domain freeze semantics; Stress/VaR callers of `apply`.

---

## PERF-002 — FULL_REVALUATION is an `N × S` Python/QuantLib reconstruction loop

**Severity:** CRITICAL  
**Hot path:** Full revaluation / QuantLib / `/risk/summary?methodology=FULL_REVALUATION` / `/risk/var/compare`

**Evidence:**

- `full_revaluation_pnl_series` and `VaRAnalytics._full_reval_position_pnls` loop scenarios then trades.
- `QuantLibPricingEngine.value` rebuilds `ZeroCurve` / `BlackVarianceSurface` / `BlackScholesMertonProcess` / `VanillaOption` / schedules per call (`backend/app/pricing/quantlib.py`).
- Curve cache stores RiskForge `YieldCurve` only; QL handles are still rebuilt (`curve_rates.py` vs `_zero_curve_handle`).
- Measured 9-trade × 750: builtin **715 ms**, QuantLib **1301 ms**.
- One QL equity option: **0.132 ms**. Estimate: 1 000 options × 1 000 scenarios ≈ **130 s** if every call reconstructs; 50k × 10k is not a batch job on this design.

**Observed behavior:** No instrument/engine reuse across scenarios. No RelinkableHandle quote updates. No scenario-chunked process pool.

**Impact:** FULL_REVAL cannot meet interactive latency except on demo-sized books. `/risk/var/compare` always runs FULL_REVAL alongside LINEAR/Δ-Γ.

**Recommendation:** (1) Stream scenarios in chunks; do not keep all shocked snapshots. (2) Reuse QL instruments with relinkable quotes/curves keyed by (trade, curve fingerprint). (3) Parallelize by **process** over scenario partitions (ADR 007). (4) Keep LINEAR/Δ-Γ as the default API methodology.

**Validation benchmark:** N ∈ {10,100,1k} × S ∈ {50,750,1k} builtin vs QuantLib; trades/s and scenarios/s; RSS.

**Numerical parity requirement:** Existing FULL_REVAL vs golden tests (`test_var_methodology.py`, `test_quantlib_pricing.py`) at current abs/rel tols.

**Estimated effort:** L–XL  
**Dependencies:** Quant Pricing + C++/process workers; ADR 007.

---

## PERF-003 — Hierarchy recomputes full risk on every node

**Severity:** CRITICAL  
**Hot path:** Hierarchy / `/risk/hierarchy` / risk-run `hierarchy` / dashboard collage

**Evidence:**

- `HierarchyEngine._node` calls `_metrics` (full VaR), `_stress` (all default scenarios), `_limits` for **every** trade, book, strategy, desk, portfolio, and firm node (`backend/app/risk/hierarchy.py`).
- `build()` constructs a one-position `Portfolio` per trade, then re-aggregates the same positions at every ancestor.
- Measured: 20 trades → 143 ms; 50 → 453 ms; **100 trades / 118 nodes → 895 ms** (250 obs, builtin equities).
- Hierarchy JSON for 50 trades: **167 KB** (~2.8 KB/node including nested stress `by_position` and limits).

**Observed behavior:** Additive NAV/Greeks/stress are recomputed from pricing instead of summed from children. Non-additive VaR is recomputed from scratch on each subset (correct statistically, but the implementation re-prices rather than slicing a trade-level P&L matrix).

**Impact:** Estimate: ~**90 s** for 10k trades on this host class; 100k is a batch job. Payload estimate ~**28 MB** (10k nodes) to **~280 MB** (100k) as JSON. Frontend `Promise.all` includes this on every dashboard load.

**Recommendation:** Price and approximate-P&L **once at trade grain**. Roll up additive metrics. For node VaR/ES, either (a) subset-sum the trade P&L matrix (LINEAR/Δ-Γ exact; FULL_REVAL exact if trade P&Ls stored) or (b) compute VaR only for requested drill nodes. Return a flat or lazy tree, not nested stress arrays on every node.

**Validation benchmark:** wall time and JSON bytes for N ∈ {50,200,1k,10k} with a fixed desk/book shape; additive reconciliation abs 1e-9 unchanged.

**Numerical parity requirement:** Node `var_*` / ES match current subset `HistoricalRiskEngine.calculate` within existing quantile noise (same series). NAV/Greeks/stress sums remain abs 1e-9.

**Estimated effort:** L  
**Dependencies:** Portfolio Risk + Frontend payload contract (Lead Architect if DTO shrinks).

---

## High Findings

## PERF-004 — Dashboard issues nine independent synchronous risk runs

**Severity:** HIGH  
**Hot path:** API / Frontend `loadDashboard`

**Evidence:** `frontend/src/api.js` `Promise.all` of summary, stress, evaluate, contributors, limits, factors, var, hierarchy, attribution/demo. Each POSTs the full portfolio. Service methods do not share valuations (`backend/app/services/portfolio_service.py`). Limits calls `risk.calculate` **and** `stress_engine.run` again. Contributors calls `var_engine.report` again.

**Observed behavior:** Same book is priced and shocked many times per page load. FastAPI handlers are sync `def`, so they occupy worker threads for the whole compute.

**Impact:** Demo is fine (167 ms serial warm). At 1k+ trades, nine overlapping GIL/QL-lock jobs amplify PERF-003/005. No common `RiskContext`.

**Recommendation:** One server-side “overview” computation (or one risk-run with multiple result types) returning summary + var + stress + limits + contributors. Keep drill-down endpoints lazy.

**Validation benchmark:** End-to-end `/api/v1` dashboard equivalent at N=9, 1k, 10k; count of `PricingEngine.value` calls (trace/hook).

**Numerical parity requirement:** Byte-stable numbers vs today’s separate endpoints on the demo artifact.

**Estimated effort:** M  
**Dependencies:** Backend API + Frontend; optional risk-run.

---

## PERF-005 — `shocked_value` rebuilds the scenario per trade

**Severity:** HIGH  
**Hot path:** Stress / threat evaluate / scenario attribution

**Evidence:** `PricingEngine.shocked_value` → `shock_snapshot` → `apply_scenario` per position (`backend/app/interfaces/pricing.py`, `backend/app/risk/stress.py`). Scenario memo hashes `content_hash` on **every** lookup and `model_copy`s on hit (`scenario_memo.py`). Measured **4.0×** vs shock-once then `value()` on the 9-trade book.

**Observed behavior:** N identical applies per scenario. Memo reduces apply work after the first trade but still pays JSON+SHA256 + copy. Threat evaluate (`THREAT_SCENARIOS` = 8) then runs factor-isolated revals per scenario (`scenario_attribution.py`).

**Impact:** Stress scales as `O(S_stress × N × (apply_or_hash + price))`. Factor isolation adds `O(F_keys × N)` extra reprices per scenario. Evaluate was **92 ms** vs simple `run` **11 ms** on 9 trades.

**Recommendation:** Shock once per scenario; `value_portfolio` on the shocked snapshot. Use precomputed `by_trade_pnl` for attribution (already optional). Isolate factors from the same base without N extra applies.

**Validation benchmark:** `StressEngine.run` / `evaluate` N ∈ {9,1k,10k} × 5–8 scenarios; `value` call counts.

**Numerical parity requirement:** Per-position PnL abs 1e-9 vs current `shocked_value`.

**Estimated effort:** S–M  
**Dependencies:** Stress engine; PricingEngine helper `value_portfolio_shocked`.

---

## PERF-006 — Valuation LRU is an anti-cache on unique shocked markets

**Severity:** HIGH  
**Hot path:** CachedPricingEngine / FULL_REVAL / reverse stress

**Evidence:** Key = SHA256(full trade JSON) + `market.content_hash()` + config (`backend/app/pricing/cache.py`). Default maxsize **4096**. QuantLib full-reval 9×750: **`hits=0, misses=6768, size=4096`**, wall **1959 ms vs 1301 ms** uncached. `content_hash` is full-snapshot JSON+SHA256 (2.3 ms at F=1000).

**Observed behavior:** Every historical observation is a new hash. LRU fills with shocked valuations that will not recur, evicts, and still hashes on the miss path. `model_copy` of `Valuation` on every return.

**Recommendation:** Disable the LRU for shocked/full-reval loops (or key only base snapshot). Cache **instrument setup** (QL handles) keyed by trade + curve/vol fingerprint, not NPV. Invalidation: fingerprint change ⇒ miss. Never serve NPV across different `content_hash`.

**Validation benchmark:** Same FULL_REVAL N×S with cache on/off; hit rate; hash time vs `value` time.

**Numerical parity requirement:** Identical NPVs to inner engine; existing cache tests remain valid for **repeated base** valuations.

**Estimated effort:** S  
**Dependencies:** Pricing cache policy; env `RISKFORGE_PRICING_CACHE`.

---

## PERF-007 — Native kernel is not the product Historical VaR bottleneck

**Severity:** HIGH (misplaced optimization / FFI)  
**Hot path:** C++ kernel / Python↔C++ boundary / LINEAR/Δ-Γ

**Evidence:** `_pnl_via_scenario_kernel` builds **one** `Exposure` and a Python `Shock` list (`backend/app/risk/historical.py`). Default backend is NumPy, **0.016 ms** for 750 scenarios. `benchmarks/RESULTS.md` already documents 1×N as FFI-bound. ctypes packs via nested list comprehensions into `c_double` arrays every call (`backend/app/compute/kernel.py`). C++ still does nested `O(E×S)` even though this kernel is linear in exposures. Thread pool is created **per call** (smoke `t4` was **slower** than serial).

**Observed behavior:** SLA-K1/K2 prove nested-loop C++ vs nested-loop Python on synthetic `E×S`. Product VaR does not use that shape. `libriskkernel` is not in `backend/native/` unless separately built.

**Impact:** Further kernel micro-opts will not move HTTP VaR. If per-trade exposures are ever passed in without aggregating, C++ would do unnecessary `E×S` vs a sum-then-scale.

**Recommendation:** Keep NumPy as the 1×S path. If name-level shocks appear, design a **factor-indexed** batch kernel (exposures × factor-id, CSR shocks) rather than packing Python objects per scenario. Persistent thread pool; optional SIMD later, only after a profiler shows `E×S` time.

**Validation benchmark:** Product `approximate_pnl_series` 1×S vs native vs NumPy; optional true `E×S` name-level kernel vs NumPy rewrite.

**Numerical parity requirement:** Existing `KERNEL_PNL_*` / `KERNEL_ABI_*` tols.

**Estimated effort:** M for a real factor kernel; S to stop wrapping 1×S in ctypes.  
**Dependencies:** C++ Performance; Portfolio Risk methodology (aggregate vs per-name shocks).

---

## PERF-008 — Contribution paths multiply full revaluations

**Severity:** HIGH  
**Hot path:** ES contributions / scenario attribution / `/risk/es?methodology=FULL_REVALUATION`

**Evidence:** `_aggregate_factor_pnl_full_reval` reprices the **whole book four extra times per observation** (`backend/app/risk/es.py`). Scenario attribution does isolated full reval per `RiskFactor.key` (`scenario_attribution.py`). ES FULL n=30 S=20: **91 ms** vs Δ-Γ sample **1.0 ms**.

**Impact:** FULL_REVAL ES ≈ `5 × N × S` pricings (total + 4 families) plus snapshot applies. At 1k×1k this is a long batch; at 50k×10k it is resource exhaustion.

**Recommendation:** Compute factor P&L from shocked marks without a second full snapshot stack where the shock is linear in that family; keep `interaction` residual. For LINEAR/Δ-Γ, keep the current additive Greek split (already cheap).

**Validation benchmark:** ES report time and `value` counts LINEAR vs FULL for S=20,75,750.

**Numerical parity requirement:** Contribution sum ≈ portfolio ES (existing abs 1e-6 / rel 1e-8).

**Estimated effort:** M  
**Dependencies:** Portfolio Risk + Stress attribution.

---

## PERF-009 — Position P&L matrices are materialized densely

**Severity:** HIGH  
**Hot path:** VaR report / contributors / ES / memory

**Evidence:** `VaRAnalytics._position_pnls` stores `dict[id, ndarray(S)]` (`backend/app/risk/var.py`). FULL_REVAL fills `N × S` in Python loops. Contributors and ES reuse this.

**Impact:** Estimate: 100k trades × 10k scenarios × 8 bytes ≈ **8 GB** for one dense P&L matrix (plus copies in book/desk rollups). LINEAR/Δ-Γ does not need this for **portfolio** VaR (aggregated Greeks suffice); it is only required for Euler/ES allocation.

**Recommendation:** Portfolio VaR from aggregated series only. Contributions: compute on demand, or chunk trades, or keep a memory-mapped/float32 column store. Do not hold book+desk+strategy copies (they are sums).

**Validation benchmark:** RSS for N×S ∈ {1k×750, 10k×1k, 50k×1k} on `var_report`.

**Numerical parity requirement:** Component VaR Euler sum = parametric VaR (existing tests).

**Estimated effort:** M  
**Dependencies:** Portfolio Risk DTOs (maybe drop full series from HTTP).

---

## PERF-010 — Heavy endpoints remain synchronous

**Severity:** HIGH  
**Hot path:** API responsiveness / risk runs

**Evidence:** `backend/app/api/risk.py` and stress routers are sync. Risk-run supports `summary|var|stress|hierarchy|...` but the SPA calls POST compute APIs directly. Worker `ThreadPoolExecutor(max_workers=2)` shares the QL `RLock` in-process.

**Impact:** Hierarchy / FULL_REVAL / threat evaluate / var compare / reverse-multi will exceed interactive latency (~100–300 ms) as soon as N or F leaves demo scale. QL threads serialize.

**Recommendation:** Keep warm LINEAR/Δ-Γ **summary** sync. Move hierarchy, FULL_REVAL, evaluate, var/compare, reverse-multi, what-if to `POST /risk/runs`. Scale QL with **processes**, not threads.

**Validation benchmark:** p50/p95 API times at demo vs N=1k; queue wait vs compute for risk-runs.

**Numerical parity requirement:** Job payload equals sync endpoint.

**Estimated effort:** M  
**Dependencies:** Backend API + Frontend polling (already exists for runs).

---

## Medium Findings

## PERF-011 — QuantLib objects have no lifecycle beyond a single `value()`

**Severity:** MEDIUM  
**Hot path:** QuantLib

**Evidence:** `_option`, `_bond_npv`, `_swap_npv`, `_fx_option` construct engines every call. `_bond` / `_swap` / cap / swaption do a **second** NPV for DV01. `position.model_copy(update=...)` on every market overlay.

**Recommendation:** Relinkable quotes + cached instruments per trade; bump quotes for FD DV01 instead of rebuilding swaps. Invalidation: trade economics or evaluation date change. Do not cache across threads without the existing `RLock`.

**Validation benchmark:** `value_portfolio` on mixed book 1k repeats; option/swap share of time (cProfile).

**Numerical parity requirement:** Golden QL tests rel=1e-10 / existing bands.

**Estimated effort:** L  
**Dependencies:** Quant Pricing Engineer.

## PERF-012 — Scenario memo and curve fingerprint hash on the hot path

**Severity:** MEDIUM  
**Hot path:** Python / caching

**Evidence:** `scenario_memo_key` uses `base.content_hash()` every `apply_scenario`. `select_yield_curve` hashes currency curve payload every call even when marks did not change in a meaningful way. Demo `content_hash` 0.026 ms; F=1000: **2.3 ms**.

**Recommendation:** Thread-local last-snapshot pointer: if `id` and object identity match, skip hash. Invalidation: any `bump`/`model_copy` yields a new object.

**Validation benchmark:** `apply_scenario` 10k times on identical (base, scenario).

**Numerical parity requirement:** Memo tests unchanged.

**Estimated effort:** S

## PERF-013 — What-if / reverse-multi evaluation counts

**Severity:** MEDIUM  
**Hot path:** What-if / reverse stress

**Evidence:** What-if runs before and after VaR + factors + stress (`incremental_var.py`). Reverse-multi: feasibility + ray search (`DEFAULT_MAX_ITERATIONS=40`) + **8** coordinate passes × **4** families × up to 40 binary-search steps — worst case **O(10³)** full portfolio reprices (`reverse_stress_multi.py`).

**Impact:** Fine on 9 trades (reverse equity **9 ms**). Linear in N×iters. Reverse-multi on 10k option trades is a job.

**Recommendation:** Reuse base Greeks for LINEAR what-if; bound reverse-multi evals; job-ify.

**Validation benchmark:** Count `value_portfolio` in `solve` / `what_if_analysis`.

**Numerical parity requirement:** Existing reverse/what-if tests.

**Estimated effort:** M

## PERF-014 — Kernel thread spawn and lack of SIMD

**Severity:** MEDIUM  
**Hot path:** C++ kernel

**Evidence:** `std::vector<std::thread>` / `jthread` allocated inside `portfolio_scenarios_flat_into`. Smoke 64×64: t4 **slower** (0.28 ms vs 0.14 ms ctypes). No SIMD; inner loop is scalar doubles, unit-stride `e[i*5]`.

**Recommendation:** Persistent pool; skip threads unless `n_shocks * n_exposures` exceeds a threshold (~1e6). SIMD only if a real `E×S` product path exists.

**Validation benchmark:** Existing harness smoke vs `10k_x_1k` t1/t4.

**Numerical parity requirement:** 1e-12 ABI.

**Estimated effort:** S

## PERF-015 — Frontend payload and table scale

**Severity:** MEDIUM  
**Hot path:** Frontend (material only)

**Evidence:** Full hierarchy tree + `by_position` stress on every node (167 KB / 50 trades). Heatmaps iterate API matrices. No virtualized tree. No client-side risk math (good).

**Recommendation:** Paginate/virtualize trade rows; send node metrics without nested scenario maps; lazy-load children.

**Validation benchmark:** JSON size and React render time at 1k / 10k nodes.

**Numerical parity requirement:** Display-only; no number changes.

**Estimated effort:** M  
**Dependencies:** Frontend.

## PERF-016 — Persistence JSON for large results

**Severity:** MEDIUM  
**Hot path:** Persistence / network

**Evidence:** `risk_results.payload` is unconstrained JSON (`backend/app/persistence/models.py`). Hierarchy/var contributions would store tens of MB per run. Market snapshots store the full tree, not a hash + deltas.

**Recommendation:** Store summary metrics + pointer to artifact/object storage; snapshot diffs vs base `content_hash`.

**Validation benchmark:** Postgres row size for hierarchy N=1k.

**Numerical parity requirement:** Reload equals in-memory DTO.

**Estimated effort:** M

---

## Low Findings

## PERF-017 — `np.quantile` full sort

**Severity:** LOW  
**Hot path:** VaR tail

**Evidence:** `np.quantile` on losses in `historical.py` / `var.py` / `es.py`. 10⁷ samples: 94 ms vs partition 45 ms. At S=750–10k this is **noise**.

**Recommendation:** Do not optimize until S≳1e6 or this shows up in a product profile. Then `partition`/`argpartition` for VaR and tail mean.

**Validation benchmark:** S=1e5, 1e6, 1e7 quantile vs partition; ES tail mean equality.

**Numerical parity requirement:** Same default NumPy quantile interpolation (`linear`) or an explicit definition change documented in methodology.

**Estimated effort:** S

## PERF-018 — ctypes Python object packing

**Severity:** LOW  
**Hot path:** Python↔C++

**Evidence:** `NativeScenarioKernel.pnl` builds Python lists then `c_double` arrays. Product 1×S should pass NumPy buffers (`ctypes.data` / memoryview) if native is kept.

**Estimated effort:** S  
**Numerical parity:** ABI tols.

## PERF-019 — Limits trigger SensitivityEngine bump-revalue

**Severity:** LOW–MEDIUM  
**Hot path:** Limits / sensitivities

**Evidence:** `_key_rate_dv01_abs` may run `SensitivityEngine.calculate` (2× portfolio PV per tenor) when KR not precomputed (`limits.py`). Hierarchy nodes can repeat this.

**Recommendation:** Pass Greeks from the trade-level context; skip FD when Δ-Γ Greeks already exist.

**Estimated effort:** S

---

## Scalability Model

Assumptions: this host class; builtin equities unless noted; **estimate** marked where not measured. F = unique names in the snapshot (not N).

### 1k trades × 1k scenarios

| Path | Expectation |
|---|---|
| LINEAR / Δ-Γ summary | **Interactive** (measured 1k×750 Δ-Γ **3.0 ms**). |
| VaR contributions (`N×S` arrays) | Fine (~8 MB). |
| FULL_REVAL if F≲20 (demo-like) | **~1–2 s** QL (measured 9×750 = 1.3 s; scales ~linear in S, worse if options). |
| FULL_REVAL if F=200 | Snapshot gen **estimate ~6 min** from 19 s / 50 scen × 20; plus pricing. **Not interactive.** |
| Hierarchy | **Estimate ~8–15 s** from 895 ms / 100 trades (250 obs). Borderline / job. |
| Dashboard 9× sync | Hierarchy-dominated; likely **timeouts** if hierarchy stays in `Promise.all`. |

### 10k trades × 1k scenarios

| Path | Expectation |
|---|---|
| LINEAR / Δ-Γ | **OK** (measured 10k×750 **30 ms** + Pydantic construct **81 ms**). HTTP JSON body for 10k trades is the larger cost (**hypothesis** tens of MB parse). |
| Contributors / ES Δ-Γ | `N×S` ~80 MB; CPU still small. |
| FULL_REVAL | Snapshot `O(F²S)` plus `10¹⁰` QL reconstructions if F and option share are large. **Not realistic** on this architecture. |
| Hierarchy | **Estimate ~90 s** + **~28 MB** JSON. Must be a risk-run. |
| Native kernel 1×S | Irrelevant vs NumPy 0.02 ms. |

### 50k trades × 10k scenarios

| Path | Expectation |
|---|---|
| LINEAR / Δ-Γ portfolio VaR | Still plausible: Greeks `O(N)` **estimate ~150 ms** equities; kernel `O(S)` trivial. Mixed QL options: pricing Greeks becomes the limit (FD/QL rebuild). |
| Dense trade P&L | **~8 GB** float64. Unacceptable to materialize or send as JSON. |
| FULL_REVAL | **Unsafe / impossible** without streaming, single-copy apply, instrument reuse, and process-parallel chunks. Naïve `50k × 10k` QL options **estimate** 10⁷ s. |
| Hierarchy | **Hours-class** if per-node recompute remains. |
| Memory | Scenario matrices and snapshot lists must be **chunked**. Never keep `S` full `MarketSnapshot` graphs (each includes curves/surfaces). |

---

## Top 10 Performance Actions

1. **Single-copy scenario apply** (fix `O(F²)`). Highest leverage for FULL_REVAL and stress.
2. **Stream/chunk shocked markets**; do not materialize `list[MarketSnapshot]` of length S.
3. **Hierarchy from one trade-level pass** (roll-up additive; subset VaR from trade P&L or lazy nodes).
4. **One request-scoped valuation/risk context** for dashboard (or a single risk-run).
5. **Shock once per scenario**, then `value_portfolio`.
6. **Bypass NPV LRU on unique snapshots**; cache QL instrument setup instead.
7. **QL RelinkableHandle / reuse engines** across scenarios; process-parallel FULL_REVAL (ADR 007).
8. **Async jobs** for hierarchy, FULL_REVAL, threat evaluate, var/compare, reverse-multi.
9. **Stop dense `N×S` allocation** except for contribution jobs; chunk those.
10. **Leave the nested-loop C++ kernel as-is** until a profiler shows a real `E×S` product hot path; do not treat SLA-K1 as HTTP VaR capacity.

---

## Recommended Benchmark Suite

Keep `benchmarks/run_scenario_bench.py` for kernel SLA. Add **product-path** benches (separate from unit tests), recording wall, RSS, `value()` counts, snapshot counts:

| ID | Workload | What it proves |
|---|---|---|
| P-DG-10k | 10k equities, 750 obs, Δ-Γ `HistoricalRiskEngine.calculate` | Aggregated path SLA candidate |
| P-DG-100k | 100k equities, 1k obs, Δ-Γ | Greeks + construct + JSON parse |
| P-SNAP-F | `historical_shocked_snapshots` F={50,200,1k} S={50,750} | PERF-001 |
| P-FULL-QL | Mixed 50-trade book, S={50,750}, QuantLib FULL_REVAL | PERF-002 |
| P-HIER | N={100,1k,10k} `HierarchyEngine.build` | PERF-003; JSON bytes |
| P-STRESS | N={9,1k,10k} `StressEngine.run` vs evaluate | PERF-005/008 |
| P-CACHE | FULL_REVAL with cache on/off; hit/miss | PERF-006 |
| P-API | Sync summary vs hierarchy vs `/risk/runs` | PERF-010 |
| P-MEM | `var_report` RSS vs N×S | PERF-009 |
| K-SLA | existing `check_m6_sla.py` | Kernel only; not HTTP |

Do not gate CI on absolute milliseconds. Gate on: relative kernel SLA (optional, host-class), snapshot-apply complexity regression (F=200 S=50 wall ceiling), and hierarchy not calling `calculate` more than `O(trades)` after the roll-up fix.

---

## Suggested Optimization Sequence

Follow **Measure → bottleneck → optimize → benchmark → numerical parity**.

1. **Instrument** `value()` / `apply()` / `calculate` counters on the demo dashboard path (no behavior change).
2. **PERF-005 + PERF-004** (shock once; shared context). Small, immediately reduces duplicate work. Parity: demo artifact.
3. **PERF-006** (don’t LRU unique shocks). Small, stops full-reval slowdown.
4. **PERF-001** (single-copy apply). Unblocks any FULL_REVAL scale. Parity: snapshot hashes.
5. **PERF-003** (hierarchy roll-up). Unblocks the UI’s most expensive call. Parity: additive invariants + subset VaR.
6. **PERF-010** (jobs for remaining heavy endpoints).
7. **PERF-002 + PERF-011** (QL reuse + process-parallel chunks). Only after snapshots are cheap.
8. **PERF-008/009** (contribution multipliers and dense matrices) when FULL_REVAL jobs exist.
9. **Kernel** only if a new name-level `E×F×S` methodology is introduced; then batch ABI, not per-shock Python objects.

Do **not** start with SIMD, OpenMP, or rewriting NumPy Δ-Γ — those are not the bottleneck for the workloads RiskForge claims to care about.

---

## Files inspected (review-only)

Primary paths: `README.md`, `ROADMAP.md`, `BUILD_NOTES.md`, `docs/performance.md`, `benchmarks/`, `backend/app/risk/`, `backend/app/pricing/`, `backend/app/compute/kernel.py`, `backend/native/`, `backend/app/services/`, `backend/app/api/`, `frontend/src/api.js`, `docs/adr/007-quantlib-concurrency.md`.
