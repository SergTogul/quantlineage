# RiskForge Development Roadmap

Authoritative backlog from 2026-09-02. `TASKS.md` is **absent** in this checkout (still referenced by agent docs); do not recreate Milestone 0 work there—use this file going forward.

## Progress

| Milestone | Status |
|-----------|--------|
| Milestone 0 — Prototype Foundation | COMPLETE |
| Milestone 1 — Quant Foundation | **COMPLETE** (2026-09-02) |
| Milestone 2 — VaR, ES & Portfolio Risk | **COMPLETE** (2026-09-02) |
| Milestone 3 — Stress & Threat Engine V3 | **COMPLETE** (2026-09-02) |
| Milestone 4 — Hierarchy, Attribution & Limits | **COMPLETE** (2026-09-02 Lead Architect formal acceptance) |
| Milestone 5 — Persistence & Risk-Run Platform | **COMPLETE** (2026-09-02: M5.1/M9.9 GHA `postgres-persistence-smoke` green; M5.5 non-blocking polish remains) |
| Milestone 6 — C++ Performance Engine | **PARTIAL** (M6.1–M6.7 DONE; no risk-path speed SLA) |
| Milestone 7 — API Productionization | **PARTIAL** (M7.1–M7.5 DONE — dual-mount + typed models + OpenAPI examples + error model; M7.6 legacy sunset open) |
| Milestone 8 — Risk Terminal UI | PARTIAL (firm-root hierarchy; thin hedge/multi/risk-run helpers; risk-run poll card; no change-attr/ES panels) |
| Milestone 9 — Testing, CI & Engineering Quality | PARTIAL (M9.6 + M9.9 DONE — full CI green on GHA; M9.1–M9.5/M9.7/M9.10 still open) |
| Milestone 10 — Demo Data & Reproducibility | NOT STARTED |
| Milestone 11 — AI Risk Assistant | NOT STARTED |
| Milestone 12 — Documentation & Portfolio Presentation | NOT STARTED |
| Milestone 13 — Final Portfolio Demo | NOT STARTED |

### Baseline verification (2026-09-02, local macOS — Lead Architect acceptance)

| Check | Result |
|-------|--------|
| QuantLib | 1.43 import OK |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`) | **160 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **10 passed** |
| Frontend `npm run build` | **OK** |
| C++ via `test_native_kernel` | **passed** (g++/Apple clang 14; earlier same-day baseline; not re-run in this acceptance pass) |
| Manual `g++` of `kernel_test.cpp` without `-I include` | fails include path (docs/README must use `-I include`) |
| Milestone 1 status | **COMPLETE** — see M1 evidence + documented limitations |
| Concurrent M2 note | Suite count includes M2.3/M2.4 tests landed during same-day work; M1 acceptance does not claim Milestone 2 complete |
| `TASKS.md` | missing |
| Prior stub `ROADMAP.md` | replaced by this file |

### Architecture map (evidence-based)

```text
Trade (domain/models.py)
  → PricingEngine (interfaces/pricing.py)
      ├─ QuantLibPricingEngine  [equity, EQ option, ZC bond, IRS, EQ future, FX fwd/opt, IR future]
      └─ BuiltinPricingEngine   [same instrument set]
      ├─ curve_rates / QL ZeroCurve   when MarketSnapshot.curves|key_rates attached
      └─ surface_vol lookup           when MarketSnapshot.vol_surfaces attached
  → MarketSnapshot (frozen + recursive MappingProxy; model_copy re-freezes; typed bump/apply/diff)
  → Risk engines
      ├─ SensitivityEngine  [bump-revalue; key-rate DV01 when curves/key_rates present]
      ├─ HistoricalRiskEngine / VaRAnalytics  [LINEAR / DELTA_GAMMA / FULL_REVALUATION]
      ├─ StressEngine / ReverseStress / Compare
      ├─ Hierarchy / Attribution / Limits / Factors / Query
  → PortfolioService → FastAPI (app/api/* routers; dual-mount legacy + /api/v1)
  → React SPA (single page cards) / optional NativeScenarioKernel (LINEAR/Δ-Γ via RISKFORGE_SCENARIO_KERNEL)
```

### Highest-risk gaps (post–M1–M5 progress)

1. Caps/floors/swaptions still deferred; EquityVol/FXVol bumps do not rewrite surface grids; QL uses `BlackConstantVol` at point σ (not full surface engine); Builtin vs QL bond day-count gap
2. M5 **COMPLETE** (2026-09-02): M5.1/M9.9 GHA `postgres-persistence-smoke` green (https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125); M5.5 valuation LRU only (curve/scenario memo open — non-blocking polish)
3. M6 native kernel wired for LINEAR/DELTA_GAMMA via `RISKFORGE_SCENARIO_KERNEL` (M6.3–M6.7 DONE incl. parity + QL concurrency ADR); FULL_REVALUATION stays Python; **no product risk-path speed SLA claimed**
4. M7.1–M7.5 DONE (router split + dual-mount `/api/v1` + typed response models + OpenAPI examples + `{code,message,details}` errors); M7.6 legacy sunset still open; formal `Scenario` not yet the stress HTTP wire type
5. UI is one scroll dashboard: nav, heatmaps, hedge-compare page, risk-change attribution, ES contributions still missing (risk-run start/poll card landed M8.9)
6. M9.9 **DONE** — full CI green on GHA runners (run 33673245125); static analysis (Ruff/mypy/ESLint) not started; E2E lags new endpoints
7. Multi-factor reverse stress = ray + coordinate descent (documented; not a certified global optimum)

### Suite verification (2026-09-02, Lead Architect — local macOS)

| Check | Result |
|-------|--------|
| Backend pytest (`cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q --tb=line`) | **513 passed** (2026-09-02 M7.3), 1 Starlette/httpx deprecation warning, 0 failed, 0 skipped |
| Frontend `npm test` | **26 passed**, 0 failed |
| Frontend `npm run build` | **OK** (vite; 22 modules) |
| M5 milestone | **COMPLETE** — M5.1/M9.9 GHA green (run 33673245125); M5.5 remains non-blocking polish |
| M5.6 / M5.7 / M5.9 | **DONE** (DI; Postgres `SKIP LOCKED` claim + Compose worker; stress scenario_definitions HTTP) |
| M5.5 | **PARTIAL** (valuation LRU; curve/scenario memo open) |
| M6.1–M6.7 | **DONE** (harness, baseline, risk-path wire, parallel pool, ABI+Historical parity, QL concurrency ADR) |
| M6 milestone | **PARTIAL** — no rubber-stamp COMPLETE / no product VaR wall-time SLA |

---

## Milestone 0 — Prototype Foundation

Status: COMPLETE

Working MVP: PricingEngine seam, QuantLib + builtin adapters (partial QL coverage), MarketSnapshot + shock, 7 instruments, synthetic VaR/ES + component VaR, stress/threat/custom/reverse/hedge-compare, hierarchy, attribution, limits, NL keyword query, Python + optional C++ scenario kernel, FastAPI, React terminal, backend/frontend/e2e tests.

Deficiencies discovered are assigned to later milestones (do not redo M0).

---

## Milestone 1 — Quant Foundation

Status: **COMPLETE** (Lead Architect acceptance 2026-09-02)

Critical review items closed with code evidence:

1. Nested `curves` / `vol_surfaces` deep-frozen via recursive `MappingProxyType`; `model_copy` re-applies freeze
2. `RateZero` tenor bumps isolate pillars; `PARALLEL`/`ALL` parallel-shift scalar + pillars + matching curve zeros
3. Key-rate DV01 uses tenor bumps when curves/key_rates present (`KEY_RATE_CURVES_CONSUMED_BY_PRICING=True`); Builtin/QL bond/swap consume curves; options consume `vol_surfaces`

### Tasks

- [x] M1.1 Local production dependency verification
  - Evidence (2026-09-02 acceptance): QuantLib 1.43; backend **160 passed** with `RISKFORGE_PRICING_ENGINE=quantlib`; frontend `npm test` **10 passed**; `npm run build` OK
- [x] M1.2 Complete QuantLib instrument coverage
  - EquityFuture / FXForward / FXOption: native QL paths (no Builtin fallback); tight parity tests
  - InterestRateFuture: domain + Builtin/QL adapters (algebraic STIR mark; full QL FRA still deferred)
  - Caps/floors/swaptions: **deferred** (documented limitation) until richer IR vol / exercise modeling
  - Builtin `pay_fixed=True` aligned to standard payer economics (matches QuantLib)
- [x] M1.3 Formal market-data domain
  - Frozen `MarketSnapshot` with recursive deep-freeze; bump/apply/diff/content_hash; sub-market views
  - RateZero: `PARALLEL`/`ALL` vs specific tenors (no silent parallel on tenor bumps)
  - Pricing consumes attached curves/key_rates (bonds/swaps) and vol surfaces (EQ/FX options) when present; scalars remain fallback
  - Evidence: `tests/test_market_snapshot.py`; ADR 002
- [x] M1.4 Yield curves
  - USD OIS/SOFR scaffolds, key tenors, linear zeros, triangular key-rate shocks; attach → `curves`/`key_rates`
  - Builtin `discount_factor` / `continuous_zero`; QuantLib `_curve_handle` / `ZeroCurve` when attached
  - Limitation (accepted for M1): flat zeros / no market-instrument bootstrap yet
  - Evidence: `tests/test_curves.py`, `tests/test_curve_pricing.py`
- [x] M1.5 Volatility surfaces
  - Equity/FX expiry × moneyness grids; parallel / expiry-bucket / skew / term shocks; bilinear lookup
  - `attach_vol_surface`; Builtin + QuantLib option paths via `surface_vol.option_vol_from_snapshot`
  - Limitation: flat/scaffolding grids only — no SABR/local-vol calibration
  - Evidence: `tests/test_vol_surfaces.py`, `tests/test_surface_vol_pricing.py`
- [x] M1.6 Typed risk-factor taxonomy
  - Evidence: typed `RiskFactor` in `backend/app/risk/factor_types.py`; `RiskFactorEngine` migrated (API still string keys); `test_factor_types.py`
- [x] M1.7 Unified bump-and-revalue sensitivity engine
  - delta/gamma/vega/DV01/FX delta; key-rate DV01 uses true tenor bump + `method=bump_revalue` when tenor available
  - Honest parallel fallback (`bump_revalue_parallel_fallback`) only when no `key_rates`/curve pillar for that tenor
  - Flag `KEY_RATE_CURVES_CONSUMED_BY_PRICING=True`
  - Evidence: `tests/test_sensitivities.py` (isolation + swap tenor + missing-fallback cases)
- [x] M1.8 Quant correctness tests
  - Hypothesis properties + FD Greek reconciliation (`test_quant_properties.py`); QuantLib golden BS/GK + Builtin cross-check (`test_quantlib_golden.py`); `hypothesis>=6.112,<7` in `requirements.txt`
  - Conventions: cash delta/gamma/vega; discounted European intrinsic; `pay_fixed=True` = payer

### Acceptance Criteria

- [x] QuantLib adapters for EquityFuture, FXForward, FXOption behind `PricingEngine` with reference comparison tests
- [x] Domain models for IR future; cap/floor/swaption **documented deferral** under M1.2
- [x] Immutable market domain with bump/diff (deep freeze of nested curve/surface payloads; `model_copy` re-freezes)
- [x] USD OIS/SOFR curve scaffolding; equity/FX vol surface scaffolding
- [x] Typed `RiskFactor` abstraction used by risk vectors
- [x] Sensitivity engine for delta/gamma/vega/DV01/honest key-rate DV01/FX delta
- [x] Property/golden tests green under QuantLib

### Documented M1 limitations (not blockers)

- Caps/floors/swaptions not priced
- Curves are flat-zero scaffolds (no bootstrap from deposits/futures/swaps)
- Vol surfaces are scaffolding grids (no SABR/local-vol)
- QuantLib IR future remains algebraic STIR (not full FRA/futures engine)
- Without attached curves/key_rates, key-rate DV01 correctly falls back to parallel and tags the method
- `MarketSnapshot.bump(EquityVol|FXVol)` updates scalar vols only — attached `vol_surfaces` grids are unchanged (pricing still reads grid when present)
- QuantLib options use `BlackConstantVol` at surface-lookup σ, not a QL surface/interpolation engine
- Builtin ZC bond uses simple compound `(1+y)^T`; QL uses continuous/`Actual365Fixed` — golden tests allow ~5% relative band

### Follow-on tasks (discovered during M1–M5; do not reopen M1 acceptance)

- [ ] M1.9 Caps / floors / swaptions pricing (IR vol + exercise)
  - Why: deferred under M1.2; needs richer IR vol / exercise modeling before domain+adapters
- [ ] M1.10 Surface-aware EquityVol / FXVol bumps rewrite attached `vol_surfaces` grids
  - Why/evidence: `MarketSnapshot.bump` only scales `equity_vols`/`fx_vols`; `test_surface_vol_pricing.py` documents the gap — stress/vega paths can diverge when grids are attached
- [ ] M1.11 QuantLib full surface / smile engine (replace point `BlackConstantVol`)
  - Why/evidence: `quantlib.py` builds `BlackConstantVol` from `surface_vol.option_vol_from_snapshot` σ; not a QL `BlackVarianceSurface` (or equiv.)
- [ ] M1.12 Align Builtin vs QuantLib ZC bond day-count / compounding conventions
  - Why/evidence: `test_quantlib_golden.py` bond case uses `rel=5e-2` vs simple-compound reference; document or close the convention gap
- [ ] M1.13 Curve bootstrap from market instruments (replace flat-zero scaffolds)
  - Why: accepted M1.4 limitation; deposits/futures/swaps bootstrap still open

---

## Milestone 2 — VaR, ES & Portfolio Risk

Status: **COMPLETE** (2026-09-02 Lead Architect formal acceptance)

### Tasks

- [x] M2.1 Historical market dataset abstraction
  - `backend/app/risk/historical_data.py`: `FactorObservationSeries`, `HistoricalMarketDataset` protocol, `SyntheticHistoricalDataset`, `ArrayHistoricalDataset`
  - Separates factor observations from scenario generation (M2.2) and valuation (`HistoricalRiskEngine` / `VaRAnalytics`)
  - Aggregate equity/FX returns, vol moves, parallel rate bp moves only — no key-rate / tenor dependency required for aggregate path
  - `HistoricalRiskEngine` + `VaRAnalytics` consume dataset; default synthetic preserves prior seeded RNG
  - Evidence: `tests/test_historical_data.py` (7) + risk regression green (2026-09-02)
- [x] M2.2 Historical scenario generation
  - `backend/app/risk/scenarios.py`: `AggregateFactorChange` → typed `MarketScenario` / `FactorChange` → shocked `MarketSnapshot[]`
  - Expands aggregate observation moves onto factors present in a base snapshot; applies via `MarketSnapshot.apply` (bump units); `to_stress_scenario` bridges `shock_snapshot`
  - Does **not** alter Δ-Γ VaR (`HistoricalRiskEngine` / `VaRAnalytics`); empty scenario preserves `content_hash`
  - Evidence: `tests/test_scenarios.py`
- [x] M2.3 Full-revaluation Historical VaR
  - Explicit `VaRMethodology`: `LINEAR` | `DELTA_GAMMA` (default, legacy Δ-Γ) | `FULL_REVALUATION`
  - `FULL_REVALUATION` reprices via `PricingEngine` on M2.2 `historical_shocked_snapshots`
  - Methodology on `RiskSummary` / `VaRReport`; query param on `/risk/summary`, `/risk/var`
  - Evidence: `tests/test_var_methodology.py`
- [x] M2.4 VaR comparison (Linear / Δ-Γ / Full reval)
  - `backend/app/risk/var_compare.py`: `compare_methodologies()` — shared dataset, times each mode (delegates P&L to M2.3 `HistoricalRiskEngine`)
  - DTOs: `VaRMethodologyMetrics`, `VaRMethodologyComparison`; service + `POST /risk/var/compare`
  - Returns per methodology: VaR95, VaR99, ES99, `runtime_ms`, methodology label
  - Evidence: `tests/test_var_compare.py`
- [x] M2.5 Expected Shortfall contributions
  - `backend/app/risk/es.py`: historical tail-conditional ES by position / book / strategy / desk / risk factor
  - LINEAR/DELTA_GAMMA: additive Greek factor P&L; FULL_REVALUATION: factor-isolated reval + `interaction` residual
  - DTOs: `ESContribution`, `ESContributionReport`; `PortfolioService.es_contributions()`; `POST /risk/es` (optional `methodology` query)
  - Position-level `component_es` also on `RiskContribution` in `VaRReport`
  - Reconciliation: contribution sum ≈ portfolio ES (abs 1e-6 / rel 1e-8)
  - Evidence: `tests/test_es_contributions.py` (service + API)
- [x] M2.6 Component VaR
  - Euler / covariance allocation of **parametric** VaR on methodology P&L series (`LINEAR` | `DELTA_GAMMA` | `FULL_REVALUATION`)
  - `CVaR_i = VaR · Cov(X_i, X) / Var(X)`; Σ CVaR = parametric VaR (not historical quantile VaR)
  - Shared helpers in `backend/app/risk/marginal_var.py`; `VaRAnalytics.report` contributions
  - Evidence: `tests/test_component_var.py` — reconciliation under Δ-Γ and full reval; single-position / zero-shock edges
- [x] M2.7 Marginal VaR
  - `MVaR_i = ∂VaR/∂w_i|_{w=1} = z · Cov(X_i, X) / σ`; at current holdings `MVaR_i = CVaR_i`
  - `RiskContribution.marginal_var` (default 0.0, append-only); FD helper `finite_difference_marginal_var`
  - Methodology documented in `marginal_var.py` module docstring
  - Evidence: `tests/test_marginal_var.py`
- [x] M2.8 Incremental VaR
  - `backend/app/risk/incremental_var.py`: `apply_what_if_changes`, `incremental_var`, `what_if_analysis`
  - Methodology: IVaR = VaR(P′) − VaR(P) (same for VaR95 / ES99); positive ⇒ risk-increasing; input portfolio never mutated
  - Delegates P&L/quantiles to `HistoricalRiskEngine`; default methodology `DELTA_GAMMA`
  - Evidence: `tests/test_incremental_var.py`
- [x] M2.9 What-if API `POST /risk/what-if` (M7.2 will version under `/api/v1`)
  - DTOs: `WhatIfRequest` / `WhatIfReport` (+ incremental metrics, factor exposure & stress loss diffs)
  - Supports add/remove/modify hypothetical trades without mutating persisted/sample portfolio
  - Returns before risk, after risk, incremental risk, changed factor exposures, changed stress losses
  - Optional methodology via body or query override
  - Evidence: `tests/test_what_if.py`

### Acceptance Criteria

Methodology-selectable VaR/ES with contribution reconciliation; what-if without mutating persisted portfolio.

### Formal acceptance evidence (2026-09-02)

| Check | Result |
|-------|--------|
| M2.1–M2.9 checklist | All `[x]` with file/test evidence in ROADMAP |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`) | **219 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **10 passed** |
| Frontend `npm run build` | **OK** |
| M2.5 API gap closed | `POST /risk/es` wired to `PortfolioService.es_contributions()` |
| Known residual | Dual-mount `/api/v1` landed in M7.2; M7.6 legacy sunset still open |

---

## Milestone 3 — Stress & Threat Engine V3

Status: **COMPLETE** (2026-09-02 Lead Architect formal acceptance)

### Tasks

- [x] M3.1 Formal Scenario domain model
  - `backend/app/risk/scenario_model.py`: `Scenario` with id/name/category/description/`FactorShock[]`/threshold/severity/metadata
  - Shocks reference typed `RiskFactor` (`factor_types.py`); apply via `MarketSnapshot.apply`
  - Adapters to/from legacy `StressScenario` and M2.2 `MarketScenario` (existing stress APIs unchanged)
  - Severity bands aligned with StressEngine threat levels; ADR 004
  - Evidence: `tests/test_scenario_model.py`
- [x] M3.2 Multi-factor scenario engine
  - `backend/app/risk/scenario_engine.py`: `ScenarioEngine` / `apply_scenario` / `expand_scenario` / `shocked_snapshots`
  - Primary path: formal `Scenario` / `FactorShock` via M3.1 `scenario_model.apply_scenario`
  - Also accepts legacy `StressScenario`, M2.2 `MarketScenario` / `FactorChange`, and `(RiskFactor, amount)` pairs
  - Combined equity + rates + FX + vol → shocked `MarketSnapshot` via `MarketSnapshot.apply` / `bump`
  - Canonical expansion for `StressScenario` (`scenario_from_stress`); caller order for explicit lists; independent scenarios
  - `shock_snapshot` delegates to engine (StressScenario APIs unchanged); re-exported from `stress.py`
  - Evidence: `tests/test_scenario_engine.py`
- [x] M3.3 Historical crisis library
  - `backend/app/risk/crisis_library.py`: documented presets (Lehman 2008, COVID Mar-2020, 2022 rates, Euro 2011, Volmageddon 2018, China 2015, dot-com-style)
  - Formal `Scenario` category `HISTORICAL_APPROXIMATION` for all crisis presets; observation series → `HISTORICAL_REPLAY`
  - Honest disclaimers; never present approximations as exact replays; wired into `THREAT_SCENARIOS`
  - Evidence: `tests/test_crisis_library.py`
- [x] M3.4 Scenario contribution decomposition
  - `backend/app/risk/scenario_attribution.py`: hierarchy (portfolio/desk/strategy/book/trade) + risk-factor decomposition
  - Factor path: isolated full reval per typed `RiskFactor.key` + `interaction` residual
  - Formal `Scenario` and legacy `StressScenario` inputs; wired into `StressEngine.evaluate` / `contributions`
  - DTOs: `ScenarioContribution`, `ScenarioContributionBreakdown` on `StressEvaluation.contributions`
  - Evidence: `tests/test_scenario_attribution.py` (reconciliation abs 1e-6 / rel 1e-8)
- [x] M3.5 Reverse stress single-factor
  - `backend/app/risk/reverse_stress.py`: binary-search solver on typed `FactorShock` / formal `Scenario` (REVERSE)
  - Returns target loss (absolute), wire-compatible `required_shock`, resulting P&L, convergence diagnostics
  - Units: equity/vol/fx relative; rates in bp (legacy `max_shock=0.80` → 800bp bound)
  - `ReverseStressEngine` re-exported from `stress.py`; `/risk/stress/reverse` unchanged
  - Evidence: `tests/test_reverse_stress.py`
- [x] M3.6 Reverse stress multi-factor
  - `backend/app/risk/reverse_stress_multi.py`: constrained L2 ray search + coordinate descent
  - Documented assumptions on result; adverse orthant; reuses M3.5 shock builders (no single-factor rewrite)
  - API: `POST /risk/stress/reverse/multi`; re-exported from `stress.py`
  - Evidence: `tests/test_reverse_stress_multi.py`
- [x] M3.7 Hedge comparison
  - `ScenarioComparisonEngine` → `HedgeComparisonReport`: hedge_cost, base/hedged VaR & ES, scenario loss, factor exposure deltas
  - Legacy per-scenario pnl/improvement fields retained inside `scenarios[]`
  - API: `POST /risk/stress/compare` returns report (not bare list)
  - Evidence: `tests/test_hedge_comparison.py`

### Acceptance Criteria

Flagship stress with typed multi-factor shocks, honest crisis labeling, reconciled contributions, single- and multi-factor reverse stress, strengthened hedge compare.

### Formal acceptance evidence (2026-09-02)

| Check | Result |
|-------|--------|
| M3.1–M3.7 checklist | All `[x]` with file/test evidence in ROADMAP; focused suite **78 passed** |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`, QuantLib 1.43) | **282 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **10 passed** |
| Frontend `npm run build` | **OK** |
| Breaking API shape | `POST /risk/stress/compare` returns `HedgeComparisonReport` object (not bare `ScenarioComparison[]`); legacy per-scenario fields live under `scenarios[]` |
| Multi-factor reverse limitations | Adverse orthant only; monotonicity assumed not proven; ray + coordinate descent is not a certified global optimum; assumptions echoed on result |
| Known residual | Hedge-compare UI still absent (M8.5); dual-mount `/api/v1` (M7.2 DONE; M7.6 sunset open); formal `Scenario` not yet stress HTTP wire type (M3.8) |
| Hierarchy | Left untouched in M3 acceptance — M4.2 later fixed hierarchy↔stress via lazy import (no residual circular-import gap) |

### Follow-on tasks (discovered during M1–M5)

- [ ] M3.8 Expose formal `Scenario` as stress HTTP wire type (versioned `/api/v1`)
  - Why/evidence: ADR 004 keeps `StressScenario` as stable wire DTO; adapters exist; HTTP still legacy shape
- [ ] M3.9 Publish multi-factor reverse-stress limitations in methodology docs (not a fake “complete optimizer”)
  - Why/evidence: M3.6 acceptance + `reverse_stress_multi.py` — ray search + coordinate descent, adverse orthant, monotonicity assumed; **not** a certified global optimum. Keep M3.6 `[x]`; document for users/interviewers (pairs with M12.4 / M12.6)

---

## Milestone 4 — Hierarchy, Attribution & Limits

Status: **COMPLETE** (2026-09-02 Lead Architect formal acceptance)

### Tasks

- [x] M4.1 First-class hierarchy — DONE (Firm→Portfolio→Desk→Strategy→Book→Trade; position desk/strategy with portfolio defaults; HierarchyRef / portfolio_at / risk_at; MV reconciliation; ES multi-desk rollups)
- [x] M4.2 Hierarchical risk aggregation — DONE
  - Each `HierarchyNode` carries NAV, Greeks (`delta`/`gamma`/`vega`/`dv01`/`fx_delta`), `var_95`/`var_99`/`expected_shortfall_99`, default-scenario `stress`, and `limits`
  - Additive reconciliation (parent == sum children, abs 1e-9): MV, Greeks, stress P&L
  - Non-additive (node subset): VaR, ES, limits — match `risk.calculate` / `LimitEngine` / `StressEngine.run`
  - Firm root aligned with M4.1; lazy stress import avoids circular import with scenario_attribution
  - Evidence: `tests/test_hierarchy.py`
- [x] M4.3 P&L Explain v2 — DONE
  - `AttributionEngine.explain`: actual P&L = PV(curr,cm)−PV(prev,pm); market bridge on previous book via Delta/Gamma/Vega/Rates/FX/Theta; trade flow New/Closed trades (incl. size changes)
  - Reconciliation: `explained_change + residual == total_change` (Taylor residual absorbs higher-order / duration-DV01 gaps)
  - API compat: `AttributionRequest`/`AttributionReport`/`POST /risk/attribution` + demo; additive optional `dt_years` for theta
  - Evidence: `tests/test_attribution.py`; regression `test_next_phase.py` attribution cases
- [x] M4.4 Risk change attribution — DONE
  - New `backend/app/risk/risk_attribution.py` (separate from P&L `attribution.py`)
  - Waterfall: closed / position changes / new trades → equity / vol / rates / FX → correlation residual
  - Metric: `var_99` | `var_95` | `expected_shortfall_99`; market-aware Greeks when snapshot provided
  - Invariants: identical state → ~0; drivers reconcile to total Δ within abs 1e-6 / rel 1e-8
  - Service: `PortfolioService.risk_change_attribution`; API `POST /risk/change-attribution` (`RiskChangeAttributionRequest`)
  - Evidence: `tests/test_risk_attribution.py` (incl. API contract)
- [x] M4.5 Configurable risk limits — DONE
  - `LimitEngine`: firm/desk VaR, ES, DV01, key-rate DV01, concentration, vega, FX, stress loss
  - Status OK / WARNING / BREACH via configurable `warning_threshold_pct` (default 80%)
  - Hierarchy reuses node stress for `stress_loss`; `breached` kept for API compat
  - Evidence: `tests/test_limits.py`, `tests/test_risk.py`, `tests/test_hierarchy.py`
- [x] M4.6 Limit drill-down — DONE
  - `limit_drilldown.py` consumes `LimitResult` + hierarchy subset + metric contributors
  - Breach (or selected metric) shows: hierarchy node/path, metric, value, limit, utilization %, top contributors
  - Contributor rules: VaR/ES → component VaR/ES; Greeks → abs greek; `single_position_pct` → abs MV share; `stress_loss` → worst-scenario position losses
  - Consumes M4.5 `LimitResult` (status/warning/scope/label preserved on value/limit/utilization/breached)
  - Optional `POST /risk/limits/drilldown` (`LimitDrilldownRequest` / `LimitDrilldownReport`)
  - Evidence: `tests/test_limit_drilldown.py`

### Acceptance Criteria

Firm→trade hierarchy with additive MV/Greek/stress reconciliation; P&L Explain v2; risk-change VaR/ES waterfall; configurable OK/WARNING/BREACH limits; breach drill-down with top contributors.

### Formal acceptance evidence (2026-09-02)

| Check | Result |
|-------|--------|
| M4.1–M4.6 checklist | All `[x]` with file/test evidence in ROADMAP |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`, QuantLib 1.43) | **324 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **22 passed** |
| Integration unblock during acceptance | Renamed Alembic scripts dir `backend/alembic` → `backend/migrations` (avoids shadowing installed `alembic` package; `alembic.ini` + `test_persistence.py` updated) |
| Known residual — P&L Explain | Taylor residual absorbs higher-order / duration–DV01 gaps; not a full-reval explain |
| Known residual — risk-change attribution | Correlation residual is plug-to-total; not a structural corr model; linear/Greek market path when snapshot present |
| Known residual — limits UI | Full limits / drill-down UX still M8; API + thin frontend helpers only |
| Known residual — key-rate contributors | `limit_drilldown.contributors_for_metric` maps `key_rate_dv01` → position `dv01` (parallel), not tenor KR DV01 (M4.7) |
| Known residual | Dual-mount `/api/v1` (M7.2 DONE; M7.6 sunset open); RiskRun persistence wiring still M5 |
| Hierarchy ↔ stress | Circular import fixed in M4.2 via lazy stress import — no open hierarchy/stress residual |

### Follow-on tasks (discovered during M1–M5)

- [ ] M4.7 Key-rate DV01 limit drill-down contributors use tenor KR DV01 (not parallel `dv01`)
  - Why/evidence: `limit_drilldown.py` `_GREEK_METRICS` / `attr = "dv01" if metric == "key_rate_dv01"`; misleading when curves/key_rates are present

---

## Milestone 5 — Persistence & Risk-Run Platform

Status: **COMPLETE** (2026-09-02 DevOps) — GHA `postgres-persistence-smoke` + full CI green; M5.5 remains non-blocking polish

Task rollup: M5.1–M5.4 / M5.6 / M5.7 / M5.9 **DONE**; M5.5 **PARTIAL** (non-blocking polish only).

### Tasks

- [x] M5.1 PostgreSQL persistence (SQLAlchemy + Alembic) — DONE
  - New package `backend/app/persistence/` (config, session, ORM models, repository ABCs + SQLAlchemy repos)
  - Tables: portfolios, trades, market_snapshots (meta + JSON data), scenario_definitions, risk_runs, risk_results, limit_definitions
  - Alembic initial revision `001_initial_persistence` under `backend/migrations/` (not `alembic/`, to avoid package shadowing); SQLite-capable unit tests (no live Postgres required in unit suite)
  - Compose `postgres` service + `RISKFORGE_DATABASE_URL` (psycopg3); ADR 005
  - Postgres CI: `postgres-persistence-smoke` job in `.github/workflows/ci.yml` + `scripts/smoke_postgres.sh` (wait-for-pg → Alembic `backend/migrations/` upgrade head → seed wiring). **Local Compose smoke green** (2026-09-02 DevOps). **GHA green** (2026-09-02): https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125 (job https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125/job/100391676176) — M9.9 residual **CLOSED**
- [x] M5.2 RiskRun domain model — DONE
  - Domain DTOs: `RiskRunStatus`, `RiskResultRef`, `RiskRun` in `domain/models.py`
  - Lifecycle validation (QUEUED/RUNNING/COMPLETED/FAILED), computed `duration`
  - Persistence mapping: `completed_at`↔`finished_at`, `error`↔`error_message`, result refs
  - ORM columns + Alembic `002_risk_run_domain_fields` (append-only; 001 untouched)
  - Repository `create`/`get`/`set_status` return domain `RiskRun`
  - Evidence: `tests/test_risk_run.py`, `tests/test_persistence.py`
- [x] M5.3 Risk run lifecycle (QUEUED/RUNNING/COMPLETED/FAILED) — DONE
  - `RiskRunService` (`enqueue`/`start`/`complete`/`fail`/`get`/`get_result_payloads`)
  - Directed transitions only; illegal transitions raise `InvalidRiskRunTransition`
  - Evidence: `tests/test_risk_run_lifecycle.py`
- [x] M5.4 Async risk execution APIs — DONE (default in-memory; SQLAlchemy path covered in tests)
  - `POST/GET /risk/runs` + `/api/v1/risk/runs` (M7.2 dual-mount for all public routers)
  - In-process `RiskRunWorker` (ThreadPoolExecutor) → `RiskRunService` → `PortfolioService` dispatch
  - `run_type`: summary, var, stress, factors, limits, hierarchy, contributors
  - Default: `InMemoryRiskRunRepository`; optional `session_factory` → SQLAlchemy repos + result payloads
  - DTOs: `RiskRunCreateRequest` / `RiskRunView` (`from_risk_run`)
  - Evidence: `tests/test_risk_run_api.py`
  - Residuals deferred: optional Redis/RQ for fair scheduling / ops; M5.6 wires default Postgres DI when ``RISKFORGE_DATABASE_URL`` is set
  - Multi-worker claim safety landed under **M5.7** (`claim_queued` + `FOR UPDATE SKIP LOCKED`)
- [x] M5.5 Caching with invalidation tests — PARTIAL
  - `CachedPricingEngine` in `backend/app/pricing/cache.py` wraps any `PricingEngine` (no QuantLib leakage)
  - Cache key = trade payload hash + `MarketSnapshot.content_hash` + `PricingConfiguration` (engine id / evaluation date / extras)
  - Factory opt-in via `RISKFORGE_PRICING_CACHE` (default on) + `RISKFORGE_PRICING_CACHE_SIZE`
  - Correctness: hit/miss, market-bump miss, config miss, LRU eviction, clear — `tests/test_pricing_cache.py`
  - **Not yet:** dedicated curve-construction cache; scenario-engine invariant memo beyond valuation LRU
- [x] M5.6 Wire persistence repositories into FastAPI DI / services — **DONE**
  - Optional DI: ``RISKFORGE_DATABASE_URL`` set → SQLAlchemy session factory + seeded sample portfolio / market snapshot / DEFAULT+THREAT scenarios / DEFAULT_LIMITS + ``RiskRunWorker(session_factory=…)``
  - Unset → ``SAMPLE_PORTFOLIO`` + in-memory snapshot/scenario/limit repos (pre-seeded) + ``InMemoryRiskRunRepository`` (default tests unchanged)
  - ``Depends``: ``get_default_portfolio``, ``get_default_market_snapshot``, ``get_market_snapshot_repository``, ``get_scenario_definition_repository``, ``get_limit_definition_repository``, ``get_risk_run_worker``; repos also on ``app.state`` when memory-backed
  - Worker upserts portfolio on submit when SQLAlchemy-backed (FK to ``portfolios``)
  - Evidence: `tests/test_persistence_di.py`; ADR 005 updated
- [x] M5.7 Compose (or process) risk-run worker after M5.4 stabilizes — **DONE**
  - Compose `worker` service: `python -m app.worker` claims `QUEUED` risk_runs from shared Postgres (`RISKFORGE_DATABASE_URL`)
  - Same `RiskRunWorker` + SQLAlchemy session factory as API lifespan; portfolio loaded from DB on cache miss
  - Compose `backend` sets `RISKFORGE_EXTERNAL_WORKER=1` (HTTP enqueues only); unset → in-process ThreadPoolExecutor (tests/local default)
  - Repo `claim_queued` (memory + SQLAlchemy): QUEUED→RUNNING; **Postgres** uses `SELECT … FOR UPDATE SKIP LOCKED` so concurrent workers do not double-claim; SQLite/unit path is FIFO without skip-locked (documented)
  - Compose ships one worker by default (demo); Redis/RQ **not** required for claim safety
  - Evidence: `tests/test_durable_worker.py` (poll + memory exclusive claim + SQLite claim + mocked postgres `skip_locked`)
  - Residual: multi-worker live stress beyond claim-unit tests optional; GHA Postgres path proven via `postgres-persistence-smoke` (M9.9 **DONE**)

### Acceptance Criteria (milestone bar)

Durable persistence + async risk-run platform: SQLAlchemy/Alembic schema, RiskRun domain/lifecycle, async run APIs, FastAPI DI for persistence-backed services, compose/process worker with Postgres claim safety (`FOR UPDATE SKIP LOCKED`), and caching with invalidation tests. Postgres path exercised beyond SQLite (local Compose smoke + GHA `postgres-persistence-smoke`). Milestone **COMPLETE**; M5.5 curve/scenario memo remains non-blocking polish.

### Formal acceptance decision (2026-09-02) — **COMPLETE** (cleared after M9.9 GHA green)

**Verdict (initial):** Do **not** rubber-stamp COMPLETE. Tests were green and the risk-run spine (M5.2–M5.4) was done, but DI for snapshots/scenarios/limits and Postgres CI proof were open.

**Update same day (Backend/API M5.6 close):** M5.6 DI blocking gap is **CLOSED**. Remaining blockers were Postgres runner validation (M9.9), M5.7 multi-worker claim, and optional M5.5 cache polish. Milestone stays **IN PROGRESS**.

**Suite verify same day (Lead Architect):** Full backend **426 passed** + frontend **26 passed** + build OK. M5.9 confirmed **DONE**. Did **not** clear M5.1/M9.9 or (then) M5.7 blockers → milestone remained **IN PROGRESS**.

**Update same day (Backend/API M5.7 claim safety):** M5.7 multi-worker claim blocker is **CLOSED** via Postgres `FOR UPDATE SKIP LOCKED` on `claim_queued` (Compose single-worker demo unchanged; SQLite fallback documented). Remaining milestone blocker: **M5.1 / M9.9** Postgres runner green. M5.5 remains non-blocking polish.

**Update same day (DevOps M9.9 attempt):** Local `scripts/smoke_postgres.sh` against Compose `postgres:16-alpine` **passed** (Alembic 001→002 + seed portfolio/snapshot/scenarios/limits). CI workflow hardened (psycopg wait + version print). **M9.9 still NOT DONE** — this checkout has **no `git remote` / no `gh` CLI**, so no GitHub Actions run history and no push to obtain runner evidence. Do **not** mark Milestone 5 COMPLETE until a green `postgres-smoke` (and ideally full CI) GHA URL is recorded. M5.5 alone remains non-blocking polish.

**Update same day (DevOps M9.9 close):** Origin https://github.com/SergTogul/riskforge-mvp ; push `31228fb`; CI run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125 — jobs `postgres-persistence-smoke`, `backend-pytest`, `frontend-test-build` all green. **M9.9 DONE**; **M5.1 residual CLOSED**; Milestone 5 marked **COMPLETE**. M5.5 stays non-blocking polish.

| Check (initial formal pass) | Result |
|-------|--------|
| QuantLib | 1.43 import OK |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`) | **403 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **26 passed** |
| M5.2–M5.4 | **DONE** — domain, lifecycle, async APIs + tests |
| M5.1 | **PARTIAL** — schema/repos/Alembic/Compose Postgres; Postgres CI job was missing at formal pass |
| M5.5 | **PARTIAL** — valuation LRU + invalidation tests; no curve-construction / scenario memo cache |
| M5.6 (at formal pass) | **PARTIAL** — portfolios + risk_runs DI only |
| M5.7 (at formal pass) | **PARTIAL** — Compose poll worker + `test_durable_worker.py`; no `SKIP LOCKED` yet |
| Milestone status | **IN PROGRESS** |

### Progress update (2026-09-02, Backend/API — M5.6 close)

| Check | Result |
|-------|--------|
| M5.6 | **DONE** — FastAPI DI + seeding for portfolios, risk_runs, market_snapshots, scenario_definitions, limit_definitions |
| M5.1 Postgres CI | **DONE** — Compose local green + GHA `postgres-persistence-smoke` success (run 33673245125) |
| Backend pytest (builtin, this change) | **410 passed** at formal pass; ~7 native/C++ failures on Apple clang 14 (`std::jthread` / missing `-I include`) were **pre-existing**, unrelated to DI — **resolved** by M6.4 portable stdlib thread pool (`__cpp_lib_jthread` fallback to `std::thread`+join) + compile flags with `-I native/include` |
| Evidence | `tests/test_persistence_di.py`; ADR 005 |

### Progress update (2026-09-02, Backend/API — M5.7 claim safety)

| Check | Result |
|-------|--------|
| M5.7 | **DONE** — `claim_queued` + Postgres `FOR UPDATE SKIP LOCKED`; Compose worker poll uses claim; in-process submit path unchanged |
| SQLite / unit | FIFO claim without skip-locked (documented); mocked postgresql dialect asserts `skip_locked=True` |
| Evidence | `tests/test_durable_worker.py`; ADR 005; README / Compose comments |

### Remaining items after COMPLETE

1. ~~**M5.1 / M9.9 (blocking):**~~ **CLOSED 2026-09-02** — GHA run https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125 (`postgres-persistence-smoke` green).
2. **M5.5 (non-blocking polish):** Curve-construction cache and/or scenario-engine memo — optional; does not reopen Milestone 5 COMPLETE.

~~**M5.6 (blocking):** Wire market_snapshots / scenario_definitions / limit_definitions repositories into FastAPI DI~~ **CLOSED 2026-09-02.**

~~**M5.7 (blocking for “platform”):** Safe queue claim (`FOR UPDATE SKIP LOCKED` and/or Redis/RQ) or accepted single-worker caveat~~ **CLOSED 2026-09-02** (`claim_queued` + Postgres `SKIP LOCKED`).

### Follow-on (post-COMPLETE; do not use to skip blocking items above)

- [ ] M5.8 API versioning of risk-runs only under `/api/v1` (superseded by M7.2 full dual-mount; M7.6 may sunset legacy)
- [x] M5.9 Persist stress/scenario HTTP payloads via scenario_definitions DI once M5.6 closes — **DONE 2026-09-02**
  - ``GET /risk/stress/scenarios`` and ``POST /risk/stress/evaluate`` load via ``get_default_stress_scenarios`` → ``scenario_definition_repo`` (memory or SQLAlchemy seed)
  - ``POST /risk/stress`` uses ``get_baseline_stress_scenarios`` (DEFAULT-id filter on the same DI list; empty/missing → in-code ``DEFAULT_SCENARIOS``)
  - Empty or unconfigured repo falls back to in-code ``THREAT_SCENARIOS`` for GET/evaluate (no 503 on stress defaults)
  - Evidence: ``tests/test_stress_scenarios_di.py``
  - Frontend: dashboard does not call GET scenarios; Stress/Threat cards consume POST results only — no display-helper change

---

## Milestone 6 — C++ Performance Engine

Status: **PARTIAL** (M6.1–M6.7 DONE; no risk-path speed SLA claimed)

Lead Architect suite verify 2026-09-02: native path covered by green full backend suite (includes `test_native_kernel` / Historical VaR kernel tests). M6.5/M6.6 closed same day (parity edge cases + ADR 007). Milestone stays **PARTIAL** — do not claim COMPLETE or product VaR wall-time wins.

### Tasks

- [x] M6.1 Benchmark harness under `benchmarks/` — DONE
  - Repo-root `benchmarks/run_scenario_bench.py` + `benchmarks/README.md` (env caveats; not production SLAs)
  - Workloads: `smoke`, `1k_x_1k`, `10k_x_1k`, optional `50k_x_1k`
  - Metrics: wall time, throughput (ops/s & scenarios/s), peak RSS, speedup vs Python
  - Impls: Python reference, NumPy, ctypes (`risk_kernel_capi`), C++ header binary (enhanced `native/src/benchmark.cpp`)
  - Smoke: `python3 -m pytest benchmarks/test_bench_smoke.py -q` (separate from product unit suite)
  - Does not touch M5.4 risk-run APIs
- [x] M6.2 Baseline Python / NumPy / C++ single-thread comparison — DONE
  - Formal I/O contract + results table: `benchmarks/RESULTS.md` (not production SLA)
  - Workloads captured: `1k_x_1k`, `10k_x_1k` (`OMP_NUM_THREADS=1`)
  - Documents NumPy strength-reduction caveat (rewrite ≠ nested-loop fair compare)
- [x] M6.3 Native scenario aggregation wired into risk path — DONE
  - `approximate_pnl_series` / `HistoricalRiskEngine` LINEAR & DELTA_GAMMA honor
    `RISKFORGE_SCENARIO_KERNEL=python|native` (+ optional `RISKFORGE_SCENARIO_KERNEL_LIB`)
  - Default remains NumPy vectorized Python path; methodology / vol-point scaling stay in Python
  - **FULL_REVALUATION cannot use the kernel** (PricingEngine revaluation only; documented in
    `historical.py`, `compute/kernel.py`, `native/README.md`)
  - Evidence: `tests/test_historical_scenario_kernel.py`
- [x] M6.4 Parallel C++ — DONE
  - **One strategy only:** C++20 stdlib thread pool over contiguous shock partitions
    (`std::jthread` when available, else `std::thread`+join; Apple libc++ often lacks
    jthread). Documented in `backend/native/README.md` — **not OpenMP**; no mixing.
  - Env `RISKFORGE_KERNEL_THREADS` (+ CLI `--threads`); serial path when `1` or `n_shocks≤1`
  - Numerical parity: C++ `kernel_test` + `tests/test_native_kernel.py` (parallel ≈ serial)
  - Harness: `benchmarks/run_scenario_bench.py --threads N --parallel-compare`
  - Capture: `benchmarks/RESULTS.md` (M6.4 section; environment caveats; not a VaR SLA)
- [x] M6.5 Native/Python parity tests — DONE
  - ABI: `tests/test_native_kernel.py` (Python ↔ native, parallel ↔ serial, empty/single/zero/NaN/32×64 matrix)
  - Risk path: `tests/test_historical_scenario_kernel.py` (M6.7 NumPy ↔ native VaR/ES)
  - C++: `native/tests/kernel_test.cpp` (serial/parallel + flat ABI)
  - Tolerances documented: `KERNEL_ABI_*` = 1e-12; `KERNEL_PNL_ABS/REL` = 1e-9 / 1e-12
    (`app.compute.kernel`, `native/README.md`)
- [x] M6.6 QuantLib concurrency architecture review/ADR — DONE
  - `docs/adr/007-quantlib-concurrency.md` (RLock in adapter; prefer process isolation for
    parallel QL reval; native kernels separate from QL globals; matches `quantlib.py` +
    `risk_run_worker.py` + native README)

### Follow-on clarification (M1–M5 audit)

- [x] M6.7 Prove native kernel hot-path equivalence on Historical VaR / scenario aggregation before claiming perf wins — DONE (parity gate)
  - NumPy vs pure-Python kernel ABI + NumPy vs native on LINEAR/DELTA_GAMMA P&L and VaR/ES
  - Explicit tolerances: `KERNEL_PNL_ABS_TOL=1e-9`, `KERNEL_PNL_REL_TOL=1e-12` (`historical.py`)
  - FULL_REVALUATION remains kernel-free even when `RISKFORGE_SCENARIO_KERNEL=native`
  - **No product risk-path speedup claimed yet** — microbench table in `benchmarks/RESULTS.md`
    remains separate from Historical VaR wall time

---

## Milestone 7 — API Productionization

Status: **PARTIAL** (M7.1–M7.5 DONE 2026-09-02; M7.6 legacy sunset still open — do not claim COMPLETE)

### Tasks

- [x] M7.1 Router decomposition — DONE (2026-09-02, Backend/API)
  - `main.py` is wiring-only (lifespan, CORS, `include_router`)
  - Routers: `api/health.py`, `portfolio.py`, `market.py`, `risk.py`, `stress.py`, `attribution.py`, `limits.py`, `risk_runs.py`
  - `get_portfolio_service` / `portfolio_service` in `api/deps.py` (PricingEngine via factory unchanged)
  - Public paths unchanged (`/health`, `/portfolio`, `/market/*`, `/risk/*`; risk-runs dual-mounted)
  - Evidence: `tests/test_api_router_decomposition.py`; full suite **445 passed**
- [x] M7.2 API versioning `/api/v1/` — DONE (2026-09-02, Backend/API)
  - Dual-mount: every public domain router at legacy path **and** `/api/v1/...`
  - `risk_runs` unified as `/risk/runs` + `/api/v1/risk/runs` only (no triple/nested prefix)
  - Legacy clients unchanged; UI may keep unversioned paths
  - Evidence: `tests/test_api_v1_compatibility.py`; OpenAPI + smoke parity on critical GETs/POSTs; full suite **453 passed**
- [x] M7.3 Typed request/response models — DONE (2026-09-02, Backend/API)
  - Wired `response_model=` on critical risk paths using existing domain types (no formula duplication):
    VaRReport, ESContributionReport, WhatIfReport, list[StressResult], ReverseStressResult,
    MultiFactorReverseStressResult, HedgeComparisonReport, RiskChangeAttributionReport,
    LimitDrilldownReport (risk-runs already RiskRunView)
  - Request bodies already domain-typed; dual-mount unchanged; PricingEngine seams preserved
  - Evidence: `tests/test_api_typed_models.py` (OpenAPI $ref + live response validation)
- [x] M7.4 OpenAPI examples — DONE (2026-09-02, Backend/API)
  - Critical paths: VaR/ES, what-if, stress/reverse/multi, hedge-compare (`HedgeComparisonReport`), change-attribution, limits drill-down, risk-runs
  - Centralized illustrative payloads in `app/api/openapi_examples.py`; wired via `Body(openapi_examples=...)` + `responses` (incl. M7.5 `{code,message,details}` where documented)
  - Evidence: `tests/test_api_openapi_examples.py`; full suite green with QuantLib
- [x] M7.5 Consistent error model — DONE (2026-09-02, Backend/API)
  - Envelope `{code, message, details}` for HTTPException, request validation (422), and unhandled 500
  - Centralized in `app/api/errors.py` via `register_exception_handlers` (legacy + `/api/v1` share handlers)
  - Successful response schemas and PricingEngine seams unchanged; 500 message opaque (no exception leak)
  - Evidence: `tests/test_api_error_model.py`; risk-run `detail` assertions updated to `message`
- [ ] M7.6 Complete `/api/v1` migration for all risk routes (beyond dual-mount)
  - Why/evidence: dual-mount lands in M7.2; M7.6 = prefer/document `/api/v1` as canonical and plan legacy sunset

### Progress update (2026-09-02, Backend/API — M7.1)

- Decomposed monolithic route handlers into charter-aligned APIRouter modules.
- Milestone 7 remains **PARTIAL** — do not claim COMPLETE until M7.2–M7.6 land with evidence.

### Progress update (2026-09-02, Backend/API — M7.2)

- Dual-mounted all public routers under `/api/v1` while preserving legacy unversioned paths.
- Milestone 7 remains **PARTIAL** until M7.3–M7.6 criteria are met with evidence.

### Progress update (2026-09-02, Backend/API — M7.5)

- Centralized `{code, message, details}` error handlers on the FastAPI app (covers both mounts).
- Milestone 7 remains **PARTIAL** — M7.3 typed models and M7.6 legacy sunset still open.

### Progress update (2026-09-02, Backend/API — M7.4)

- Added OpenAPI request/response/error examples for critical risk endpoints (illustrative numbers only).
- Milestone 7 remains **PARTIAL** — M7.3 typed models and M7.6 legacy sunset still open.

### Progress update (2026-09-02, Backend/API — M7.3)

- Wired domain `response_model=` on critical VaR/ES/what-if/stress/reverse/multi/hedge/change-attr/limits-drilldown routes.
- Milestone 7 remains **PARTIAL** — M7.6 `/api/v1` canonical + legacy sunset still open.

---


## Milestone 8 — Risk Terminal UI

Status: PARTIAL (prototype SPA; firm-root hierarchy card + thin compare/multi API client helpers)

### Tasks

- [ ] M8.1 Main application navigation — NOT STARTED (single scroll page)
- [ ] M8.2 Overview dashboard — PARTIAL
- [ ] M8.3 Risk heatmaps — NOT STARTED
- [ ] M8.4 Scenario Builder — PARTIAL
- [ ] M8.5 Before/after hedge workflow — PARTIAL (`compareHedge` / `hedgeComparisonSummary` for `HedgeComparisonReport` object shape; **no full UI page** yet; breaking API shape vs legacy list)
- [ ] M8.6 Risk drill-down — PARTIAL (Hierarchy card walks Firm→Portfolio; counts desks/strategies/books/trades; displays root NAV/VaR/ES/Greeks from API)
- [ ] M8.7 P&L Explain UI — PARTIAL (demo only)
- [ ] M8.8 Limits UI — PARTIAL (`limitStatus` prefers API `WARNING`/`OK`/`BREACH` — **done** in `risk.mjs`; full limits/drill-down UX still open)
- [x] M8.9 Risk-run UI — DONE (start)
  - Thin `createRiskRun` / `getRiskRun` in `api.js` (`POST/GET /risk/runs`)
  - Dashboard `RiskRuns` card: run_type select, start, poll QUEUED→RUNNING→COMPLETED/FAILED
  - Display helpers: `riskRunStatus` / `riskRunStatusClass` / `isRiskRunTerminal` / `riskRunSummary` (no client risk math)
  - Evidence: `frontend/src/lib/risk.test.mjs`
- [ ] M8.10 Risk change attribution UI panel
  - Why/evidence: `POST /risk/change-attribution` + `Attribution` P&L panel exist; **no** risk-change waterfall UI / API client
- [ ] M8.11 ES contributions UI panel
  - Why/evidence: `POST /risk/es` wired (M2.5); frontend has no ES contribution consumer
- [ ] M8.12 VaR methodology compare UI (`POST /risk/var/compare`)
  - Why/evidence: M2.4 API exists; terminal does not surface Linear / Δ-Γ / Full-reval comparison

---

## Milestone 9 — Testing, CI & Engineering Quality

Status: PARTIAL (M9.6 + M9.9 DONE; other M9 tasks still open)

### Tasks

- [ ] M9.1 Frontend testing stack (Vitest/RTL/MSW) — PARTIAL (node:test helpers only)
- [ ] M9.2 E2E Playwright — PARTIAL (4 critical-path specs)
- [ ] M9.3 Backend property tests (Hypothesis) — PARTIAL (landed under M1.8 `test_quant_properties.py`; broaden beyond pricing Greeks)
- [ ] M9.4 Golden quant tests — PARTIAL (M1.8 `test_quantlib_golden.py`; expand instrument coverage)
- [ ] M9.5 Stress invariants — PARTIAL
- [x] M9.6 CI GitHub Actions — workflow at `.github/workflows/ci.yml` (backend pytest Py3.12 + QuantLib-preferred / builtin fallback, frontend `npm test`/`npm run build`, optional native g++ smoke, **`postgres-smoke` service job** via `scripts/smoke_postgres.sh`). Runner validation deferred to **M9.9**.
- [ ] M9.7 Static analysis (Ruff/mypy/ESLint) — NOT STARTED
  - [ ] M9.8 Containers — PARTIAL (compose: `postgres` + `backend` + `worker` + `frontend`; worker claims via Postgres `SKIP LOCKED` — see M5.7; Redis/RQ optional)

- [x] M9.9 Validate CI on GitHub-hosted runners (fix workflow green; document QuantLib install path) — **DONE** (2026-09-02)
  - Local evidence (2026-09-02, DevOps): `docker compose up -d postgres` + `RISKFORGE_DATABASE_URL=postgresql+psycopg://riskforge:riskforge@localhost:5432/riskforge ./scripts/smoke_postgres.sh` → **exit 0** (`postgres smoke OK`; Alembic head `002_risk_run_domain_fields`). Idempotent re-run OK. See `BUILD_NOTES.md`.
  - CI hardening: smoke waits up to 60s for psycopg `SELECT 1`; job prints sqlalchemy/alembic/psycopg versions; QuantLib optional for `postgres-smoke` (full `requirements.txt` preferred; strip QuantLib on wheel failure). Main `backend` job still prefers QuantLib wheel on `ubuntu-latest`, falls back to builtin.
  - GHA evidence: repo https://github.com/SergTogul/riskforge-mvp ; push SHA `31228fb`; CI run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125 — `postgres-persistence-smoke` https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125/job/100391676176 ; also `backend-pytest` + `frontend-test-build` green. QuantLib path: backend job prefers wheel on ubuntu-latest with builtin fallback (see workflow).
  - Milestone 5 COMPLETE cleared on this evidence; M5.5 polish remains optional.
- [ ] M9.10 E2E coverage for post-M2/M3/M4/M5 endpoints — PARTIAL
  - Why/evidence: Playwright has dashboard / scenario-builder / reverse-stress / risk-query / **risk-runs poll** (`e2e/tests/risk-runs.spec.ts`); still missing ES, change-attribution, reverse multi, hedge-compare object shape

---

## Milestone 10 — Demo Data & Reproducibility

Status: NOT STARTED

### Tasks

- [ ] M10.1 Demo portfolios (Equity Vol / Rates Macro / Cross-Asset) — PARTIAL (one in-code SAMPLE_PORTFOLIO)
- [ ] M10.2 Demo historical market dataset — NOT STARTED (`data/sample_portfolio.csv` unused orphan)
- [ ] M10.3 Deterministic demo scripts — NOT STARTED

---

## Milestone 11 — AI Risk Assistant

Status: NOT STARTED

### Tasks

- [ ] M11.1 Deterministic tool contracts — PARTIAL (keyword `RiskQueryEngine` + service methods)
- [ ] M11.2 LLM orchestration — NOT STARTED
- [ ] M11.3 Risk assistant evaluation suite — NOT STARTED
- [ ] M11.4 Guardrails — NOT STARTED

---

## Milestone 12 — Documentation & Portfolio Presentation

Status: NOT STARTED

### Tasks

- [ ] M12.1 Recruiter/interviewer README — PARTIAL (current README is MVP-oriented)
- [ ] M12.2 Architecture documentation — PARTIAL (agent docs; no system diagrams package)
- [ ] M12.3 ADRs under `docs/adr/` — PARTIAL
  - Landed (2026-09-02, evidence-backed only): `001`–`006` plus `007-quantlib-concurrency.md` (M6.6)
  - Not written yet (insufficient decided evidence / still open): e.g. RiskRun domain/API lifecycle (M5.2+), API versioning, VaR methodology modes, caching — do not invent ADRs ahead of code
  - Native kernel risk-path wiring (M6.3) documented via env flag + native/README; no separate ADR unless Lead requests
- [ ] M12.4 Methodology documentation — NOT STARTED
  - Must include honest multi-factor reverse-stress assumptions (M3.9) and VaR methodology modes
- [ ] M12.5 Performance report — PARTIAL (`BUILD_NOTES.md` caveated microbench)
- [ ] M12.6 Known engine / pricing limitations catalog (recruiter-facing)
  - Why: surface bump vs grid (M1.10), BlackConstantVol (M1.11), bond day-count (M1.12), KR drill-down (M4.7), multi-factor reverse (M3.9) — prevent over-claiming completeness

---

## Milestone 13 — Final Portfolio Demo

Status: NOT STARTED

### Tasks

- [ ] M13.1 Seed data + deterministic setup for 3–5 minute demo flow
- [ ] M13.2 Screenshots + demo instructions + expected output ranges
- [ ] M13.3 Clean-checkout verification of demo path

---

## Definition of Done (reminder)

A task is DONE only when implementation exists, tests pass, review completed, docs updated if needed, and this file marks `[x]` with evidence. Never mark blocked/partial work complete.
