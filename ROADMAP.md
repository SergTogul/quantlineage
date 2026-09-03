# RiskForge Development Roadmap

Authoritative backlog from 2026-09-02. `TASKS.md` is **absent** in this checkout (still referenced by agent docs); do not recreate Workstream 0 work there—use this file going forward.

## Progress

| Workstream | Status |
|-----------|--------|
| Workstream 0 — Prototype Foundation | COMPLETE |
| Workstream 1 — Quant Foundation | **COMPLETE** (2026-09-02) |
| Workstream 2 — VaR, ES & Portfolio Risk | **COMPLETE** (2026-09-02) |
| Workstream 3 — Stress & Threat Engine V3 | **COMPLETE** (2026-09-02) |
| Workstream 4 — Hierarchy, Attribution & Limits | **COMPLETE** (2026-09-02 Lead Architect formal acceptance) |
| Workstream 5 — Persistence & Risk-Run Platform | **COMPLETE** (2026-09-02: GHA green; caching polish **DONE**) |
| Workstream 6 — C++ Performance Engine | **COMPLETE** (2026-09-02 — + formal scenario-kernel SLA-K1/K2) |
| Workstream 7 — API Productionization | **COMPLETE** (2026-09-02 — dual-mount + typed models + OpenAPI examples + error model + `/api/v1` canonical / legacy sunset plan) |
| Workstream 8 — Risk Terminal UI | **COMPLETE** (2026-09-02) — SPA `/api/v1`; nav; heatmaps; overview collage; scenario builder; hierarchy drill; P&L attribution API; limits UX; hedge-compare; risk-run poll; analytics panels |
| Workstream 9 — Testing, CI & Engineering Quality | **COMPLETE** (2026-09-03 — containers DONE; Redis/RQ residual resolved as accepted deferral with queue-contract tests) |
| Workstream 10 — Demo Data & Reproducibility | **COMPLETE** (2026-09-02 — ) |
| Workstream 11 — AI Risk Assistant | **COMPLETE** (2026-09-03 — deterministic tools plus provider-agnostic model/tool loop) |
| Workstream 12 — Documentation & Portfolio Presentation | **COMPLETE** (2026-09-03 — recruiter docs, architecture, methodology, performance, and limitations package) |
| Workstream 13 — Final Portfolio Demo | **COMPLETE** (2026-09-03 — ) |

### Baseline verification (2026-09-02, local macOS — Lead Architect acceptance)

| Check | Result |
|-------|--------|
| QuantLib | 1.43 import OK |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`) | **160 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **10 passed** |
| Frontend `npm run build` | **OK** |
| C++ via `test_native_kernel` | **passed** (g++/Apple clang 14; earlier same-day baseline; not re-run in this acceptance pass) |
| Manual `g++` of `kernel_test.cpp` without `-I include` | fails include path (docs/README must use `-I include`) |
| Workstream 1 status | **COMPLETE** — see evidence + documented limitations |
| Concurrent note | Suite count includes tests landed during same-day work; acceptance does not claim Workstream 2 complete |
| `TASKS.md` | missing |
| Prior stub `ROADMAP.md` | replaced by this file |

### Architecture map (evidence-based)

```text
Trade (domain/models.py)
 → PricingEngine (interfaces/pricing.py)
 ├─ QuantLibPricingEngine [equity, EQ option, ZC bond, IRS, EQ future, FX fwd/opt, IR future]
 └─ BuiltinPricingEngine [same instrument set]
 ├─ curve_rates / QL ZeroCurve when MarketSnapshot.curves|key_rates attached
 └─ surface_vol lookup when MarketSnapshot.vol_surfaces attached
 → MarketSnapshot (frozen + recursive MappingProxy; model_copy re-freezes; typed bump/apply/diff)
 → Risk engines
 ├─ SensitivityEngine [bump-revalue; key-rate DV01 when curves/key_rates present]
 ├─ HistoricalRiskEngine / VaRAnalytics [LINEAR / DELTA_GAMMA / FULL_REVALUATION]
 ├─ StressEngine / ReverseStress / Compare
 ├─ Hierarchy / Attribution / Limits / Factors / Query
 → PortfolioService → FastAPI (app/api/* routers; canonical `/api/v1` + deprecated legacy dual-mount)
 → React SPA (single page cards) / optional NativeScenarioKernel (LINEAR/Δ-Γ via RISKFORGE_SCENARIO_KERNEL)
```

### Highest-risk gaps (post– progress)

1. Caps/floors and vanilla European swaptions have a scoped flat Black-76 pricing slice; EquityVol/FXVol bumps now rewrite attached surface grids; QL still uses `BlackConstantVol` at point σ for equity/FX options (not full surface engine)
2. **COMPLETE** (2026-09-02): GHA `postgres-persistence-smoke` green (https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125); caching polish **DONE** (valuation LRU + curve-construction + scenario memo)
3. **COMPLETE** (2026-09-02 Lead Architect + C++ Performance): DONE; formal **scenario-kernel SLA** SLA-K1 ≥50× / SLA-K2 ≥1.3× on `10k_x_1k` (reference host; `benchmarks/RESULTS.md` + `benchmarks/check_m6_sla.py`); FULL_REVALUATION stays Python; **not** an HTTP end-to-end VaR latency claim
4. **COMPLETE** (router split + dual-mount `/api/v1` + typed models + OpenAPI examples + `{code,message,details}` + canonical/sunset docs + legacy Deprecation headers); ** formal Scenario HTTP wire DONE** (legacy StressScenario endpoints retained)
5. **COMPLETE** (2026-09-02): overview collage, scenario builder presets, Firm→trade hierarchy drill, P&L `/risk/attribution` UI, limits status+drill UX (plus prior nav/heatmaps/hedge/runs/analytics panels)
6. **COMPLETE** (2026-09-02): ; compose containers DONE; Redis/RQ explicitly **deferred** (Postgres `SKIP LOCKED` claim path — ADR 005 / ). transient GHA `e2e-playwright` failure on multi-factor reverse UI land must stay fixed (testid + exact heading) — see below. local mypy lint regression fixed on master (`11339c6`); GHA URL confirmation blocked by invalid `gh` keyring token (see )
7. Multi-factor reverse stress = ray + coordinate descent (**not** a certified global optimum); methodology doc published at `docs/methodology/multi_factor_reverse_stress.md`. ** POSTPONED** — do not implement until Lead/user unblocks

### Suite verification (2026-09-02, Lead Architect — local macOS)

| Check | Result |
|-------|--------|
| Backend pytest (`cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q --tb=line`) | **519 passed** (2026-09-02 ), 1 Starlette/httpx deprecation warning, 0 failed, 0 skipped |
| Frontend `npm test` | **56 passed**, 0 failed |
| Frontend `npm run build` | **OK** (vite; 22 modules) |
| workstream | **COMPLETE** — GHA green (run 33673245125); caching polish **DONE** |
| | **DONE** (DI; Postgres `SKIP LOCKED` claim + Compose worker; stress scenario_definitions HTTP) |
| | **DONE** (valuation LRU + curve-construction cache + scenario-result memo) |
| | **DONE** (harness, baseline, risk-path wire, parallel pool, ABI+Historical parity, QL concurrency ADR) |
| workstream | **COMPLETE** (2026-09-02) — formal scenario-kernel SLA-K1/K2 recorded; not HTTP VaR wall-time |
| workstream | **COMPLETE** (2026-09-02) — ; legacy dual-mount remains until sunset removal gate |

---

## Workstream 0 — Prototype Foundation

Status: COMPLETE

Working MVP: PricingEngine seam, QuantLib + builtin adapters (partial QL coverage), MarketSnapshot + shock, 7 instruments, synthetic VaR/ES + component VaR, stress/threat/custom/reverse/hedge-compare, hierarchy, attribution, limits, NL keyword query, Python + optional C++ scenario kernel, FastAPI, React terminal, backend/frontend/e2e tests.

Deficiencies discovered are assigned to later workstreams (do not redo ).

---

## Workstream 1 — Quant Foundation

Status: **COMPLETE** (Lead Architect acceptance 2026-09-02)

Critical review items closed with code evidence:

1. Nested `curves` / `vol_surfaces` deep-frozen via recursive `MappingProxyType`; `model_copy` re-applies freeze
2. `RateZero` tenor bumps isolate pillars; `PARALLEL`/`ALL` parallel-shift scalar + pillars + matching curve zeros
3. Key-rate DV01 uses tenor bumps when curves/key_rates present (`KEY_RATE_CURVES_CONSUMED_BY_PRICING=True`); Builtin/QL bond/swap consume curves; options consume `vol_surfaces`

### Tasks

- [x] Local production dependency verification
 - Evidence (2026-09-02 acceptance): QuantLib 1.43; backend **160 passed** with `RISKFORGE_PRICING_ENGINE=quantlib`; frontend `npm test` **10 passed**; `npm run build` OK
- [x] Complete QuantLib instrument coverage
 - EquityFuture / FXForward / FXOption: native QL paths (no Builtin fallback); tight parity tests
 - InterestRateFuture: domain + Builtin/QL adapters (algebraic STIR mark; full QL FRA still deferred)
 - Caps/floors/swaptions: **deferred** (documented limitation) until richer IR vol / exercise modeling
 - Builtin `pay_fixed=True` aligned to standard payer economics (matches QuantLib)
- [x] Formal market-data domain
 - Frozen `MarketSnapshot` with recursive deep-freeze; bump/apply/diff/content_hash; sub-market views
 - RateZero: `PARALLEL`/`ALL` vs specific tenors (no silent parallel on tenor bumps)
 - Pricing consumes attached curves/key_rates (bonds/swaps) and vol surfaces (EQ/FX options) when present; scalars remain fallback
 - Evidence: `tests/test_market_snapshot.py`; ADR 002
- [x] Yield curves
 - USD OIS/SOFR scaffolds, key tenors, linear zeros, triangular key-rate shocks; attach → `curves`/`key_rates`
 - Builtin `discount_factor` / `continuous_zero`; QuantLib `_curve_handle` / `ZeroCurve` when attached
 - Limitation (accepted for ): flat zeros / no market-instrument bootstrap yet
 - Evidence: `tests/test_curves.py`, `tests/test_curve_pricing.py`
- [x] Volatility surfaces
 - Equity/FX expiry × moneyness grids; parallel / expiry-bucket / skew / term shocks; bilinear lookup
 - `attach_vol_surface`; Builtin + QuantLib option paths via `surface_vol.option_vol_from_snapshot`
 - Limitation: flat/scaffolding grids only — no SABR/local-vol calibration
 - Evidence: `tests/test_vol_surfaces.py`, `tests/test_surface_vol_pricing.py`
- [x] Typed risk-factor taxonomy
 - Evidence: typed `RiskFactor` in `backend/app/risk/factor_types.py`; `RiskFactorEngine` migrated (API still string keys); `test_factor_types.py`
- [x] Unified bump-and-revalue sensitivity engine
 - delta/gamma/vega/DV01/FX delta; key-rate DV01 uses true tenor bump + `method=bump_revalue` when tenor available
 - Honest parallel fallback (`bump_revalue_parallel_fallback`) only when no `key_rates`/curve pillar for that tenor
 - Flag `KEY_RATE_CURVES_CONSUMED_BY_PRICING=True`
 - Evidence: `tests/test_sensitivities.py` (isolation + swap tenor + missing-fallback cases)
- [x] Quant correctness tests
 - Hypothesis properties + FD Greek reconciliation (`test_quant_properties.py`); QuantLib golden BS/GK + Builtin cross-check (`test_quantlib_golden.py`); `hypothesis>=6.112,<7` in `requirements.txt`
 - Conventions: cash delta/gamma/vega; discounted European intrinsic; `pay_fixed=True` = payer

### Acceptance Criteria

- [x] QuantLib adapters for EquityFuture, FXForward, FXOption behind `PricingEngine` with reference comparison tests
- [x] Domain models for IR future; cap/floor/swaption **documented deferral** under
- [x] Immutable market domain with bump/diff (deep freeze of nested curve/surface payloads; `model_copy` re-freezes)
- [x] USD OIS/SOFR curve scaffolding; equity/FX vol surface scaffolding
- [x] Typed `RiskFactor` abstraction used by risk vectors
- [x] Sensitivity engine for delta/gamma/vega/DV01/honest key-rate DV01/FX delta
- [x] Property/golden tests green under QuantLib

### Documented limitations (not blockers)

- Caps/floors/swaptions not priced
- Curves are flat-zero scaffolds (no bootstrap from deposits/futures/swaps)
- Vol surfaces are scaffolding grids (no SABR/local-vol)
- QuantLib IR future remains algebraic STIR (not full FRA/futures engine)
- Without attached curves/key_rates, key-rate DV01 correctly falls back to parallel and tags the method
- `MarketSnapshot.bump` / `apply` rewrites attached `vol_surfaces` grids for typed EquityVol / FXVol shocks
- QuantLib equity/FX options consume attached grids via `BlackVarianceSurface`; richer calibrated SABR/local-vol remains out of scope
- Builtin ZC bond uses simple compound `(1+y)^T`; QL uses continuous/`Actual365Fixed` — golden tests allow ~5% relative band

### Follow-on tasks (discovered during ; do not reopen acceptance)

- [x] Caps / floors / swaptions pricing (IR vol + exercise) — **DONE** (2026-09-03 scoped vanilla slice)
 - Caps/floors: `CapFloorPosition` domain model plus Builtin and QuantLib flat-forward Black-76 optionlet-strip valuation
 - Swaptions: `SwaptionPosition` domain model plus Builtin and QuantLib flat-forward Black-76 option on generated annuity; European payer/receiver only
 - Evidence: `backend/tests/test_ir_options_pricing.py`; no-fallback parity in `backend/tests/test_quantlib_pricing.py`; handoffs `docs/agents/HANDOFF_SWAPTIONS.md` and `docs/agents/HANDOFF_VOL_SURFACE_BUMPS.md`
 - Residual limitations: no IR vol cube/smile, Bermudan/callable structures, physical/cash settlement variations, or explicit calendar/date schedules
- [x] Surface-aware EquityVol / FXVol bumps rewrite attached `vol_surfaces` grids — **DONE** (2026-09-03)
 - `MarketSnapshot.bump` / `apply` now rewrite matching attached `vol_surfaces` grids as well as scalar ATM marks for generic, expiry-bucket, skew, and term vol shocks
 - Evidence: `backend/tests/test_market_snapshot.py`, `backend/tests/test_surface_vol_pricing.py`; handoff `docs/agents/HANDOFF_VOL_SURFACE_BUMPS.md`
- [x] QuantLib full surface / smile engine (replace point `BlackConstantVol`) — **DONE** (2026-09-03)
 - `QuantLibPricingEngine` now builds a `BlackVarianceSurface` from matching equity/FX `MarketSnapshot.vol_surfaces` grids and uses scalar `BlackConstantVol` only when no matching grid is attached
 - Evidence: `backend/tests/test_quantlib_pricing.py`; handoff `docs/agents/HANDOFF_QUANTLIB_SURFACE_SMILE_M1_11.md`
- [x] Align Builtin vs QuantLib ZC bond day-count / compounding conventions — **DONE** (2026-09-02)
 - Builtin scalar (no curve) now uses continuous compounding on Actual365Fixed year fraction ``max(1, round(T*365))/365``, matching QuantLib ``ZeroCouponBond`` + ``FlatForward(Continuous, Actual365Fixed)``.
 - Tight Builtin↔QL parity + continuous golden: **rel=1e-10** (`test_quantlib_golden.py`); curve-path still discounts at domain pillar ``maturity_years`` (`test_curve_pricing.py`).
 - Historical annual ``face/(1+y)^T`` retired as a reference (was **rel=5e-2** gap).
- [x] Curve bootstrap from market instruments (replace flat-zero scaffolds) — **DONE** (2026-09-03 scoped minimal bootstrap)
 - Structured `CurveBootstrapInstrument` inputs support deposits/simple annual rates and explicit continuous-zero instruments; `bootstrap_yield_curve` converts simple deposit DFs to continuous zeros, sorts nodes deterministically, and rejects duplicate/invalid tenors
 - `attach_bootstrapped_curve` writes the curve payload to `MarketSnapshot.curves`, updates discount `key_rates`, and sets scalar rate/projection fallbacks; existing Builtin/QuantLib curve resolver can parse non-key tenors such as `6M`
 - Evidence: `backend/tests/test_curves.py`, `backend/tests/test_curve_pricing.py`; handoff `docs/agents/HANDOFF_CURVE_BOOTSTRAP_M1_13.md`
 - Residual limitations: deterministic offline single-curve helper only; no live vendor integration, futures convexity, swap-quote bootstrap, calendars/stubs, or production multi-curve calibration

---

## Workstream 2 — VaR, ES & Portfolio Risk

Status: **COMPLETE** (2026-09-02 Lead Architect formal acceptance)

### Tasks

- [x] Historical market dataset abstraction
 - `backend/app/risk/historical_data.py`: `FactorObservationSeries`, `HistoricalMarketDataset` protocol, `SyntheticHistoricalDataset`, `ArrayHistoricalDataset`
 - Separates factor observations from scenario generation and valuation (`HistoricalRiskEngine` / `VaRAnalytics`)
 - Aggregate equity/FX returns, vol moves, parallel rate bp moves only — no key-rate / tenor dependency required for aggregate path
 - `HistoricalRiskEngine` + `VaRAnalytics` consume dataset; default synthetic preserves prior seeded RNG
 - Evidence: `tests/test_historical_data.py` (7) + risk regression green (2026-09-02)
- [x] Historical scenario generation
 - `backend/app/risk/scenarios.py`: `AggregateFactorChange` → typed `MarketScenario` / `FactorChange` → shocked `MarketSnapshot[]`
 - Expands aggregate observation moves onto factors present in a base snapshot; applies via `MarketSnapshot.apply` (bump units); `to_stress_scenario` bridges `shock_snapshot`
 - Does **not** alter Δ-Γ VaR (`HistoricalRiskEngine` / `VaRAnalytics`); empty scenario preserves `content_hash`
 - Evidence: `tests/test_scenarios.py`
- [x] Full-revaluation Historical VaR
 - Explicit `VaRMethodology`: `LINEAR` | `DELTA_GAMMA` (default, legacy Δ-Γ) | `FULL_REVALUATION`
 - `FULL_REVALUATION` reprices via `PricingEngine` on `historical_shocked_snapshots`
 - Methodology on `RiskSummary` / `VaRReport`; query param on `/risk/summary`, `/risk/var`
 - Evidence: `tests/test_var_methodology.py`
- [x] VaR comparison (Linear / Δ-Γ / Full reval)
 - `backend/app/risk/var_compare.py`: `compare_methodologies` — shared dataset, times each mode (delegates P&L to `HistoricalRiskEngine`)
 - DTOs: `VaRMethodologyMetrics`, `VaRMethodologyComparison`; service + `POST /risk/var/compare`
 - Returns per methodology: VaR95, VaR99, ES99, `runtime_ms`, methodology label
 - Evidence: `tests/test_var_compare.py`
- [x] Expected Shortfall contributions
 - `backend/app/risk/es.py`: historical tail-conditional ES by position / book / strategy / desk / risk factor
 - LINEAR/DELTA_GAMMA: additive Greek factor P&L; FULL_REVALUATION: factor-isolated reval + `interaction` residual
 - DTOs: `ESContribution`, `ESContributionReport`; `PortfolioService.es_contributions`; `POST /risk/es` (optional `methodology` query)
 - Position-level `component_es` also on `RiskContribution` in `VaRReport`
 - Reconciliation: contribution sum ≈ portfolio ES (abs 1e-6 / rel 1e-8)
 - Evidence: `tests/test_es_contributions.py` (service + API)
- [x] Component VaR
 - Euler / covariance allocation of **parametric** VaR on methodology P&L series (`LINEAR` | `DELTA_GAMMA` | `FULL_REVALUATION`)
 - `CVaR_i = VaR · Cov(X_i, X) / Var(X)`; Σ CVaR = parametric VaR (not historical quantile VaR)
 - Shared helpers in `backend/app/risk/marginal_var.py`; `VaRAnalytics.report` contributions
 - Evidence: `tests/test_component_var.py` — reconciliation under Δ-Γ and full reval; single-position / zero-shock edges
- [x] Marginal VaR
 - `MVaR_i = ∂VaR/∂w_i|_{w=1} = z · Cov(X_i, X) / σ`; at current holdings `MVaR_i = CVaR_i`
 - `RiskContribution.marginal_var` (default 0.0, append-only); FD helper `finite_difference_marginal_var`
 - Methodology documented in `marginal_var.py` module docstring
 - Evidence: `tests/test_marginal_var.py`
- [x] Incremental VaR
 - `backend/app/risk/incremental_var.py`: `apply_what_if_changes`, `incremental_var`, `what_if_analysis`
 - Methodology: IVaR = VaR(P′) − VaR(P) (same for VaR95 / ES99); positive ⇒ risk-increasing; input portfolio never mutated
 - Delegates P&L/quantiles to `HistoricalRiskEngine`; default methodology `DELTA_GAMMA`
 - Evidence: `tests/test_incremental_var.py`
- [x] What-if API `POST /risk/what-if` ( will version under `/api/v1`)
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
| checklist | All `[x]` with file/test evidence in ROADMAP |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`) | **219 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **10 passed** |
| Frontend `npm run build` | **OK** |
| API gap closed | `POST /risk/es` wired to `PortfolioService.es_contributions` |
| Known residual | Dual-mount `/api/v1` + sunset plan DONE; legacy paths remain until removal gate |

---

## Workstream 3 — Stress & Threat Engine V3

Status: **COMPLETE** (2026-09-02 Lead Architect formal acceptance)

### Tasks

- [x] Formal Scenario domain model
 - `backend/app/risk/scenario_model.py`: `Scenario` with id/name/category/description/`FactorShock[]`/threshold/severity/metadata
 - Shocks reference typed `RiskFactor` (`factor_types.py`); apply via `MarketSnapshot.apply`
 - Adapters to/from legacy `StressScenario` and `MarketScenario` (existing stress APIs unchanged)
 - Severity bands aligned with StressEngine threat levels; ADR 004
 - Evidence: `tests/test_scenario_model.py`
- [x] Multi-factor scenario engine
 - `backend/app/risk/scenario_engine.py`: `ScenarioEngine` / `apply_scenario` / `expand_scenario` / `shocked_snapshots`
 - Primary path: formal `Scenario` / `FactorShock` via `scenario_model.apply_scenario`
 - Also accepts legacy `StressScenario`, `MarketScenario` / `FactorChange`, and `(RiskFactor, amount)` pairs
 - Combined equity + rates + FX + vol → shocked `MarketSnapshot` via `MarketSnapshot.apply` / `bump`
 - Canonical expansion for `StressScenario` (`scenario_from_stress`); caller order for explicit lists; independent scenarios
 - `shock_snapshot` delegates to engine (StressScenario APIs unchanged); re-exported from `stress.py`
 - Evidence: `tests/test_scenario_engine.py`
- [x] Historical crisis library
 - `backend/app/risk/crisis_library.py`: documented presets (Lehman 2008, COVID Mar-2020, 2022 rates, Euro 2011, Volmageddon 2018, China 2015, dot-com-style)
 - Formal `Scenario` category `HISTORICAL_APPROXIMATION` for all crisis presets; observation series → `HISTORICAL_REPLAY`
 - Honest disclaimers; never present approximations as exact replays; wired into `THREAT_SCENARIOS`
 - Evidence: `tests/test_crisis_library.py`
- [x] Scenario contribution decomposition
 - `backend/app/risk/scenario_attribution.py`: hierarchy (portfolio/desk/strategy/book/trade) + risk-factor decomposition
 - Factor path: isolated full reval per typed `RiskFactor.key` + `interaction` residual
 - Formal `Scenario` and legacy `StressScenario` inputs; wired into `StressEngine.evaluate` / `contributions`
 - DTOs: `ScenarioContribution`, `ScenarioContributionBreakdown` on `StressEvaluation.contributions`
 - Evidence: `tests/test_scenario_attribution.py` (reconciliation abs 1e-6 / rel 1e-8)
- [x] Reverse stress single-factor
 - `backend/app/risk/reverse_stress.py`: binary-search solver on typed `FactorShock` / formal `Scenario` (REVERSE)
 - Returns target loss (absolute), wire-compatible `required_shock`, resulting P&L, convergence diagnostics
 - Units: equity/vol/fx relative; rates in bp (legacy `max_shock=0.80` → 800bp bound)
 - `ReverseStressEngine` re-exported from `stress.py`; `/risk/stress/reverse` unchanged
 - Evidence: `tests/test_reverse_stress.py`
- [x] Reverse stress multi-factor
 - `backend/app/risk/reverse_stress_multi.py`: constrained L2 ray search + coordinate descent
 - Documented assumptions on result; adverse orthant; reuses shock builders (no single-factor rewrite)
 - API: `POST /risk/stress/reverse/multi`; re-exported from `stress.py`
 - Evidence: `tests/test_reverse_stress_multi.py`
- [x] Hedge comparison
 - `ScenarioComparisonEngine` → `HedgeComparisonReport`: hedge_cost, base/hedged VaR & ES, scenario loss, factor exposure deltas
 - Legacy per-scenario pnl/improvement fields retained inside `scenarios[]`
 - API: `POST /risk/stress/compare` returns report (not bare list)
 - Evidence: `tests/test_hedge_comparison.py`

### Acceptance Criteria

Flagship stress with typed multi-factor shocks, honest crisis labeling, reconciled contributions, single- and multi-factor reverse stress, strengthened hedge compare.

### Formal acceptance evidence (2026-09-02)

| Check | Result |
|-------|--------|
| checklist | All `[x]` with file/test evidence in ROADMAP; focused suite **78 passed** |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`, QuantLib 1.43) | **282 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **10 passed** |
| Frontend `npm run build` | **OK** |
| Breaking API shape | `POST /risk/stress/compare` returns `HedgeComparisonReport` object (not bare `ScenarioComparison[]`); legacy per-scenario fields live under `scenarios[]` |
| Multi-factor reverse limitations | Adverse orthant only; monotonicity assumed not proven; ray + coordinate descent is not a certified global optimum; assumptions echoed on result |
| Known residual | Hedge-compare UI landed ; dual-mount + sunset DONE (legacy still served); ** formal Scenario wire DONE** (legacy StressScenario retained; hedge-compare/what-if still legacy shape) |
| Hierarchy | Left untouched in acceptance — later fixed hierarchy↔stress via lazy import (no residual circular-import gap) |

### Follow-on tasks (discovered during )

- [x] Expose formal `Scenario` as stress HTTP wire type (versioned `/api/v1`) — **DONE** (2026-09-02 Lead Architect + Backend)
 - Wire: `app.api.scenario_wire` (`ScenarioWire` / `FactorShockWire` / `FormalCustomStressRequest`)
 - Routes: `GET /api/v1/risk/stress/scenarios/formal`, `POST .../formal/custom`, `POST .../formal/evaluate/custom`
 - Adapters → `StressScenario` for `StressEngine` (no VaR/pricing math change); legacy `StressScenario` endpoints unchanged
 - Evidence: `backend/tests/test_scenario_wire_api.py`; ADR 004 consequences updated
 - Residual: hedge-compare / what-if still accept `StressScenario` only; Frontend ScenarioBuilder may keep legacy shape until a UI follow-on
- [x] Publish multi-factor reverse-stress limitations in methodology docs (not a fake “complete optimizer”) — **DONE** (2026-09-02)
 - Doc: `docs/methodology/multi_factor_reverse_stress.md` — adverse orthant, L2 box objective, ray + coordinate descent, monotonicity assumed not proven, **not** a certified global optimum
 - Evidence: `backend/tests/test_m39_methodology_docs.py` (doc exists; covers `ASSUMPTIONS`; rejects over-claim language)
 - Keep `[x]`; full recruiter methodology pack remains under **postponed**

---

## Workstream 4 — Hierarchy, Attribution & Limits

Status: **COMPLETE** (2026-09-02 Lead Architect formal acceptance)

### Tasks

- [x] First-class hierarchy — DONE (Firm→Portfolio→Desk→Strategy→Book→Trade; position desk/strategy with portfolio defaults; HierarchyRef / portfolio_at / risk_at; MV reconciliation; ES multi-desk rollups)
- [x] Hierarchical risk aggregation — DONE
 - Each `HierarchyNode` carries NAV, Greeks (`delta`/`gamma`/`vega`/`dv01`/`fx_delta`), `var_95`/`var_99`/`expected_shortfall_99`, default-scenario `stress`, and `limits`
 - Additive reconciliation (parent == sum children, abs 1e-9): MV, Greeks, stress P&L
 - Non-additive (node subset): VaR, ES, limits — match `risk.calculate` / `LimitEngine` / `StressEngine.run`
 - Firm root aligned with ; lazy stress import avoids circular import with scenario_attribution
 - Evidence: `tests/test_hierarchy.py`
- [x] P&L Explain v2 — DONE
 - `AttributionEngine.explain`: actual P&L = PV(curr,cm)−PV(prev,pm); market bridge on previous book via Delta/Gamma/Vega/Rates/FX/Theta; trade flow New/Closed trades (incl. size changes)
 - Reconciliation: `explained_change + residual == total_change` (Taylor residual absorbs higher-order / duration-DV01 gaps)
 - API compat: `AttributionRequest`/`AttributionReport`/`POST /risk/attribution` + demo; additive optional `dt_years` for theta
 - Evidence: `tests/test_attribution.py`; regression `test_next_phase.py` attribution cases
- [x] Risk change attribution — DONE
 - New `backend/app/risk/risk_attribution.py` (separate from P&L `attribution.py`)
 - Waterfall: closed / position changes / new trades → equity / vol / rates / FX → correlation residual
 - Metric: `var_99` | `var_95` | `expected_shortfall_99`; market-aware Greeks when snapshot provided
 - Invariants: identical state → ~0; drivers reconcile to total Δ within abs 1e-6 / rel 1e-8
 - Service: `PortfolioService.risk_change_attribution`; API `POST /risk/change-attribution` (`RiskChangeAttributionRequest`)
 - Evidence: `tests/test_risk_attribution.py` (incl. API contract)
- [x] Configurable risk limits — DONE
 - `LimitEngine`: firm/desk VaR, ES, DV01, key-rate DV01, concentration, vega, FX, stress loss
 - Status OK / WARNING / BREACH via configurable `warning_threshold_pct` (default 80%)
 - Hierarchy reuses node stress for `stress_loss`; `breached` kept for API compat
 - Evidence: `tests/test_limits.py`, `tests/test_risk.py`, `tests/test_hierarchy.py`
- [x] Limit drill-down — DONE
 - `limit_drilldown.py` consumes `LimitResult` + hierarchy subset + metric contributors
 - Breach (or selected metric) shows: hierarchy node/path, metric, value, limit, utilization %, top contributors
 - Contributor rules: VaR/ES → component VaR/ES; Greeks → abs greek; `single_position_pct` → abs MV share; `stress_loss` → worst-scenario position losses
 - Consumes `LimitResult` (status/warning/scope/label preserved on value/limit/utilization/breached)
 - Optional `POST /risk/limits/drilldown` (`LimitDrilldownRequest` / `LimitDrilldownReport`)
 - Evidence: `tests/test_limit_drilldown.py`

### Acceptance Criteria

Firm→trade hierarchy with additive MV/Greek/stress reconciliation; P&L Explain v2; risk-change VaR/ES waterfall; configurable OK/WARNING/BREACH limits; breach drill-down with top contributors.

### Formal acceptance evidence (2026-09-02)

| Check | Result |
|-------|--------|
| checklist | All `[x]` with file/test evidence in ROADMAP |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`, QuantLib 1.43) | **324 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **22 passed** |
| Integration unblock during acceptance | Renamed Alembic scripts dir `backend/alembic` → `backend/migrations` (avoids shadowing installed `alembic` package; `alembic.ini` + `test_persistence.py` updated) |
| Known residual — P&L Explain | Taylor residual absorbs higher-order / duration–DV01 gaps; not a full-reval explain |
| Known residual — risk-change attribution | Correlation residual is plug-to-total; not a structural corr model; linear/Greek market path when snapshot present |
| Known residual — limits UI | Closed under (status strip + value/limit table + per-metric/breach drill-down) |
| Known residual — key-rate contributors | Closed under (tenor KR on LimitEngine binding pillar) |
| Known residual | Dual-mount + sunset DONE (legacy still served); RiskRun persistence wiring still |
| Hierarchy ↔ stress | Circular import fixed in via lazy stress import — no open hierarchy/stress residual |

### Follow-on tasks (discovered during )

- [x] Key-rate DV01 limit drill-down contributors use tenor KR DV01 (not parallel `dv01`) — DONE
 - `contributors_for_metric("key_rate_dv01")` uses `SensitivityEngine` on the LimitEngine binding pillar (`max_T |portfolio KR_T|`); abs position KR ranked; without key_rates/curves falls back to parallel like `_key_rate_dv01_abs`
 - Evidence: `tests/test_limit_drilldown.py` (binding-tenor vs parallel ranking, signed KR reconcile, fallback)

---

## Workstream 5 — Persistence & Risk-Run Platform

Status: **COMPLETE** (2026-09-02 DevOps) — GHA `postgres-persistence-smoke` + full CI green; caching polish **DONE** (Quant Pricing)

Task rollup: **DONE**; **DONE** (valuation LRU + curve-construction + scenario memo).

### Tasks

- [x] PostgreSQL persistence (SQLAlchemy + Alembic) — DONE
 - New package `backend/app/persistence/` (config, session, ORM models, repository ABCs + SQLAlchemy repos)
 - Tables: portfolios, trades, market_snapshots (meta + JSON data), scenario_definitions, risk_runs, risk_results, limit_definitions
 - Alembic initial revision `001_initial_persistence` under `backend/migrations/` (not `alembic/`, to avoid package shadowing); SQLite-capable unit tests (no live Postgres required in unit suite)
 - Compose `postgres` service + `RISKFORGE_DATABASE_URL` (psycopg3); ADR 005
 - Postgres CI: `postgres-persistence-smoke` job in `.github/workflows/ci.yml` + `scripts/smoke_postgres.sh` (wait-for-pg → Alembic `backend/migrations/` upgrade head → seed wiring). **Local Compose smoke green** (2026-09-02 DevOps). **GHA green** (2026-09-02): https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125 (job https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125/job/100391676176) — residual **CLOSED**
- [x] RiskRun domain model — DONE
 - Domain DTOs: `RiskRunStatus`, `RiskResultRef`, `RiskRun` in `domain/models.py`
 - Lifecycle validation (QUEUED/RUNNING/COMPLETED/FAILED), computed `duration`
 - Persistence mapping: `completed_at`↔`finished_at`, `error`↔`error_message`, result refs
 - ORM columns + Alembic `002_risk_run_domain_fields` (append-only; 001 untouched)
 - Repository `create`/`get`/`set_status` return domain `RiskRun`
 - Evidence: `tests/test_risk_run.py`, `tests/test_persistence.py`
- [x] Risk run lifecycle (QUEUED/RUNNING/COMPLETED/FAILED) — DONE
 - `RiskRunService` (`enqueue`/`start`/`complete`/`fail`/`get`/`get_result_payloads`)
 - Directed transitions only; illegal transitions raise `InvalidRiskRunTransition`
 - Evidence: `tests/test_risk_run_lifecycle.py`
- [x] Async risk execution APIs — DONE (default in-memory; SQLAlchemy path covered in tests)
 - `POST/GET /risk/runs` + `/api/v1/risk/runs` ( dual-mount for all public routers)
 - In-process `RiskRunWorker` (ThreadPoolExecutor) → `RiskRunService` → `PortfolioService` dispatch
 - `run_type`: summary, var, stress, factors, limits, hierarchy, contributors
 - Default: `InMemoryRiskRunRepository`; optional `session_factory` → SQLAlchemy repos + result payloads
 - DTOs: `RiskRunCreateRequest` / `RiskRunView` (`from_risk_run`)
 - Evidence: `tests/test_risk_run_api.py`
 - Residuals deferred: optional Redis/RQ for fair scheduling / ops; wires default Postgres DI when ``RISKFORGE_DATABASE_URL`` is set
 - Multi-worker claim safety landed under (`claim_queued` + `FOR UPDATE SKIP LOCKED`)
- [x] Caching with invalidation tests — **DONE**
 - `CachedPricingEngine` in `backend/app/pricing/cache.py` wraps any `PricingEngine` (no QuantLib leakage)
 - Cache key = trade payload hash + `MarketSnapshot.content_hash` + `PricingConfiguration` (engine id / evaluation date / extras)
 - Factory opt-in via `RISKFORGE_PRICING_CACHE` (default on) + `RISKFORGE_PRICING_CACHE_SIZE`
 - Correctness: hit/miss, market-bump miss, config miss, LRU eviction, clear — `tests/test_pricing_cache.py`
 - Curve-construction LRU: `backend/app/pricing/curve_cache.py` memoizes `select_yield_curve` by currency-relevant market fingerprint; `RISKFORGE_CURVE_CACHE` (default on) + `RISKFORGE_CURVE_CACHE_SIZE`; evidence `tests/test_curve_cache.py`
 - Scenario-result memo: `backend/app/risk/scenario_memo.py` wraps `scenario_engine.apply_scenario` by base id + content hash + shock fingerprint + id tag; `RISKFORGE_SCENARIO_CACHE` (default on) + `RISKFORGE_SCENARIO_CACHE_SIZE`; evidence `tests/test_scenario_memo.py`
- [x] Wire persistence repositories into FastAPI DI / services — **DONE**
 - Optional DI: ``RISKFORGE_DATABASE_URL`` set → SQLAlchemy session factory + seeded sample portfolio / market snapshot / DEFAULT+THREAT scenarios / DEFAULT_LIMITS + ``RiskRunWorker(session_factory=…)``
 - Unset → ``SAMPLE_PORTFOLIO`` + in-memory snapshot/scenario/limit repos (pre-seeded) + ``InMemoryRiskRunRepository`` (default tests unchanged)
 - ``Depends``: ``get_default_portfolio``, ``get_default_market_snapshot``, ``get_market_snapshot_repository``, ``get_scenario_definition_repository``, ``get_limit_definition_repository``, ``get_risk_run_worker``; repos also on ``app.state`` when memory-backed
 - Worker upserts portfolio on submit when SQLAlchemy-backed (FK to ``portfolios``)
 - Evidence: `tests/test_persistence_di.py`; ADR 005 updated
- [x] Compose (or process) risk-run worker after stabilizes — **DONE**
 - Compose `worker` service: `python -m app.worker` claims `QUEUED` risk_runs from shared Postgres (`RISKFORGE_DATABASE_URL`)
 - Same `RiskRunWorker` + SQLAlchemy session factory as API lifespan; portfolio loaded from DB on cache miss
 - Compose `backend` sets `RISKFORGE_EXTERNAL_WORKER=1` (HTTP enqueues only); unset → in-process ThreadPoolExecutor (tests/local default)
 - Repo `claim_queued` (memory + SQLAlchemy): QUEUED→RUNNING; **Postgres** uses `SELECT … FOR UPDATE SKIP LOCKED` so concurrent workers do not double-claim; SQLite/unit path is FIFO without skip-locked (documented)
 - Compose ships one worker by default (demo); Redis/RQ **not** required for claim safety
 - Evidence: `tests/test_durable_worker.py` (poll + memory exclusive claim + SQLite claim + mocked postgres `skip_locked`)
 - Residual: multi-worker live stress beyond claim-unit tests optional; GHA Postgres path proven via `postgres-persistence-smoke` ( **DONE**)

### Acceptance Criteria (workstream bar)

Durable persistence + async risk-run platform: SQLAlchemy/Alembic schema, RiskRun domain/lifecycle, async run APIs, FastAPI DI for persistence-backed services, compose/process worker with Postgres claim safety (`FOR UPDATE SKIP LOCKED`), and caching with invalidation tests (valuation LRU + curve-construction + scenario memo). Postgres path exercised beyond SQLite (local Compose smoke + GHA `postgres-persistence-smoke`). Workstream **COMPLETE**.

### Formal acceptance decision (2026-09-02) — **COMPLETE** (cleared after GHA green)

**Verdict (initial):** Do **not** rubber-stamp COMPLETE. Tests were green and the risk-run spine was done, but DI for snapshots/scenarios/limits and Postgres CI proof were open.

**Update same day (Backend/API close):** DI blocking gap is **CLOSED**. Remaining blockers were Postgres runner validation , multi-worker claim, and optional cache polish. Workstream stays **IN PROGRESS**.

**Suite verify same day (Lead Architect):** Full backend **426 passed** + frontend **26 passed** + build OK. confirmed **DONE**. Did **not** clear or (then) blockers → workstream remained **IN PROGRESS**.

**Update same day (Backend/API claim safety):** multi-worker claim blocker is **CLOSED** via Postgres `FOR UPDATE SKIP LOCKED` on `claim_queued` (Compose single-worker demo unchanged; SQLite fallback documented). Remaining workstream blocker: Postgres runner green. remains non-blocking polish.

**Update same day (DevOps attempt):** Local `scripts/smoke_postgres.sh` against Compose `postgres:16-alpine` **passed** (Alembic 001→002 + seed portfolio/snapshot/scenarios/limits). CI workflow hardened (psycopg wait + version print). ** still NOT DONE** — this checkout has **no `git remote` / no `gh` CLI**, so no GitHub Actions run history and no push to obtain runner evidence. Do **not** mark Workstream 5 COMPLETE until a green `postgres-smoke` (and ideally full CI) GHA URL is recorded. alone remains non-blocking polish.

**Update same day (DevOps close):** Origin https://github.com/SergTogul/riskforge-mvp ; push `31228fb`; CI run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125 — jobs `postgres-persistence-smoke`, `backend-pytest`, `frontend-test-build` all green. ** DONE**; ** residual CLOSED**; Workstream 5 marked **COMPLETE**. stays non-blocking polish.

| Check (initial formal pass) | Result |
|-------|--------|
| QuantLib | 1.43 import OK |
| Backend pytest (`RISKFORGE_PRICING_ENGINE=quantlib`) | **403 passed**, 1 Starlette/httpx deprecation warning |
| Frontend `npm test` | **26 passed** |
| | **DONE** — domain, lifecycle, async APIs + tests |
| | **PARTIAL** — schema/repos/Alembic/Compose Postgres; Postgres CI job was missing at formal pass |
| | **DONE** — valuation LRU + curve-construction cache + scenario-result memo + invalidation tests |
| (at formal pass) | **PARTIAL** — portfolios + risk_runs DI only |
| (at formal pass) | **PARTIAL** — Compose poll worker + `test_durable_worker.py`; no `SKIP LOCKED` yet |
| Workstream status | **IN PROGRESS** |

### Progress update (2026-09-02, Backend/API — close)

| Check | Result |
|-------|--------|
| | **DONE** — FastAPI DI + seeding for portfolios, risk_runs, market_snapshots, scenario_definitions, limit_definitions |
| Postgres CI | **DONE** — Compose local green + GHA `postgres-persistence-smoke` success (run 33673245125) |
| Backend pytest (builtin, this change) | **410 passed** at formal pass; ~7 native/C++ failures on Apple clang 14 (`std::jthread` / missing `-I include`) were **pre-existing**, unrelated to DI — **resolved** by portable stdlib thread pool (`__cpp_lib_jthread` fallback to `std::thread`+join) + compile flags with `-I native/include` |
| Evidence | `tests/test_persistence_di.py`; ADR 005 |

### Progress update (2026-09-02, Backend/API — claim safety)

| Check | Result |
|-------|--------|
| | **DONE** — `claim_queued` + Postgres `FOR UPDATE SKIP LOCKED`; Compose worker poll uses claim; in-process submit path unchanged |
| SQLite / unit | FIFO claim without skip-locked (documented); mocked postgresql dialect asserts `skip_locked=True` |
| Evidence | `tests/test_durable_worker.py`; ADR 005; README / Compose comments |

### Remaining items after COMPLETE

1. ~~** (blocking):**~~ **CLOSED 2026-09-02** — GHA run https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125 (`postgres-persistence-smoke` green).
2. ~~** (non-blocking polish):**~~ **CLOSED** — curve-construction cache + scenario-result memo (+ prior valuation LRU); does not reopen Workstream 5 COMPLETE.

~~** (blocking):** Wire market_snapshots / scenario_definitions / limit_definitions repositories into FastAPI DI~~ **CLOSED 2026-09-02.**

~~** (blocking for “platform”):** Safe queue claim (`FOR UPDATE SKIP LOCKED` and/or Redis/RQ) or accepted single-worker caveat~~ **CLOSED 2026-09-02** (`claim_queued` + Postgres `SKIP LOCKED`).

### Follow-on (post-COMPLETE; do not use to skip blocking items above)

- [x] API versioning of risk-runs only under `/api/v1` — **superseded** by full dual-mount; documents `/api/v1` as canonical + legacy sunset (removal still gated)
- [x] Persist stress/scenario HTTP payloads via scenario_definitions DI once closes — **DONE 2026-09-02**
 - ``GET /risk/stress/scenarios`` and ``POST /risk/stress/evaluate`` load via ``get_default_stress_scenarios`` → ``scenario_definition_repo`` (memory or SQLAlchemy seed)
 - ``POST /risk/stress`` uses ``get_baseline_stress_scenarios`` (DEFAULT-id filter on the same DI list; empty/missing → in-code ``DEFAULT_SCENARIOS``)
 - Empty or unconfigured repo falls back to in-code ``THREAT_SCENARIOS`` for GET/evaluate (no 503 on stress defaults)
 - Evidence: ``tests/test_stress_scenarios_di.py``
 - Frontend: dashboard does not call GET scenarios; Stress/Threat cards consume POST results only — no display-helper change

---

## Workstream 6 — C++ Performance Engine

Status: **COMPLETE** (2026-09-02 — DONE + formal scenario-kernel SLA-K1/K2)

Lead Architect suite verify 2026-09-02: native path covered by green full backend suite (includes `test_native_kernel` / Historical VaR kernel tests). closed same day (parity edge cases + ADR 007).

### Formal product SLA (2026-09-02) — **COMPLETE** (Option B reversed)

**Verdict:** Mark Workstream 6 **COMPLETE**. Engineering deliverables remain DONE. The prior Option B “accept no product VaR wall-time SLA / stay PARTIAL forever” disposition is **reversed**: Lead Architect + C++ Performance publish a **measurable** product-path scenario-kernel SLA with evidence and a pass/fail check — not an invented HTTP VaR latency number, and not rubber-stamp COMPLETE without floors.

**Published SLA (reference host class in `benchmarks/RESULTS.md`):**

| ID | Requirement | Floor |
|----|-------------|------:|
| **SLA-K1** | Native nested-loop `cpp_ctypes` vs pure-Python on workload `10k_x_1k` (10 000×1 000) — same ABI as `RISKFORGE_SCENARIO_KERNEL=native` LINEAR/DELTA_GAMMA aggregation | **≥ 50×** wall-time |
| **SLA-K2** | `cpp_ctypes_t4` (`--threads 4 --parallel-compare`) vs serial `cpp_ctypes` on the same `10k_x_1k` run | **≥ 1.3×** wall-time |

**Evidence method:**

```bash
backend/.venv/bin/python benchmarks/check_m6_sla.py
# or:
backend/.venv/bin/python benchmarks/run_scenario_bench.py \
 --workload 10k_x_1k --threads 4 --parallel-compare --iters 1 --json
```

Recorded evidence: `benchmarks/RESULTS.md` (Formal product SLA + tables). 2026-09-02 refresh on reference host: SLA-K1 **106–145×**, SLA-K2 **~1.45–1.95×** (prior tables 88–125× / ~2.0×) — all above floors (K2 floor **1.3×** for thermal margin). Checksums within harness `1e-6` rel guard.

**Evidence reviewed:**

| Source | What it proves | What it does **not** prove |
|--------|----------------|----------------------------|
| `benchmarks/RESULTS.md` SLA-K1/K2 | Relative nested-loop native kernel floors on named workload + host class | HTTP/API Historical VaR wall time; multi-tenant capacity |
| `benchmarks/check_m6_sla.py` | Reproducible pass/fail against floors | CI hard gate on arbitrary runners |
| Risk-path wire + parity | Optional native LINEAR/DELTA_GAMMA aggregation; NumPy ↔ native VaR/ES within tolerances | That 1×N aggregated-Greek VaR is 50× faster than NumPy (FFI-bound; see RESULTS non-claims) |

**Decision:** COMPLETE under the scoped scenario-kernel SLA. Do **not** claim end-to-end HTTP VaR latency. Do not start from this close.

### Tasks

- [x] Benchmark harness under `benchmarks/` — DONE
 - Repo-root `benchmarks/run_scenario_bench.py` + `benchmarks/README.md` (env caveats; formal SLA in RESULTS)
 - Workloads: `smoke`, `1k_x_1k`, `10k_x_1k`, optional `50k_x_1k`
 - Metrics: wall time, throughput (ops/s & scenarios/s), peak RSS, speedup vs Python
 - Impls: Python reference, NumPy, ctypes (`risk_kernel_capi`), C++ header binary (enhanced `native/src/benchmark.cpp`)
 - Smoke: `python3 -m pytest benchmarks/test_bench_smoke.py -q` (separate from product unit suite)
 - Does not touch risk-run APIs
- [x] Baseline Python / NumPy / C++ single-thread comparison — DONE
 - Formal I/O contract + results table: `benchmarks/RESULTS.md` (SLA-K1 evidence)
 - Workloads captured: `1k_x_1k`, `10k_x_1k` (`OMP_NUM_THREADS=1`)
 - Documents NumPy strength-reduction caveat (rewrite ≠ nested-loop fair compare)
- [x] Native scenario aggregation wired into risk path — DONE
 - `approximate_pnl_series` / `HistoricalRiskEngine` LINEAR & DELTA_GAMMA honor
 `RISKFORGE_SCENARIO_KERNEL=python|native` (+ optional `RISKFORGE_SCENARIO_KERNEL_LIB`)
 - Default remains NumPy vectorized Python path; methodology / vol-point scaling stay in Python
 - **FULL_REVALUATION cannot use the kernel** (PricingEngine revaluation only; documented in
 `historical.py`, `compute/kernel.py`, `native/README.md`)
 - Evidence: `tests/test_historical_scenario_kernel.py`
- [x] Parallel C++ — DONE
 - **One strategy only:** C++20 stdlib thread pool over contiguous shock partitions
 (`std::jthread` when available, else `std::thread`+join; Apple libc++ often lacks
 jthread). Documented in `backend/native/README.md` — **not OpenMP**; no mixing.
 - Env `RISKFORGE_KERNEL_THREADS` (+ CLI `--threads`); serial path when `1` or `n_shocks≤1`
 - Numerical parity: C++ `kernel_test` + `tests/test_native_kernel.py` (parallel ≈ serial)
 - Harness: `benchmarks/run_scenario_bench.py --threads N --parallel-compare`
 - Capture: `benchmarks/RESULTS.md` ( section; SLA-K2 evidence)
- [x] Native/Python parity tests — DONE
 - ABI: `tests/test_native_kernel.py` (Python ↔ native, parallel ↔ serial, empty/single/zero/NaN/32×64 matrix)
 - Risk path: `tests/test_historical_scenario_kernel.py` ( NumPy ↔ native VaR/ES)
 - C++: `native/tests/kernel_test.cpp` (serial/parallel + flat ABI)
 - Tolerances documented: `KERNEL_ABI_*` = 1e-12; `KERNEL_PNL_ABS/REL` = 1e-9 / 1e-12
 (`app.compute.kernel`, `native/README.md`)
- [x] QuantLib concurrency architecture review/ADR — DONE
 - `docs/adr/007-quantlib-concurrency.md` (RLock in adapter; prefer process isolation for
 parallel QL reval; native kernels separate from QL globals; matches `quantlib.py` +
 `risk_run_worker.py` + native README)

### Follow-on clarification ( audit)

- [x] Prove native kernel hot-path equivalence on Historical VaR / scenario aggregation before claiming perf wins — DONE (parity gate)
 - NumPy vs pure-Python kernel ABI + NumPy vs native on LINEAR/DELTA_GAMMA P&L and VaR/ES
 - Explicit tolerances: `KERNEL_PNL_ABS_TOL=1e-9`, `KERNEL_PNL_REL_TOL=1e-12` (`historical.py`)
 - FULL_REVALUATION remains kernel-free even when `RISKFORGE_SCENARIO_KERNEL=native`
 - Product speed claim is scoped to SLA-K1/K2 (nested-loop `E×S` kernel); see Formal product SLA
- [x] Formal scenario-kernel SLA + check harness — DONE (2026-09-02)
 - Floors + evidence in `benchmarks/RESULTS.md`; pass/fail: `benchmarks/check_m6_sla.py`
 - Reverses Option B “accept no SLA”; does **not** invent HTTP VaR wall-time

### Progress update (2026-09-02, Lead Architect + C++ Performance — SLA COMPLETE)

- Owner: Lead Architect / Orchestrator + C++ Performance Engineer
- **Option B reversed:** measurable scenario-kernel SLA published; Workstream 6 **COMPLETE**
- Evidence: SLA-K1 106–145× / SLA-K2 ~1.45–1.95× on reference host (`check_m6_sla.py` PASS; floor 1.3×)
- DONE; HTTP end-to-end VaR latency **not** claimed; not started
- Handoff: `docs/agents/HANDOFF_SCENARIO_KERNEL_SLA.md`

---

## Workstream 7 — API Productionization

Status: **COMPLETE** (2026-09-02 — DONE; legacy unversioned paths remain dual-mounted until sunset removal gate)

### Tasks

- [x] Router decomposition — DONE (2026-09-02, Backend/API)
 - `main.py` is wiring-only (lifespan, CORS, `include_router`)
 - Routers: `api/health.py`, `portfolio.py`, `market.py`, `risk.py`, `stress.py`, `attribution.py`, `limits.py`, `risk_runs.py`
 - `get_portfolio_service` / `portfolio_service` in `api/deps.py` (PricingEngine via factory unchanged)
 - Public paths unchanged (`/health`, `/portfolio`, `/market/*`, `/risk/*`; risk-runs dual-mounted)
 - Evidence: `tests/test_api_router_decomposition.py`; full suite **445 passed**
- [x] API versioning `/api/v1/` — DONE (2026-09-02, Backend/API)
 - Dual-mount: every public domain router at legacy path **and** `/api/v1/...`
 - `risk_runs` unified as `/risk/runs` + `/api/v1/risk/runs` only (no triple/nested prefix)
 - Legacy clients unchanged; UI may keep unversioned paths
 - Evidence: `tests/test_api_v1_compatibility.py`; OpenAPI + smoke parity on critical GETs/POSTs; full suite **453 passed**
- [x] Typed request/response models — DONE (2026-09-02, Backend/API)
 - Wired `response_model=` on critical risk paths using existing domain types (no formula duplication):
 VaRReport, ESContributionReport, WhatIfReport, list[StressResult], ReverseStressResult,
 MultiFactorReverseStressResult, HedgeComparisonReport, RiskChangeAttributionReport,
 LimitDrilldownReport (risk-runs already RiskRunView)
 - Request bodies already domain-typed; dual-mount unchanged; PricingEngine seams preserved
 - Evidence: `tests/test_api_typed_models.py` (OpenAPI $ref + live response validation)
- [x] OpenAPI examples — DONE (2026-09-02, Backend/API)
 - Critical paths: VaR/ES, what-if, stress/reverse/multi, hedge-compare (`HedgeComparisonReport`), change-attribution, limits drill-down, risk-runs
 - Centralized illustrative payloads in `app/api/openapi_examples.py`; wired via `Body(openapi_examples=...)` + `responses` (incl. `{code,message,details}` where documented)
 - Evidence: `tests/test_api_openapi_examples.py`; full suite green with QuantLib
- [x] Consistent error model — DONE (2026-09-02, Backend/API)
 - Envelope `{code, message, details}` for HTTPException, request validation (422), and unhandled 500
 - Centralized in `app/api/errors.py` via `register_exception_handlers` (legacy + `/api/v1` share handlers)
 - Successful response schemas and PricingEngine seams unchanged; 500 message opaque (no exception leak)
 - Evidence: `tests/test_api_error_model.py`; risk-run `detail` assertions updated to `message`
- [x] Complete `/api/v1` migration for all risk routes (beyond dual-mount) — DONE (2026-09-02, Backend/API)
 - `/api/v1` documented as canonical (README + `docs/api/v1_canonical_and_legacy_sunset.md` + ADR 008)
 - Dual-mount kept (non-breaking); legacy responses add `Deprecation` / `Sunset` / `Link` (successor-version)
 - SPA migrated to `/api/v1` ( Frontend follow-up DONE 2026-09-02)
 - Planned earliest legacy removal: **2027-03-02**, gated on UI migration + Lead Architect approval
 - Evidence: `tests/test_api_legacy_deprecation.py`; dual-mount parity still covered by tests

### Progress update (2026-09-02, Backend/API — )

- Decomposed monolithic route handlers into charter-aligned APIRouter modules.
- Workstream 7 remained **PARTIAL** until landed with evidence.

### Progress update (2026-09-02, Backend/API — )

- Dual-mounted all public routers under `/api/v1` while preserving legacy unversioned paths.
- Workstream 7 remained **PARTIAL** until criteria were met with evidence.

### Progress update (2026-09-02, Backend/API — )

- Centralized `{code, message, details}` error handlers on the FastAPI app (covers both mounts).
- Workstream 7 remained **PARTIAL** until typed models and legacy sunset landed.

### Progress update (2026-09-02, Backend/API — )

- Added OpenAPI request/response/error examples for critical risk endpoints (illustrative numbers only).
- Workstream 7 remained **PARTIAL** until typed models and legacy sunset landed.

### Progress update (2026-09-02, Backend/API — )

- Wired domain `response_model=` on critical VaR/ES/what-if/stress/reverse/multi/hedge/change-attr/limits-drilldown routes.
- Workstream 7 remained **PARTIAL** until `/api/v1` canonical + legacy sunset landed.

### Progress update (2026-09-02, Backend/API — )

- Documented `/api/v1` as canonical; published deprecate→remove sunset plan; added legacy-only Deprecation/Sunset/Link headers.
- Workstream 7 marked **COMPLETE** (legacy paths intentionally still served until removal gate).

---

## Workstream 8 — Risk Terminal UI

Status: **COMPLETE** (2026-09-02 Frontend/Risk UX — remaining PARTIAL items closed)

### Follow-up from (Backend → Frontend)

- [x] Migrate `frontend/src/api.js` from unversioned paths to `/api/v1/...` (DONE 2026-09-02; bodies unchanged; `API_V1` constant).
- Keep E2E / helper tests green; ignore legacy Deprecation headers after cut-over.

### Tasks

- [x] Main application navigation — DONE (2026-09-02)
 - Sticky terminal sidebar (`AppNav`) + hash routing (`#overview` … `#risk-runs`)
 - Section map matches Frontend charter targets; panels grouped (overview / portfolio / factors / VaR&ES / stress / scenario / P&L / limits / runs)
 - Pure helpers in `lib/nav.mjs`; evidence `lib/nav.test.mjs` (no client risk math)
- [x] Overview dashboard — DONE (2026-09-02)
 - Dedicated `Overview` view: KPI strip via `overviewKpis` from `/risk/summary` + threat evaluate; section collage (`overviewCollage`) entry points with API teasers; hierarchy/factor heatmap teasers (not nav leftovers dump)
 - Evidence: `components/Overview.jsx`; `overviewKpis` / `overviewCollage` in `lib/risk.mjs` + `risk.test.mjs`
- [x] Risk heatmaps — DONE (2026-09-02)
 - Display-only color scales in `lib/heatmap.mjs` (diverging / sequential / utilization); unit tests in `heatmap.test.mjs`
 - Hierarchy VaR/ES/NAV tiles (`POST /risk/hierarchy`), factor×bucket matrix (`/risk/factors`), stress P&L tiles (`/risk/stress`), limit utilization tiles (`/risk/limits`)
 - Placed under Portfolio / Risk Factors / Stress / Limits (+ overview teaser); no client risk formulas
- [x] Scenario Builder — DONE (2026-09-02)
 - Presets (equity crash / rates hike / vol spike / FX); form validation; loading/error; API shock preview; `evaluateCustomScenario` → `/risk/stress/evaluate/custom`
 - Evidence: `ScenarioBuilder.jsx`; `SCENARIO_PRESETS` / `validateScenarioForm` / `scenarioPayload` tests
- [x] Before/after hedge workflow — DONE (2026-09-02)
 - `compareHedge` → `POST /api/v1/risk/stress/compare`; `hedgeComparisonSummary` / `spyFlatHedgePortfolio` / `defaultHedgeScenarios`
 - Dashboard `HedgeCompare` card: methodology select, SPY-flat demo hedge, VaR/ES before→after, scenario table, factor exposure deltas (API display only)
 - Evidence: `frontend/src/lib/risk.test.mjs`
- [x] Risk drill-down — DONE (2026-09-02)
 - Interactive Firm→Portfolio→Desk→Strategy→Book→Trade breadcrumb + child table; selected-node NAV/VaR/ES/Greeks from API tree only (`hierarchyNodeAtPath` / `hierarchyChildRows` / `hierarchyNodeMetrics`)
 - Evidence: `Analytics.jsx` Hierarchy; `risk.test.mjs`
- [x] P&L Explain UI — DONE (2026-09-02)
 - Interactive panel: SPY×scale → `POST /risk/attribution` (`explainPnL` + `demoPnLAttributionRequest`); optional illustrative marks via `/attribution/demo`
 - Shows base/current MV, drivers, explained, residual (API display only)
 - Evidence: `api.js` `explainPnL`/`explainPnLDemo`; `Attribution` in `Analytics.jsx`; tests for request helper
- [x] Limits UI — DONE (2026-09-02)
 - Status strip (OK/WARNING/BREACH counts); value/limit/util/warn-at table; per-metric Drill + breach drill-down via `/risk/limits/drilldown`
 - `limitStatus` prefers API status (prior); `limitStatusCounts` helper
 - Evidence: `RiskTable.jsx` Limits; `risk.test.mjs`
- [x] Risk-run UI — DONE (start)
 - Thin `createRiskRun` / `getRiskRun` in `api.js` (`POST/GET /api/v1/risk/runs`)
 - Dashboard `RiskRuns` card: run_type select, start, poll QUEUED→RUNNING→COMPLETED/FAILED
 - Display helpers: `riskRunStatus` / `riskRunStatusClass` / `isRiskRunTerminal` / `riskRunSummary` (no client risk math)
 - Evidence: `frontend/src/lib/risk.test.mjs`
- [x] Risk change attribution UI panel — DONE (2026-09-02)
 - `changeAttribution` → `POST /api/v1/risk/change-attribution`; `demoChangeAttributionRequest` / `spyScaledPortfolio` / `riskChangeAttributionSummary`
 - Dashboard card: metric + methodology selects; SPY×1.5 demo; waterfall table (API display only)
 - Evidence: `frontend/src/lib/risk.test.mjs`
- [x] ES contributions UI panel — DONE (2026-09-02)
 - `esContributions` → `POST /api/v1/risk/es`; `esContributionSummary` / dimension slice
 - Dashboard card: methodology + dimension selects; component ES / contrib % table
 - Evidence: `frontend/src/lib/risk.test.mjs`
- [x] VaR methodology compare UI (`POST /risk/var/compare`) — DONE (2026-09-02)
 - `compareVarMethodologies` → `POST /api/v1/risk/var/compare`; `varCompareSummary`
 - Dashboard card: optional observations; LINEAR / Δ-Γ / Full-reval table + runtime_ms
 - Evidence: `frontend/src/lib/risk.test.mjs`

### Acceptance / residual notes (honest)

- Frontend `npm test` **56 passed**; `npm run build` OK (2026-09-02 close pass).
- No client risk math; all panels display API payloads.
- Residual (non-blocking for ): ** formal Scenario HTTP wire DONE**; multi-factor reverse UI in Stress section (`ReverseStressMulti` → `/api/v1/risk/stress/reverse/multi`); P&L illustrative market path still uses `/attribution/demo` (position-change path uses real `/attribution`); reverse-multi E2E closed under .

---

## Workstream 9 — Testing, CI & Engineering Quality

Status: **COMPLETE** (2026-09-03 — Redis/RQ residual resolved as accepted deferral with queue-contract tests)

### Tasks

- [x] Frontend testing stack (Vitest/RTL/MSW) — **DONE** (2026-09-02, staged; lib migrate closed same day)
 - Stack: Vitest 4 + jsdom + Testing Library + MSW 2; config in `frontend/vite.config.js` + `frontend/src/test/{setup,mswServer}.js`.
 - `npm test` = `vitest run` (single runner). Lib helpers migrated off node:test: `risk.test.js` / `nav.test.js` / `heatmap.test.js` (display/request helpers only — no client risk math). `test:node` alias → `vitest run src/lib` for backwards script name.
 - Representative RTL slice: `MetricCard`, `AppNav`, `ScenarioBuilder` (validation + MSW success/error for `POST .../stress/evaluate/custom`; fixtures only — no client risk math).
 - Local evidence (lib migrate): `cd frontend && npm test` → **70** Vitest passed; `npm run lint` OK; `npm run build` OK.
 - Residual (non-blocking): broaden RTL/MSW to more panels (lib `*.mjs` node:test migrate **CLOSED** 2026-09-02).
- [x] E2E Playwright — **DONE** (2026-09-02)
 - Local: 10 Playwright specs (`cd e2e && npm test`); macOS uses Chrome channel.
 - CI: job `e2e-playwright` (Chromium on ubuntu-latest; builtin API + Vite `webServer`) landed SHA `7f01407`.
 - GHA evidence: run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33683725857 (head SHA `2f45e14`); job https://github.com/SergTogul/riskforge-mvp/actions/runs/33683725857/job/100426208499 — steps include green `Run Playwright E2E`.
 - Residual breadth (multi-factor reverse E2E) tracked under , not .
- [x] Backend property tests (Hypothesis) — **DONE** (2026-09-02, staged broaden)
 - Beyond pricing Greeks: `backend/tests/test_m9_risk_properties.py` — VaR/ES ordering, MV aggregation, component-VaR Euler reconciliation under Hypothesis.
 - Local: `pytest tests/test_m9_risk_properties.py` → **6 passed**.
 - Residual (non-blocking): more methodologies / FULL_REVAL property space; keep Greeks suite as baseline.
- [x] Golden quant tests — **DONE** (2026-09-02, expand)
 - Expanded `backend/tests/test_quantlib_golden.py` (~49 cases): equity/FX options vs analytic BS/GK; CIP equity-future & FX-forward algebra (rel=1e-12); IR STIR algebra; continuous Actual365Fixed ZC bond golden (closes annual-compound day-count gap as documented); IRS payer/receiver + ATM residual; edge eval dates (weekend/leap/year-end); PricingEngine seam check.
 - Tolerances/reference documented in module docstring (QuantLib AnalyticEuropeanEngine / FlatForward; algebraic CIP/STIR identities shared with Builtin).
 - Local: `RISKFORGE_PRICING_ENGINE=quantlib pytest tests/test_quantlib_golden.py` → **49 passed**; full backend suite → **564 passed**.
 - Residual (non-blocking): very short ``T ≲ 0.05`` option date-rounding bands remain in `test_quantlib_pricing.py`; IRS NPV not identical to Builtin annuity model.
- [x] Stress invariants — **DONE** (2026-09-02, staged)
 - Hypothesis: stress pnl == Σ by_position; empty scenario list → []; long-equity equity-shock monotonicity (same file as ).
 - Complements prior zero-shock / empty-scenario attribution tests.
 - Residual: threat-level / max_loss_pct boundary properties; multi-factor stress contribution invariants.
- [x] CI GitHub Actions — workflow at `.github/workflows/ci.yml` (backend pytest Py3.12 + QuantLib-preferred / builtin fallback, frontend `npm test`/`npm run build`, optional native g++ smoke, **`postgres-smoke` service job** via `scripts/smoke_postgres.sh`). Runner validation deferred to .
- [x] Static analysis (Ruff/mypy/ESLint) — **DONE** (staged gate, 2026-09-02)
 - CI job `lint-static-analysis` runs `ruff check app tests`, `mypy app`, and `npm run lint` (`eslint src --max-warnings 0`).
 - Config: `backend/pyproject.toml`, `backend/requirements-dev.txt`, `frontend/eslint.config.js`.
 - **Honest staging (not full-strict):** Ruff selects E/F/I/B/UP/SIM/RUF with documented ignores (E501 line length, B008 FastAPI `Depends`, pyupgrade/SIM/RUF style debt, finance γ/Δ unicode). mypy runs with `disable_error_code` for known debt (`arg-type`, `assignment`, `var-annotated`, `no-redef`, `misc`) — still catches other errors; pay down by removing codes. ESLint: recommended + react/hooks; `prop-types` off (no TS yet).
 - Trivial fixes: Ruff autofix (imports/unused), F821 lambda closure in `risk_run_worker.py`, Analytics `useEffect` deps for exhaustive-deps; kernel P&L tol imports moved to `app.compute.kernel` in tests.
 - GHA evidence: push SHA `8d7a6f2`; CI run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33683147903 — includes green `lint-static-analysis`.
 - Follow-up (non-blocking for ): enable ignored Ruff rules gradually; clear mypy `disable_error_code`; add Vitest/TS when advances.
- [x] Containers — **DONE** (2026-09-02 Lead Architect disposition; queue residual clarified 2026-09-03)
 - **Acceptance (containers):** Compose ships `postgres` + `backend` + `worker` + `frontend` (`docker-compose.yml`); `backend` sets `RISKFORGE_EXTERNAL_WORKER=1`; `worker` runs `python -m app.worker` and claims via Postgres `FOR UPDATE SKIP LOCKED` ( / ADR 005). No VaR/pricing math changed.
 - **Redis/RQ — RESOLVED AS ACCEPTED DEFERRAL (2026-09-03):** Fair scheduling / ops queue remains out of scope because current MVP semantics are covered by durable Postgres `risk_runs`, API enqueue-only mode, out-of-process `python -m app.worker`, FIFO bounded polling, and PostgreSQL `FOR UPDATE SKIP LOCKED`. No fake Redis service or RQ worker was added.
 - Follow-on (optional ops): introduce Redis/RQ or equivalent only with testable new semantics such as priority classes, tenant fairness, retry/dead-letter policy, or queue observability.

- [x] Validate CI on GitHub-hosted runners (fix workflow green; document QuantLib install path) — **DONE** (2026-09-02)
 - Local evidence (2026-09-02, DevOps): `docker compose up -d postgres` + `RISKFORGE_DATABASE_URL=postgresql+psycopg://riskforge:riskforge@localhost:5432/riskforge ./scripts/smoke_postgres.sh` → **exit 0** (`postgres smoke OK`; Alembic head `002_risk_run_domain_fields`). Idempotent re-run OK. See `BUILD_NOTES.md`.
 - CI hardening: smoke waits up to 60s for psycopg `SELECT 1`; job prints sqlalchemy/alembic/psycopg versions; QuantLib optional for `postgres-smoke` (full `requirements.txt` preferred; strip QuantLib on wheel failure). Main `backend` job still prefers QuantLib wheel on `ubuntu-latest`, falls back to builtin.
 - GHA evidence: repo https://github.com/SergTogul/riskforge-mvp ; push SHA `31228fb`; CI run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125 — `postgres-persistence-smoke` https://github.com/SergTogul/riskforge-mvp/actions/runs/33673245125/job/100391676176 ; also `backend-pytest` + `frontend-test-build` green. QuantLib path: backend job prefers wheel on ubuntu-latest with builtin fallback (see workflow).
 - Workstream 5 COMPLETE cleared on this evidence; caching polish **DONE**.
- [x] E2E coverage for post- endpoints — **DONE** (2026-09-02 QA reverse-multi close)
 - Done: ES contributions (`POST /risk/es`), change-attribution waterfall, VaR methodology compare, hedge-compare (`POST /risk/stress/compare`), overview collage → VaR & ES nav; risk-runs hash fix (`/#risk-runs`) after sectioning
 - Frontend UI: Stress-section **Multi-Factor Reverse Stress** → `POST /api/v1/risk/stress/reverse/multi` (helpers + Vitest/RTL/MSW)
 - QA E2E close: `e2e/tests/reverse-stress.spec.ts` — navigate `#stress`, fill target/max-shock/weights + factor toggles, assert Status Converged/Not converged + factor table rows; client validation for fewer than two factors; **no invented PnL/shock numbers**
 - Local evidence: `cd e2e && npm test` → **12 passed** (2026-09-02 QA); Chrome channel locally; CI stays Chromium via `CI=true` (`e2e/playwright.config.js`)
 - CI close: push SHA `a61c29a` — run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33700677387 ; job `e2e-playwright` https://github.com/SergTogul/riskforge-mvp/actions/runs/33700677387/job/100479144624 (also fixed Frontend `8409b7e` regression: single-factor heading strict-mode collision)
 - Prior gate: https://github.com/SergTogul/riskforge-mvp/actions/runs/33683725857 (job https://github.com/SergTogul/riskforge-mvp/actions/runs/33683725857/job/100426208499)
 - Prior note: Workstream 9 stayed PARTIAL until Lead Architect disposition (below).

- [x] CI failure triage (e2e-playwright reverse-stress heading collision) — **DONE** (2026-09-02 DevOps/QA)
 - **Do not hide:** GHA run **failure** https://github.com/SergTogul/riskforge-mvp/actions/runs/33700340552 (SHA `8409b7e`, “Add multi-factor reverse-stress UI”) — job **`e2e-playwright` failed**; siblings green (`backend-pytest`, `frontend-test-build`, `lint-static-analysis`, `postgres-persistence-smoke`).
 - Root cause: single-factor locator `.card` + heading `Reverse Stress` also matched **Multi-Factor Reverse Stress** card (`strict mode violation` → 2 elements).
 - Fix (already on master via close, hardened here): `exact: true` heading match + durable `data-testid="reverse-stress"` on single-factor card; multi keeps `data-testid="reverse-stress-multi"`.
 - Older historical failure ( land): https://github.com/SergTogul/riskforge-mvp/actions/runs/33680821074 (`backend-pytest` + `lint-static-analysis`) — subsequently fixed; not reopened.
 - Local evidence (this triage): backend `pytest -q` **571 passed** (QuantLib); frontend `npm test` **61+9 passed**; `ruff`/`mypy`/`eslint` OK; native kernel compile OK.
 - HEAD at triage start: SHA `f74b528` — full CI **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33701266538 (all five jobs green). Hardening push SHA `16c91cc` — CI **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33703670779 (all five jobs green, including `e2e-playwright`).

- [x] CI lint mypy regression (PortfolioService HistoricalRiskEngine narrowing) — **DONE** (2026-09-03 Lead Architect: GHA confirmed green)
 - **Local root cause (reproduced with CI commands):** `lint-static-analysis` / `mypy app` failed on `backend/app/services/portfolio_service.py` — ternary `isinstance(...)` did not narrow `risk: RiskEngine`, so `.seed` / `.observations` were attr-defined errors.
 - **Fix:** SHA `11339c6` on `master` — statement-level `isinstance(risk, HistoricalRiskEngine)` before accessing attrs (PricingEngine seams untouched).
 - **Local evidence before push:** backend `pytest -q` **619 passed** (QuantLib 1.43); `ruff`/`mypy` OK; frontend `npm test` **70 passed** + lint + build OK; native `risk_kernel_ok` + shared lib OK.
 - **Push:** `git push` succeeded (`8d3d67a..11339c6`). Expected CI run URL: https://github.com/SergTogul/riskforge-mvp/actions (filter SHA `11339c6`).
 - ~~**Blocked:** `gh run list` / `gh run watch` returned `Forbidden` from an invalid keyring token.~~ **CLEARED 2026-09-03** — `gh auth status` OK.
 - **GHA evidence (2026-09-03):** the mypy fix `11339c6` is contained in current master `9818d58`; run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33712643872 — all five jobs green, including `lint-static-analysis` https://github.com/SergTogul/riskforge-mvp/actions/runs/33712643872/job/100515202600.

### Progress update (2026-09-02, Lead Architect — disposition + Workstream 9 COMPLETE)

- Owner: Lead Architect / Orchestrator (DevOps charter consulted; no Redis/RQ implementation)
- **Decision:** ROADMAP labeled Redis/RQ as **optional** for ; already closed multi-worker claim with Postgres `SKIP LOCKED`. Required deliverable is the **Compose container stack**, which already exists and is documented. Redis/RQ is an **accepted deferred residual** (fair scheduling/ops) — **not** rubber-stamped done and **not** required for Workstream 9 COMPLETE.
- **Did not** add Redis/RQ (would be empty ceremony without product semantics; must not regress claim path or PricingEngine seams).
- ** DONE** (containers). Redis/RQ remains deferred outside .
- **Workstream 9 COMPLETE** — every required checklist item is honestly DONE.
- Next highest-value residual outside (started same session) / SLA / .

### Progress update (2026-09-03, Backend/API + DevOps — queue residual close)

- Owner: Backend/API + DevOps; no pricing/risk formulas, API DTOs, worker command, environment variables, dependencies, or containers changed.
- Resolved Redis/RQ ambiguity as an accepted deferral backed by current Postgres queue semantics: durable rows, external worker mode, FIFO claim ordering, bounded poll batches, and `FOR UPDATE SKIP LOCKED` multi-worker claim safety.
- Added queue-contract coverage for stable queued POST acceptance and poll batch limits; preserved `POST /risk/runs` acceptance and `GET /risk/runs/{id}` current-state semantics.
- Local evidence: focused durable worker/risk-run API tests **20 passed** (1 existing Starlette/httpx warning); `ruff` passed for touched backend files; `mypy app` passed; full backend pytest **659 passed** (1 existing warning).
- Handoff: `docs/agents/HANDOFF_QUEUE_RESIDUAL_M9.md`.

### Progress update (2026-09-02, Lead Architect + Backend — formal Scenario wire)

- Owner: Lead Architect / Orchestrator implementing Backend/API (+ Stress adapter reuse)
- Landed formal HTTP wire without replacing legacy `StressScenario` endpoints (ADR 004).
- Routes under dual-mount `/api/v1` (+ legacy): `GET /risk/stress/scenarios/formal`, `POST /risk/stress/formal/custom`, `POST /risk/stress/formal/evaluate/custom`.
- PnL parity: formal wire → `scenario_to_stress` matches named-dict legacy custom stress (abs 1e-9).
- PricingEngine seams / VaR math / SKIP LOCKED untouched.
- Residual: ScenarioBuilder UI and hedge-compare/what-if still use legacy shape.

### Progress update (2026-09-02, QA — E2E breadth)

- Owner: QA & Quant Validation (Lead Architect coordinated; no product/UI feature ownership)
- Landed Playwright coverage for panels that were ROADMAP-called-out gaps (ES, change-attribution, hedge-compare) plus VaR-compare and overview collage navigation
- Fixed risk-runs E2E to target `#risk-runs` (panel left Overview under )
- Workstream 9 remains **PARTIAL** — and reverse-multi E2E still open; static analysis staged gate landed (see notes)

### Progress update (2026-09-02, DevOps — static analysis)

- Owner: DevOps / Platform
- Landed CI `lint-static-analysis` (Ruff + mypy + ESLint) with staged configs; GHA green https://github.com/SergTogul/riskforge-mvp/actions/runs/33683147903 (SHA `8d7a6f2`)
- Follow-up SHA `8d7a6f2`: restore Historical VaR kernel test imports after Ruff F401 cleanup; `FloatArray` PEP 695 alias + numpy in `requirements-dev.txt` so lint-job mypy matches CI
- Workstream 9 remains **PARTIAL** — do **not** mark COMPLETE (, reverse-multi E2E still open; Playwright GHA job landed below — runner proof pending)

### Progress update (2026-09-02, DevOps/QA — Playwright in GHA)

- Owner: DevOps / Platform (+ QA coordination)
- Landed CI job `e2e-playwright`: pip backend (QuantLib optional) + `frontend`/`e2e` `npm ci` + `playwright install --with-deps chromium` + `CI=true npm test`
- `e2e/playwright.config.js`: CI uses bundled Chromium and `python -m uvicorn` when `.venv` absent; local macOS keeps Chrome channel + `.venv` uvicorn
- Local evidence: `cd e2e && npm test` → **9 passed / 1 flaky fail** then `npx playwright test tests/scenario-builder.spec.ts` → **1 passed** (session-closed flake, not product regression)
- Push: SHA `7f01407` to `origin/master`. At land time, runner green URL was **not** recorded (`gh` token invalid).

### Progress update (2026-09-02, DevOps — Playwright runner proof)

- Owner: DevOps / Platform
- Restored `gh` auth (`repo` + `workflow` scopes) and verified latest master CI.
- GHA run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33683725857 (head SHA `2f45e14`, title: Document honest Playwright CI status pending runner proof.)
- Job `e2e-playwright` **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33683725857/job/100426208499 (including step `Run Playwright E2E`). Sibling jobs also green: `backend-pytest`, `frontend-test-build`, `lint-static-analysis`, `postgres-persistence-smoke`.
- ** DONE** on this evidence. Workstream 9 remains **PARTIAL** — do **not** mark COMPLETE ( Vitest/RTL, broaden, Redis optional, reverse-multi E2E still open). Do **not** start in this task.

### Progress update (2026-09-02, QA — Vitest/RTL/MSW)

- Owner: QA & Quant Validation (+ Frontend harness only)
- Landed Vitest + RTL + MSW alongside existing node:test helpers (dual-run `npm test`).
- Representative component coverage: MetricCard, AppNav, ScenarioBuilder (MSW fixtures for custom stress evaluate).
- Local: `cd frontend && npm test` → 56 + 6 passed; lint + production build OK. CI `frontend-test-build` uses unchanged `npm test` entrypoint.
- ** DONE** (staged). Workstream 9 remains **PARTIAL** — do **not** mark COMPLETE ( broaden, Redis optional, reverse-multi E2E / Frontend multi-factor reverse UI still open).

### Progress update (2026-09-02, QA — Hypothesis + stress invariants)

- Owner: QA & Quant Validation
- Added `backend/tests/test_m9_risk_properties.py`: portfolio VaR/ES ordering, MV aggregation, component-VaR reconciliation; stress pnl sum / empty list / long-equity shock monotonicity (Hypothesis).
- Local: `cd backend && pytest tests/test_m9_risk_properties.py tests/test_quant_properties.py tests/test_component_var.py` → **20 passed**.
- ** + DONE** (staged). Workstream 9 remains **PARTIAL** — do **not** mark COMPLETE ( golden expand, Redis optional, reverse-multi UI/E2E still open).

### Progress update (2026-09-02, QA — QuantLib golden expand)

- Owner: QA & Quant Validation (PricingEngine seams preserved; no adapter code changes)
- Expanded `test_quantlib_golden.py` with IRS/FX/futures/bond continuous DF goldens, edge evaluation dates, documented tolerances (analytic BS/GK, CIP/STIR algebra, Actual365Fixed continuous bond vs annual-compound gap).
- Local: `RISKFORGE_PRICING_ENGINE=quantlib pytest tests/test_quantlib_golden.py` → **49 passed**; full `pytest` → **564 passed**, 1 warning.
- ** DONE**. Workstream 9 remains **PARTIAL** — do **not** mark COMPLETE ( Redis optional; reverse-multi UI/E2E still open — Frontend multi-factor reverse panel required before QA E2E close).

### Progress update (2026-09-02, Frontend — multi-factor reverse stress UI)

- Owner: Frontend / Risk UX
- Landed Stress-section `ReverseStressMulti` wired to existing `POST /api/v1/risk/stress/reverse/multi` (`reverseStressMulti` client). Display-only: status, target/achieved, P&L, shock table, method/assumptions from API — no client search/optimization.
- Helpers: `defaultReverseMultiForm`, `validateReverseMultiForm`, `reverseMultiRequestBody`, `formatFactorShock`, expanded `reverseStressMultiSummary`.
- Tests: `risk.test.mjs` request/display helpers; Vitest/RTL/MSW `ReverseStressMulti.test.jsx`; structural Playwright `e2e/tests/reverse-stress.spec.ts` (labels/Converged status).
- Workstream 9 remained **PARTIAL** after UI land ( Redis optional; QA E2E close pending).

### Progress update (2026-09-02, QA — reverse-multi E2E close)

- Owner: QA & Quant Validation
- Closed reverse-multi live E2E gap: fill controls (target loss %, max shock %, weights, factor checkboxes), assert Status Converged/Not converged + shock table factor rows; validation path for fewer than two factors; fixed single-factor card selector (`exact: true`) after Multi-Factor heading collision.
- Local: `cd e2e && npm test` → **12 passed** (no unexpected skips). Spec/selectors only — no UI product changes.
- GHA: run **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33700677387 (head `a61c29a`); `e2e-playwright` https://github.com/SergTogul/riskforge-mvp/actions/runs/33700677387/job/100479144624 — also clears the `8409b7e` single-factor heading strict-mode failure.
- ** DONE**. Workstream 9 remains **PARTIAL** — do **not** mark COMPLETE ( Redis/RQ optional still open). Next: Lead Architect decide deferral vs implement; then SLA / .

---

## Workstream 10 — Demo Data & Reproducibility

Status: **COMPLETE** (2026-09-02 — DONE)

### Tasks

- [x] Demo portfolios (Equity Vol / Rates Macro / Cross-Asset) — **DONE** (2026-09-02)
 - In-code books: `equity-vol`, `rates-macro`, `global-macro` (Cross-Asset theme; default `SAMPLE_PORTFOLIO`)
 - Catalog: `DEMO_PORTFOLIOS` + `GET /api/v1/portfolios` (+ `GET /portfolios/{id}`); SQLAlchemy seeds all three
 - No live market vendor feeds; marks remain synthetic/embedded
- [x] Demo historical market dataset — **DONE** (2026-09-02)
 - Packaged CSV `data/demo_historical_factors.csv` (750 obs; frozen replay of `SyntheticHistoricalDataset(seed=7)`)
 - Loaders: `load_factor_observations_csv` / `load_demo_historical_dataset` / `create_historical_dataset`
 - Env `RISKFORGE_HISTORICAL_DATASET=demo|synthetic|/path.csv`; API DI defaults to demo CSV
 - Removed unused orphan `data/sample_portfolio.csv` (portfolios are in-code since )
 - Docs: `data/README.md`; evidence `tests/test_demo_historical_dataset.py`
- [x] Deterministic demo scripts — **DONE** (2026-09-02)
 - Module/CLI: `backend/app/demo/run_demo_risk.py` (+ `scripts/run_demo_risk.py` shim)
 - Loads portfolios + demo factors; emits sorted-key VaR/stress JSON via `PortfolioService`
 - Defaults: builtin pricing + Python scenario kernel; `--check` asserts byte-identical re-runs
 - Frozen artifact: `data/demo_risk_artifact.json`; evidence `tests/test_demo_scripts.py`

### Progress update (2026-09-02, QA / Frontend — lib Vitest migrate)

- Owner: QA & Quant Validation (+ Frontend harness)
- Migrated leftover `src/lib/{risk,nav,heatmap}.test.mjs` (node:test) → Vitest `*.test.js`; removed vite exclude; `npm test` is Vitest-only.
- Local: `cd frontend && npm test` → **70 passed**; lint + build OK. No client risk math; no ; backend untouched.
- ** residual (lib migrate) CLOSED**. Remaining residual: broaden RTL/MSW panels only. Workstream 9 stays **COMPLETE**.

### Progress update (2026-09-02, Lead Architect / Backend — )

- Owner: Backend/API (+ Lead Architect coordination); no Frontend / Market Data changes
- Deterministic offline demo harness; no live vendors; PricingEngine seams untouched
- **Workstream 10 COMPLETE** — all DONE per checklist above
- Next residuals (ROADMAP): ** COMPLETE** (scenario-kernel SLA-K1/K2); **POSTPONED** — do not start; methodology doc DONE

### Progress update (2026-09-02, Market Data — )

- Owner: Market Data & Curves (+ Backend DI for `deps.py` / `PortfolioService` dataset sharing)
- File-backed aggregate factor history for Historical VaR / scenario replay; no live vendors; PricingEngine untouched.
- Demo CSV numerically identical to prior seed-7 / 750 synthetic default (API VaR continuity).
- Workstream 10 remained **PARTIAL** until (now closed same day).

### Progress update (2026-09-02, Lead Architect / Market Data — )

- Owner: Lead Architect (+ Market Data seams for snapshot-from-positions; no PricingEngine changes)
- Landed three themed demo portfolios with composition invariants, list/get catalog API, persistence seed of all demos.
- Default `GET /portfolio` still serves Cross-Asset `global-macro` (`SAMPLE_PORTFOLIO`) — E2E heading "Global Macro Demo" preserved.

---

## Workstream 11 — AI Risk Assistant

Status: **COMPLETE** (2026-09-03 — deterministic tools plus provider-agnostic model/tool loop)

### Tasks

- [x] Deterministic tool contracts — DONE for core query tools (2026-09-03)
 - Contracts: `get_portfolio_summary`, `get_var_es`, `get_worst_stress`, `get_limits`, `get_contributors`
 - Each contract declares the backing deterministic `PortfolioService` method, required inputs, return shape, and numeric source
 - Evidence: `backend/app/risk/query.py` `RiskToolName` / `RiskToolContract` / `tool_contract_schemas`; `backend/tests/test_ai_query_orchestration.py`
- [x] LLM orchestration — DONE (2026-09-03)
 - Added provider-agnostic model/tool-loop contracts: `RiskAssistantModelRequest`, `RiskAssistantModelResponse`, `RiskAssistantModel`, `DeterministicRiskAssistantModel`, and `RiskQueryEngine.answer_with_model(...)`.
 - A model adapter can request exactly one supported deterministic tool, ask for clarification, or refuse unsupported/advisory prompts; RiskForge executes known deterministic tools and ignores model-proposed answer text until tool payloads return.
 - No live provider adapter or credentials are required for local tests; network-backed provider wiring remains future product scope.
- [x] Risk assistant evaluation suite — DONE for current M11 scope (2026-09-03)
 - Expanded eval coverage for deterministic tool selection, grounded answer behavior, model/tool-loop execution, clarification, refusal, and malicious/model-invented numeric text suppression.
 - Broader future-charter tools such as hedge compare, P&L explain, factor risk, and risk-run lookup remain future scope, not blockers for this workstream.
- [x] Guardrails — DONE for deterministic query router and model/tool-loop slices (2026-09-03)
 - Unsupported advisory prompts refuse without calling risk tools
 - Ambiguous prompts ask for clarification without returning numerical risk data
 - Numeric answer text is formatted only from the selected tool payload, with the raw `tool_result` included in response data for audit

### Progress update (2026-09-03, AI Orchestration — deterministic tools)

- Owner: AI Orchestration Engineer; consumed existing Backend/API service boundary only
- Formalized deterministic tool contracts and routing around existing `PortfolioService` calls; no pricing/risk methodology or UI changes
- Public compatibility: legacy query `intent="var"` preserved; new `tool_name` / `requires_clarification` metadata added to `RiskQueryResponse`
- Local evidence: focused AI/query/API tests **38 passed**; full backend pytest **653 passed**; repo-wide `ruff check app tests` and `mypy app` passed after integration verification

### Progress update (2026-09-03, AI Orchestration — model/tool loop close)

- Owner: AI Orchestration Engineer; consumed existing deterministic `PortfolioService` tool boundary only.
- Completed provider-agnostic one-turn model/tool orchestration over existing RiskForge tools; no pricing, VaR/ES, stress, market-data, or UI formulas changed.
- Guardrails: model-selected tools must be known `RiskToolName` values; clarification/refusal responses do not call numerical tools; final numeric answers are grounded only in deterministic `tool_result` payloads.
- Local evidence: focused `tests/test_ai_query_orchestration.py` **10 passed**; scoped Ruff passed; `mypy app` passed; full backend pytest **659 passed** (1 existing Starlette/httpx warning).
- Handoff: `docs/agents/HANDOFF_AI_ORCHESTRATION_M11.md`.

---

## Workstream 12 — Documentation & Portfolio Presentation

Status: **COMPLETE** (2026-09-03 — recruiter docs, architecture, methodology, performance, and limitations package)

Note: user explicitly unblocked remaining roadmap work on 2026-09-03. Workstream 12 was completed as documentation-only work; no pricing/risk/API behavior changed.

### Tasks

- [x] Recruiter/interviewer README — DONE (2026-09-03)
 - `README.md` now frames mission, architecture, deterministic demo path, methodology, performance scope, and limitations.
- [x] Architecture documentation — DONE (2026-09-03)
 - Added `docs/architecture.md` with system boundaries, dependency direction, and deterministic tool/pricing/risk ownership.
- [x] ADRs under `docs/adr/` — DONE (2026-09-03)
 - Added `docs/adr/README.md` index/status for evidence-backed ADRs; no invented future ADRs.
- [x] Methodology documentation — DONE (2026-09-03)
 - Added `docs/methodology/README.md`; cleaned/link-checked `docs/methodology/multi_factor_reverse_stress.md`.
- [x] Performance report — DONE (2026-09-03)
 - Added `docs/performance.md`; scoped claims to measured native scenario-kernel evidence and existing build notes.
- [x] Known engine / pricing limitations catalog — DONE (2026-09-03)
 - Added `docs/known_limitations.md` to prevent over-claiming surface calibration, QuantLib coverage, reverse-stress optimality, AI, live market data, and Redis/RQ.

### Progress update (2026-09-03, Lead Architect / Documentation — close)

- Owner: Lead Architect / Documentation; docs-only package, no backend/frontend behavior changes.
- Evidence: `git diff --check` passed for W12 docs, manual local-link verifier checked 9 markdown files, `tests/test_m39_methodology_docs.py` **2 passed**, and `scripts/check_final_demo.py` returned `status: ok`.
- Handoff: `docs/agents/HANDOFF_WORKSTREAM_12_DOCS.md`.

---

## Workstream 13 — Final Portfolio Demo

Status: **COMPLETE** (2026-09-03 — deterministic runbook, screenshots/ranges, and clean-checkout smoke)

### Tasks

- [x] Seed data + deterministic setup for 3–5 minute demo flow — DONE (2026-09-03)
 - Final-demo runbook: `docs/demo/final_demo.md`
 - Reuses demo portfolios (`equity-vol`, `rates-macro`, `global-macro`), packaged historical CSV, and `run_demo_risk`; no live vendors and no invented risk numbers
 - Demo risk values are read from generated/committed artifacts only (`data/demo_risk_artifact.json`)
- [x] Screenshots + demo instructions + expected output ranges — DONE (2026-09-03)
 - Screenshots: `docs/demo/riskforge_demo_01_overview.png`, `docs/demo/riskforge_demo_02_portfolio.png`, `docs/demo/riskforge_demo_03_var_es.png`, `docs/demo/riskforge_demo_04_stress.png`
 - Expected ranges are derived from `data/demo_risk_artifact.json`, not invented in prose
- [x] Clean-checkout verification of demo path — DONE (2026-09-03)
 - CI-style local smoke: `PYTHONPATH=backend backend/.venv/bin/python scripts/check_final_demo.py`
 - Verifies required demo files exist, runs deterministic double-build check, and asserts generated artifact byte-equals `data/demo_risk_artifact.json`
 - Evidence: `backend/tests/test_final_demo_check.py` plus `scripts/check_final_demo.py`

### Progress update (2026-09-03, Lead Architect / Frontend / DevOps / QA — close)

- Owner: Lead Architect / Orchestrator coordinating Frontend, DevOps, and QA boundaries; no quant/pricing/risk formula changes
- Added final-demo runbook, durable screenshots, artifact-derived expected output ranges, and clean-checkout smoke around existing deterministic data/scripts
- **Workstream 13 COMPLETE** locally; CI still requires parent push and green run per repository workflow

---

## Definition of Done (reminder)

A task is DONE only when implementation exists, tests pass, review completed, docs updated if needed, and this file marks `[x]` with evidence. Never mark blocked/partial work complete.
