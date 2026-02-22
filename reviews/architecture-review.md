# RiskForge Architecture Review

Independent Principal / Senior Staff architecture review of the RiskForge repository as implemented on 2026-09-03.

Review only. No application source was modified as part of the review. ROADMAP task completion statuses were not updated.

Core product rule used as the review standard:

> The pricing library prices. RiskForge manages portfolio risk. The LLM orchestrates deterministic tools; it never calculates financial risk itself.

## Executive Summary

The intended split is visible in the import graph: QuantLib is confined to `backend/app/pricing/quantlib.py`, risk engines take `PricingEngine`, the C++ kernel is a 5×4 float ABI, and the UI/AI layers format API payloads rather than recompute VaR. That is real structure, not just README language.

The implementation still fails the product’s own rule in three places that will force rewrites if this is to become an institutional book:

1. **Trades are markets.** Positions carry spots, vols, yields, and FX rates. `PositionMarketDataProvider` then folds those marks into one `MarketSnapshot` with last-writer-wins on shared keys such as `rates["USD"]`. Stress, sensitivities, and full revaluation shock that collapsed snapshot.
2. **Default portfolio risk is four macro columns.** Historical LINEAR/DELTA_GAMMA (and the native kernel) consume one equity return, one vol move, one rate move, and one FX return, then broadcast them onto every name. That cannot represent a multi-asset book.
3. **The domain module is the HTTP contract.** `backend/app/domain/models.py` (~1,490 lines) holds positions, snapshots, every risk report, and FastAPI request bodies. Persistence stores JSON dumps of those same objects. Splitting transport from domain later will touch almost every layer.

Documentation overstates completeness (`ROADMAP.md` marks every workstream complete; `TASKS.md` is absent). The code is an honest, well-tested MVP with a clean pricing seam — not yet a scalable risk platform.

Finding counts:

- Critical: 2
- High: 10
- Medium: 8
- Low: 4
- Info: 3

## Architecture Map

Observed runtime shape:

```text
React SPA (frontend/src)
  POST full Portfolio JSON
    → FastAPI /api/v1 (and deprecated unversioned dual-mount)
      → process-wide PortfolioService
        → StressEngine / HistoricalRiskEngine / VaRAnalytics /
           HierarchyEngine / LimitEngine / AttributionEngine / RiskQueryEngine
          → PricingEngine (CachedPricingEngine → QuantLib | Builtin)
          → MarketSnapshot.bump / apply
          → optional NativeScenarioKernel (LINEAR / DELTA_GAMMA only)
    → optional SQLAlchemy JSON repos (when RISKFORGE_DATABASE_URL set)
    → RiskRunWorker (in-process threads or Compose process + SKIP LOCKED)
```

| Layer | Actual location | Role |
|---|---|---|
| Domain | `backend/app/domain/models.py` (single file) | Positions, snapshot, **and** API/result DTOs |
| Pricing | `interfaces/pricing.py`, `pricing/` | `PricingEngine`; QuantLib + builtin + cache |
| Market data | `market/snapshot.py`, `curves.py`, `vol_surfaces.py`; bump logic **inside** `MarketSnapshot` | Snapshot build; curves/surfaces as `dict` |
| Risk | `risk/historical.py`, `var.py`, `sensitivities.py`, `factors.py`, `hierarchy.py`, `limits.py`, `attribution.py` | VaR/ES, Greeks, aggregation |
| Stress | `risk/stress.py`, `scenario_model.py`, `scenario_engine.py`, `scenarios.py`, `reverse_stress*.py` | Three scenario types + adapters |
| Application | `services/portfolio_service.py`, `risk_run_service.py`, `risk_run_worker.py` | God orchestration + run lifecycle |
| API | `app/api/*`, `main.py` | Dual-mounted routers; domain models as bodies |
| Persistence | `persistence/` | Repository ABCs; JSON columns; not on live POST path |
| Compute/native | `compute/kernel.py`, `native/` | Δ-Γ aggregation only |
| Frontend | `frontend/src` (JS, not TS) | Display + request shaping |
| AI/query | `risk/query.py` | Keyword router + five deterministic tools |
| External | QuantLib, NumPy, FastAPI, SQLAlchemy/Postgres, React/Vite | No live market vendors |

**Clean dependency direction:** `api` → FastAPI only; `risk` → `PricingEngine` + domain; QuantLib not imported outside `pricing/quantlib.py` (+ factory); native has no QuantLib; UI does not recompute VaR.

**Violations:** `domain/models.py` imports `app.market.vol_surfaces` and `app.risk.factor_types`; HTTP DTOs live in domain; live risk HTTP posts `Portfolio` rather than ids; `RiskEngine.calculate` returns `dict`; scenario repos persist `StressScenario`, not `Scenario`; QuantLib `Settings` / `IndexManager` are process-global behind a **per-instance** `RLock`.

## Architecture Strengths

- **`PricingEngine` is a real seam.** Risk code does not import QuantLib. ADR 001 matches the import graph.
- **Snapshots are copy-on-write and nested-frozen.** `MarketSnapshot.model_config = frozen`, recursive `MappingProxyType`, `model_copy` re-freezes. Stress/VaR full reval shock copies, not in-place marks.
- **Native kernel stays numerical.** C++ takes flat Exposure/Shock buffers; FULL_REVALUATION stays on `PricingEngine`. ADR 007 is respected here.
- **AI does not calculate.** `RiskQueryEngine.answer` executes `PortfolioService` tools and formats payloads (`query.py`).
- **Frontend display helpers do not reimplement VaR/pricing.** `heatmap.mjs` and `risk.mjs` document display-only mapping.
- **Persistence does not store QuantLib handles.** Repositories dump JSON-serializable domain objects (ADR 005).
- **Error envelope and `/api/v1` canonical prefix exist.** Dual-mount is explicit and deprecated, not accidental.
- **Worker claim path is honest.** Postgres `SKIP LOCKED`; Redis/RQ deferred rather than fake-microserviced.

## Overengineering / Underengineering

**Overengineering already present:** three scenario models, dual HTTP mounts, a `RiskEngine` ABC that returns a dict, `PortfolioService` owning every engine.

**Underengineering:** trade vs market, typed curves, a factor-complete instrument registry, process-level QuantLib ownership, persistence on the live calculation path.

Do not add microservices, event buses, or extra factory pyramids. The missing abstractions are the trade/market split, one scenario type, and one sensitivity path.

---

## Critical Findings

## ARCH-001 — Trades own market marks; snapshot construction last-writer-wins
Severity: CRITICAL
Area: Domain / Market Data / Pricing
Evidence:
- `backend/app/domain/models.py:107-267` — `EquityPosition.price`, `EuropeanOptionPosition.spot/volatility`, `BondPosition.yield_rate`, `SwapPosition.market_swap_rate`, FX rates on the trade
- `backend/app/market/snapshot.py:28-60` — `PositionMarketDataProvider.snapshot` copies trade marks into one snapshot; `rates[ccy] = …` overwrites
- `backend/app/pricing/quantlib.py:82-171` — market overlay mutates a Position copy (`position.model_copy(update=updates)`) before QuantLib sees it
- `backend/app/api/market.py:14-19` — `POST /market/snapshot` rebuilds marks from the posted book

Problem: There is no separate Trade (contractual economics) vs Market (shared marks) model. The book *is* the market. Building a snapshot from positions last-writer-wins on USD rates, equity spots, and FX. A USD bond at 5% and a USD swap at 4% cannot coexist as consistent market state. Pricing adapters then write snapshot values back onto the trade.

Why it matters: Stress, bump-and-revalue, and FULL_REVALUATION all operate on that collapsed snapshot. Mixed-currency or mixed-curve books will misprice silently. Adding a real market-data source later requires rewriting position types, snapshot construction, both pricers, cache keys (which hash the full trade including marks), and every API that posts a `Portfolio`.

Recommendation: Introduce `Trade` / `InstrumentTerms` (quantity, strike, maturity, pay/receive — no spots/vols/yields) and require `PricingEngine.value(position, market: MarketSnapshot)` with `market` mandatory. Snapshot construction comes from a `MarketDataProvider` keyed by risk-factor ids, never by iterating trades. Keep a one-shot demo adapter that seeds a snapshot from sample marks, not from live trade fields.

Suggested task: Split trade economics from market marks; make `MarketSnapshot` the only pricing input; delete last-writer-wins `PositionMarketDataProvider` from the production path.
Estimated effort: L
Dependencies: ARCH-004, ARCH-010, ARCH-012

## ARCH-002 — QuantLib globals are not process-owned or as-of bound
Severity: CRITICAL
Area: Pricing / C++
Evidence:
- `backend/app/pricing/quantlib.py:50-67` — `evaluation_date = date.today()`; per-instance `RLock` around `ql.Settings.instance().evaluationDate`
- `backend/app/pricing/quantlib.py:342-347` — `index.addFixing(..., True)` writes QuantLib `IndexManager` global history
- `backend/app/domain/models.py:325` — `MarketSnapshot.as_of: str = "current"` never consumed by pricing
- `backend/app/pricing/factory.py:28-30` — factory constructs one engine; tests construct additional `QuantLibPricingEngine()` instances
- `docs/adr/007-quantlib-concurrency.md` — claims the instance lock serializes QuantLib in-process

Problem: QuantLib evaluation date and index fixings are process-global. The adapter lock is **instance-scoped**, so two engines in one process can race `Settings`. Evaluation date is wall-clock today, not snapshot `as_of` (which is an unconstrained string). Swap pricing seeds a global fixing store. Native kernels correctly avoid this; Python QuantLib paths do not fully own it.

Why it matters: Concurrent FULL_REVALUATION, CachedPricingEngine + a second engine, or worker threads with more than one adapter can produce cross-request contamination. As-of / backdated risk runs are architecturally impossible until date is bound to the snapshot. Unbounded `addFixing` is a hidden global mutable map.

Recommendation: One process-level QuantLib session (module lock or dedicated pricing process). Bind `evaluation_date` to `MarketSnapshot.as_of` (real `date`). Clear or isolate index fixings per valuation. Keep native kernels QuantLib-free (already true). Prefer process isolation for parallel reval as ADR 007 already says — implement it, don’t only document it.

Suggested task: Process-wide QuantLib session; typed snapshot as-of date drives `Settings.evaluationDate`; isolate/clear IBOR fixings per call.
Estimated effort: L
Dependencies: ARCH-001 (snapshot as-of becomes real once marks leave the trade)

---

## High Findings

## ARCH-003 — domain/models.py mixes domain, results, and HTTP DTOs
Severity: HIGH
Area: Domain / API
Evidence:
- `backend/app/domain/models.py` — one module: `Position` union, `MarketSnapshot`, `Valuation`, `RiskSummary`, `StressScenario`, `VaRReport`, `HierarchyNode`, `AttributionRequest`, `RiskQueryRequest`, `WhatIfRequest`, `RiskRunCreateRequest`, `RiskRunView`
- `backend/app/api/risk.py:17-25` — routers import those types as FastAPI bodies/responses
- `backend/app/domain/models.py:1357-1388` — `RiskRunCreateRequest` documents `POST /risk/runs` inside the domain file

Problem: Domain, risk results, and transport schemas are the same Pydantic classes. There is no `Trade` vs `PositionDTO`, no versioned API models, no persistence-specific mapping beyond JSON dump.

Why it matters: Any wire change (deprecating a field, splitting hierarchy, adding a pricing result type) becomes a domain change. Persistence, OpenAPI, frontend, and quant code all churn together. This is the main reason a PostgreSQL-backed production model will rewrite more than “just repos.”

Recommendation: Keep a small frozen domain (`Trade`, `Portfolio`, `MarketSnapshot`, `Valuation`, `RiskRun` header). Move HTTP request/response types to `app/api/schemas`. Map at the router boundary.

Suggested task: Split `domain/models.py` into domain entities vs API schemas; stop importing HTTP models from `app.domain`.
Estimated effort: L
Dependencies: ARCH-010

## ARCH-004 — MarketSnapshot.bump inverts domain → market/risk dependencies
Severity: HIGH
Area: Market Data / Domain
Evidence:
- `backend/app/domain/models.py:69-87` — `_bump_vol_surface_payload` imports `app.market.vol_surfaces`
- `backend/app/domain/models.py:473-527` — `MarketSnapshot.bump` imports `app.risk.factor_types` and encodes shock units
- `backend/app/market/snapshot.py:63-67` — `shock_snapshot` imports `app.risk.scenario_engine`

Problem: The domain snapshot owns market-transformation policy and depends upward on market and risk packages. Allowed direction in `docs/architecture.md` is domain ← market ← risk. The code is the reverse for bump/apply.

Why it matters: New factor types, surface conventions, or curve bump rules require editing the giant domain file. Risk/market cannot evolve independently. Circular imports are already papered over with function-local imports.

Recommendation: `MarketSnapshot` should be a frozen data holder. Put `bump`/`apply`/`diff` on a `MarketModel` / `SnapshotTransform` in `app.market`. Domain must not import `factor_types` or vol helpers.

Suggested task: Move snapshot transforms into `app.market`; leave `MarketSnapshot` as immutable data.
Estimated effort: M
Dependencies: ARCH-001, ARCH-013

## ARCH-005 — Three scenario models with conversion adapters
Severity: HIGH
Area: Stress / Persistence
Evidence:
- `backend/app/domain/models.py:691-705` — legacy `StressScenario` (scalar + per-name dicts)
- `backend/app/risk/scenarios.py:51-63` — `MarketScenario` + `FactorChange` (historical)
- `backend/app/risk/scenario_model.py:94-122` — formal `Scenario` + `FactorShock`
- `backend/app/risk/scenario_engine.py:55-80` — `ScenarioInput` union of all three plus raw sequences
- `backend/app/persistence/repositories.py:54-65` — scenario repo persists `StressScenario`

Problem: Formal scenarios exist (ADR 004) but HTTP, persistence, and most engines still speak `StressScenario`. The rest of the stack is a conversion layer (`scenario_from_stress`, `scenario_to_stress`, `expand_scenario`).

Why it matters: New scenario types (historical replay vs hypothetical vs reverse) must be implemented twice and converted. Persistence cannot store typed factor shocks without another migration. This is overengineering *and* underengineering: three types, one actual wire format.

Recommendation: One `Scenario` (typed shocks) in domain. Adapter only at the legacy HTTP sunset. Persist `Scenario` JSON. Delete `MarketScenario` once historical generation returns `Scenario`.

Suggested task: Make `Scenario` the only stored and engine-facing type; keep `StressScenario` as a deprecated HTTP shim until sunset.
Estimated effort: L
Dependencies: ARCH-003, ARCH-019

## ARCH-006 — Instrument isinstance ladders copied across layers
Severity: HIGH
Area: Pricing / Market Data / Risk
Evidence:
- `backend/app/pricing/builtin.py:48-79` — `isinstance` chain per instrument
- `backend/app/pricing/quantlib.py:84-196` — parallel chain for overlay + dispatch; leftover `BuiltinPricingEngine().value` fallback
- `backend/app/market/snapshot.py:32-51` — same chain to fill snapshot maps
- `backend/app/risk/factors.py:40-53` — same chain for factor exposures; **omits** `CapFloorPosition` / `SwaptionPosition`

Problem: Adding an instrument means touching pricers, snapshot builder, QuantLib overlay, factor engine, sample books, and tests. There is no registry of “this product reads these market keys / emits these factors.”

Why it matters: Caps/floors/swaptions already demonstrate the failure: they price, but `RiskFactorEngine` never attributes their DV01/vega. Extension cost is linear in number of files, not one plugin.

Recommendation: Per-instrument adapter: terms schema, market-key requirements, factor emitters, builtin value, QuantLib value. Factory maps `type` discriminator → adapter. Risk/market iterate adapters, not `isinstance`.

Suggested task: Introduce an instrument adapter registry; migrate one product family as the template; make missing factor coverage a test invariant.
Estimated effort: L
Dependencies: ARCH-001, ARCH-007

## ARCH-007 — Factor taxonomy incomplete; historical VaR is four macros
Severity: HIGH
Area: Risk / Market Data
Evidence:
- `backend/app/risk/historical_data.py:7-10,46-57` — four columns: equity, vol, rate bps, FX
- `backend/app/risk/scenarios.py:80-110` — `expand_aggregate_change` broadcasts one equity return onto **every** `equity_spots` name (same for vol/FX/rates)
- `backend/app/risk/historical.py:67-139` — LINEAR/DELTA_GAMMA uses those four series; native kernel ABI is the same 4-shock layout
- `backend/app/risk/factors.py:40-53` — IR optionality absent from typed factors
- `backend/app/risk/factor_types.py:127` — `RiskFactor = Union[EquitySpot, EquityVol, RateZero, FXSpot, FXVol]` only

Problem: Named `RiskFactor` types exist (ADR 003) but historical VaR does not use them. Default methodology is a one-factor-per-asset-class proxy. The C++ kernel hard-wires that proxy.

Why it matters: A long AAPL vs short SPY book has perfectly correlated historical equity risk. Tenor-specific rates are ignored in approximate VaR. Native acceleration cannot be extended to per-name shocks without an ABI break. This is the ceiling on “RiskForge owns risk factors.”

Recommendation: Historical dataset keyed by `RiskFactor.key` (sparse panel). Approximate P&L is Σ_i exposure_i × shock_i (with gamma on spot factors). Keep a documented 4-column demo dataset as a projection of that panel, not the engine’s native input. Extend `RiskFactor` for IR vol / caplet / swaption.

Suggested task: Replace 4-column `FactorObservationSeries` with a per-factor observation panel; update kernel ABI or keep the kernel as a packed view of that panel.
Estimated effort: XL
Dependencies: ARCH-006, ARCH-016

## ARCH-008 — Split Greek/P&L pipelines; VaRAnalytics ignores market
Severity: HIGH
Area: Risk / Pricing
Evidence:
- `backend/app/pricing/builtin.py:93,154` — analytic delta/gamma/vega/dv01 on `Valuation`
- `backend/app/risk/historical.py:210-227` — portfolio VaR LINEAR/Δ-Γ sums those analytic Greeks
- `backend/app/risk/var.py:55-57` — component VaR calls `pricing.value(p)` **with no market**
- `backend/app/risk/sensitivities.py:154-160,327-344` — bump-and-revalue vega uses **absolute** vol bump; `MarketSnapshot.bump` uses **relative** vol (`models.py:314,489-493`)
- `backend/app/risk/historical.py:208-210` — comment: `market is None` preserves “position-embedded marks”

Problem: Risk has two Greek systems (analytic `Valuation` vs `SensitivityEngine` bump-revalue) with different vol units, and two pricing contexts (with snapshot vs trade-embedded). Limits key-rate DV01 uses sensitivities; VaR uses analytic sums. Component VaR can disagree with portfolio VaR because one path ignores the snapshot.

Why it matters: Users will see inconsistent delta/vega/DV01 across screens. Quant validation cannot name a single Greek definition. This is how incorrect calculations appear without a single obvious bug.

Recommendation: One sensitivity service: bump `MarketSnapshot` through `PricingEngine`, cache results, feed VaR approximation, limits, and UI. Analytic Greeks on `Valuation` may remain as diagnostics but must not drive VaR. `value(position, market)` always required.

Suggested task: Make bump-revalue the sole risk Greek source; delete no-market `pricing.value(p)` from VaR/component paths; unify vol bump units with `MarketSnapshot.bump`.
Estimated effort: L
Dependencies: ARCH-001, ARCH-012

## ARCH-009 — PortfolioService is a process-wide god object
Severity: HIGH
Area: API / Service
Evidence:
- `backend/app/services/portfolio_service.py:79-123` — constructs ~12 engines; methods cover snapshot, summary, stress, reverse, hedge, factors, VaR, ES, compare, what-if, hierarchy, attribution, query, limits, drilldown
- `backend/app/api/deps.py:38-48` — process-wide `portfolio_service = PortfolioService(...)`
- `backend/app/main.py:24` — worker captures that singleton at import

Problem: One god service plus a process singleton is the application layer. Hidden state: pricing cache, QuantLib evaluation date, historical dataset, in-memory run repo. Routers are thin, but all composition lives in one constructor.

Why it matters: Tests, workers, and HTTP share one engine/cache. You cannot run two books with different pricing configs, evaluation dates, or datasets without global env vars. Replacing `PortfolioService` later is a wide rewrite even if risk math is fine.

Recommendation: Keep `PortfolioService` as a façade if useful, but inject engines explicitly (already partially done). Request-scoped or run-scoped pricing/market context. Stop importing a module-global service in `main.py`.

Suggested task: Replace module-global `portfolio_service` with FastAPI lifespan factory; thread `PricingContext` (engine, snapshot, as-of) through run execution.
Estimated effort: M
Dependencies: ARCH-002, ARCH-010

## ARCH-010 — Live risk API POSTs the book; persistence is a side path
Severity: HIGH
Area: Persistence / API
Evidence:
- `backend/app/api/risk.py:31-37` — `POST /risk/summary` body is a full `Portfolio`
- `frontend/src/api.js:12-22` — dashboard POSTs the same book to nine endpoints
- `backend/app/persistence/repositories.py` — `PortfolioRepository` exists
- `backend/app/api/portfolio.py:14-17` — `GET /portfolio` can load SQLAlchemy seed, but risk POSTs do not use ids
- `backend/app/services/risk_run_worker.py:79-110` — runs still take an in-memory `Portfolio`, not a repo load by id

Problem: Persistence is a parallel stack (seed, risk-run headers, JSON blobs). The live risk path is stateless “POST the entire book every time.” Snapshot ids on `RiskRun` are optional and unused by most calculate paths.

Why it matters: You cannot audit which snapshot produced a VaR, share a book across users, or avoid sending 10 copies of the same positions. Adding PostgreSQL without rewriting quant math is possible **only** if calculation already takes `(portfolio_id, snapshot_id)`. Today it does not. JSON blob columns also mean no relational constraints on trades/factors.

Recommendation: Canonical API: `POST /api/v1/risk/var` with `{portfolio_id, market_snapshot_id, methodology}`. Worker loads both from repos. Keep a debug endpoint that accepts inline portfolio for tests.

Suggested task: Add id-based risk endpoints; wire `RiskRun` to persisted portfolio + snapshot; stop requiring full position lists on every calculate call.
Estimated effort: L
Dependencies: ARCH-001, ARCH-003, ARCH-009

## ARCH-011 — Hierarchy is label-slicing that re-runs full risk per node
Severity: HIGH
Area: Risk / Hierarchy
Evidence:
- `backend/app/risk/hierarchy.py:3-9,107-134,149-186` — each node builds a sub-`Portfolio` and re-runs `_metrics` (full VaR) + `_stress` + `_limits`
- `backend/app/risk/hierarchy_placement.py:13-20` — hierarchy is `desk`/`strategy`/`book` **strings** on positions, not a graph
- `backend/app/domain/models.py:286-292,96-104` — firm/desk/strategy on `Portfolio` with optional position overrides
- `backend/app/domain/models.py:908-914` — `RiskLimit.scope` is “informational”; evaluation uses whatever subset the caller passed

Problem: Firm→Trade is a grouping of labels, not a durable tree. Aggregation is “recompute everything on the subset,” including non-additive VaR (correct) but also full historical reval and stress **per trade node**. There is no first-class `HierarchyNodeId`. Multi-portfolio firm rollup is not modeled (`PORTFOLIO` level always matches the single posted book).

Why it matters: Tree size × VaR cost. A 2,000-trade book becomes thousands of independent risk runs. Limits cannot express “desk VaR cap” without the caller slicing first. You cannot hang results off a stable node id for persistence.

Recommendation: Price/shock once at trade grain; store `PositionRiskResult`; additive metrics sum up the tree; non-additive VaR runs on cached PnL vectors per node (same historical shocks). Persist a hierarchy definition separately from trades.

Suggested task: Compute position-level PnL/Greeks once; aggregate hierarchy from those vectors; give nodes stable ids.
Estimated effort: L
Dependencies: ARCH-007, ARCH-008

## ARCH-012 — PricingEngine does not fully isolate QuantLib semantics
Severity: HIGH
Area: Pricing
Evidence:
- `backend/app/pricing/quantlib.py:82-171` — snapshot → field overlay on Position, then QuantLib
- `backend/app/pricing/quantlib.py:197-199` — unknown types silently fall through to `BuiltinPricingEngine`
- `backend/app/pricing/quantlib.py:334-339` — bond PV from curve; DV01 from flat yield bump **without** the curve
- `backend/app/pricing/quantlib.py:88-91` and `backend/app/pricing/builtin.py:54` — equity/future discount rate `market.rates.get("USD", …)`
- `backend/app/pricing/quantlib.py:468-473` — IR future is algebraic, not a QuantLib instrument (acknowledged)

Problem: The adapter isolates QuantLib **types** but not QuantLib **semantics**. Market is smuggled via Position fields. Greeks are not the same object as NPV (curve PV vs yield DV01). Builtin fallback can silently change methodology if a new `Position` type is added. Equity rates are USD-only.

Why it matters: Engine switches (`RISKFORGE_PRICING_ENGINE`) will not stay equivalent as products grow. Sensitivity vs VaR already diverge (ARCH-008). Multi-currency equity is wrong by construction.

Recommendation: QuantLib adapter should build QL market objects from `MarketSnapshot` (curves, surfaces, FX) and quotes from trade terms only. Report DV01 as bump of the same curve used for NPV. Fail closed on unknown instruments. Drop hardcoded USD; key rates by currency on the trade/snapshot.

Suggested task: Stop copying snapshot fields onto Position; price from (terms, snapshot); align DV01 with the NPV curve; remove silent Builtin fallback.
Estimated effort: L
Dependencies: ARCH-001, ARCH-008, ARCH-020

---

## Medium Findings

## ARCH-013 — Curves and vol surfaces stored as untyped dict payloads
Severity: MEDIUM
Area: Market Data
Evidence:
- `backend/app/domain/models.py:335-338` — `curves: dict[str, dict]`, `vol_surfaces: dict[str, dict]`
- `backend/app/domain/models.py:52-62,69-87` — bump helpers treat payloads as untyped maps (`zeros`, `grid`, `atm_vol`)

Problem: Nested market structure is schema-on-read JSON. Typed `VolSurface` exists in `market/vol_surfaces.py` only after parse.

Why it matters: Invalid grids fail late in pricing. Persistence cannot migrate curve schema safely. Stress bump logic duplicates parser knowledge.

Recommendation: Pydantic/dataclass curve and surface types on `MarketSnapshot`; serialize at the edge.

Suggested task: Replace `dict[str, dict]` curve/surface fields with typed models.
Estimated effort: M
Dependencies: ARCH-004

## ARCH-014 — RiskEngine ABC returns an untyped dict
Severity: MEDIUM
Area: Risk
Evidence:
- `backend/app/interfaces/risk.py:7-10` — `RiskEngine.calculate(...) -> dict[str, float]`
- `backend/app/risk/historical.py:200-249` — extra `methodology`/`market` kwargs; returns a dict including `"methodology"` string

Problem: The risk interface is a leftover stub. It neither matches `HistoricalRiskEngine` nor returns `RiskSummary`. Hierarchy and limits consume `dict`.

Why it matters: New VaR methodologies get shoved into a bag of floats. Liskov substitutions are illusory (`isinstance(self.risk, HistoricalRiskEngine)` throughout `PortfolioService`).

Recommendation: `RiskEngine.measure(portfolio, market, spec) -> RiskResult`. Delete dict returns from the public contract.

Suggested task: Replace `RiskEngine.calculate` dict with a typed `RiskResult` used by hierarchy, limits, and summary.
Estimated effort: S
Dependencies: ARCH-003, ARCH-009

## ARCH-015 — Limit.scope is informational, not enforced
Severity: MEDIUM
Area: Risk
Evidence:
- `backend/app/domain/models.py:908-914` — `scope` / `label` informational; evaluation uses the passed subset
- `backend/app/risk/limits.py:174-204` — `LimitEngine.evaluate` does not filter by `item.scope`

Problem: Limits look hierarchical in the type system but are not. Scope is a display string.

Why it matters: A “desk” limit on a firm-level call still evaluates firm metrics. Operators will trust the field.

Recommendation: Evaluate limits against `HierarchyRef`. Reject or resolve scope inside the engine.

Suggested task: Enforce `RiskLimit.scope` by slicing via `portfolio_at` before metric resolution.
Estimated effort: M
Dependencies: ARCH-011

## ARCH-016 — Native ctypes ABI has no version or error channel
Severity: MEDIUM
Area: C++
Evidence:
- `backend/app/compute/kernel.py:97-116` — `restype = None`; no status code, no ABI version, no null checks
- `backend/native/src/risk_kernel_capi.cpp:9-15` — `void` C API
- `backend/native/include/risk_kernel.hpp:28-40` — Exposure/Shock structs match the 4-macro model

Problem: The numerical boundary is narrow (good) but unsafe and coupled to ARCH-007’s 4-shock layout. ctypes will happily pass bad lengths.

Why it matters: ABI evolution for per-name factors will be a silent mismatch. Hard crashes on bad pointers rather than Python errors.

Recommendation: Versioned header (`RISKFORGE_KERNEL_ABI=1`), return `int` error codes, length validation. Don’t put business policy in C++ (already avoided).

Suggested task: Add ABI version + error return to `riskforge_portfolio_scenarios`; reject length mismatches in the ctypes wrapper.
Estimated effort: S
Dependencies: ARCH-007

## ARCH-017 — Frontend is untyped JS with no generated client
Severity: MEDIUM
Area: Frontend
Evidence:
- `frontend/package.json` — JavaScript React, `"react": "latest"`, no OpenAPI client
- `frontend/src/api.js:12-22` — `loadDashboard` fans out nine POSTs of the full portfolio
- `frontend/src/App.jsx:32-40` — one blob of dashboard state, hash-based sections

Problem: No typed client, no generated schemas, dashboard does not use risk-run aggregation. Display math is disciplined (good); contract math is duplicated by hand.

Why it matters: Schema drift vs `domain/models.py` will show up as runtime `undefined`. Nine parallel full-book POSTs multiply ARCH-010.

Recommendation: Generate a TypeScript client from OpenAPI; one `POST /risk/runs` (or a batch summary) for overview; keep view-models display-only.

Suggested task: OpenAPI-generated frontend client; overview via one risk-run or batch endpoint.
Estimated effort: M
Dependencies: ARCH-010, ARCH-019

## ARCH-018 — NL query is substring routing over five tools
Severity: MEDIUM
Area: AI
Evidence:
- `backend/app/risk/query.py:11-16,134-171,333-334` — five tools; `term in question` substring routing
- `backend/app/risk/query.py:266-306` — `_format_answer` interpolates tool JSON only (does not compute VaR)

Problem: The orchestration rule is honored (strength). The router is not an architecture for a real assistant: substring `es` matches inside unrelated words; tools omit hierarchy, reverse stress, attribution.

Why it matters: A future LLM loop will still be boxed into five tools unless the contract surface grows. Substring routing will mis-fire in demos.

Recommendation: Keep deterministic execution. Replace `_mentions` with token/intent matching or the already-sketched `RiskAssistantModel`. Expand tool schemas to match `PortfolioService` without letting the model invent numbers.

Suggested task: Word-boundary intent routing; add tool contracts for hierarchy, reverse stress, and attribution (execute via existing services).
Estimated effort: M
Dependencies: None

## ARCH-019 — Dual-mount API and untyped RiskRun.request
Severity: MEDIUM
Area: API
Evidence:
- `backend/app/main.py:87-93` — every domain router mounted twice
- `backend/app/domain/models.py:1304-1305,1388` — `RiskRun.request: dict[str, Any]`
- `backend/app/api/risk.py:1` — comment still says “until M7.2 /api/v1 migration”

Problem: Versioning is dual-mount, not v2 modules. Run envelopes are untyped dicts. Comments lag the canonical prefix.

Why it matters: Sunset will be a grep, not a module deletion. Invalid `request` payloads fail late in the worker.

Recommendation: Keep `/api/v1` only in a dated sunset. Typed `RiskRunRequest` union per `run_type`.

Suggested task: Typed run-request models; schedule removal of unversioned mounts (docs already exist).
Estimated effort: M
Dependencies: ARCH-003

## ARCH-020 — Equity rates hardcoded to USD
Severity: MEDIUM
Area: Pricing
Evidence:
- `backend/app/pricing/builtin.py:54` — `market.rates.get("USD", position.risk_free_rate)`
- `backend/app/pricing/quantlib.py:91,99` — same USD default for equity futures/options

Problem: Equity discounting ignores listing currency.

Why it matters: Non-USD equity books get the USD dummy rate from the snapshot constructor (`rates = {"USD": 0.04}`).

Recommendation: Currency on equity terms; look up `rates[ccy]`.

Suggested task: Add `currency` to equity/future/option positions; price off that curve.
Estimated effort: S
Dependencies: ARCH-001, ARCH-012

---

## Low Findings

## ARCH-021 — Frontend runtime deps pinned to latest
Severity: LOW
Area: Frontend
Evidence:
- `frontend/package.json:16-19` — `react`, `react-dom`, `vite`, `@vitejs/plugin-react` all `"latest"`

Problem: Builds are not reproducible from `package.json` ranges.

Why it matters: CI and local can drift; not a domain flaw. A lockfile exists, but `"latest"` still invites accidental upgrades.

Recommendation: Pin versions; keep the lockfile as the install source of truth.

Suggested task: Replace `"latest"` with pinned semver matching the lockfile.
Estimated effort: S
Dependencies: None

## ARCH-022 — C++ kernel getenv plus duplicated serial/parallel loops
Severity: LOW
Area: C++
Evidence:
- `backend/native/include/risk_kernel.hpp:50-63,74-100,153-209` — `std::getenv` in `resolve_kernel_threads`; serial and parallel loops duplicated for struct vs flat layouts

Problem: Env lookup on the hot path; duplicated numeric kernels.

Why it matters: Noise for maintenance; not policy in C++ (good).

Recommendation: Resolve thread count once at library load; one template/implementation for the inner product.

Suggested task: Cache thread count; deduplicate flat vs struct inner loops.
Estimated effort: S
Dependencies: None

## ARCH-023 — Agent docs still point at missing TASKS.md
Severity: LOW
Area: Docs
Evidence:
- `ROADMAP.md:3` — `TASKS.md` absent
- Agent charters still refer to `TASKS.md`
- `ROADMAP.md:7-22` — all workstreams marked COMPLETE while residual gaps remain in the same file (IR vol cube, reverse-stress optimiser, dual-mount)

Problem: Agent operating docs and the backlog disagree. Completeness flags hide residual architecture debt.

Why it matters: Future agents will treat the platform as done and pile features on ARCH-001.

Recommendation: Single backlog (`ROADMAP.md` or FINDINGS). Don’t mark workstreams complete when critical architecture items remain.

Suggested task: Point agent docs at `ROADMAP.md` only; add an explicit architecture-debt section without flipping completion checkboxes as part of this review.
Estimated effort: S
Dependencies: None

## ARCH-024 — CORS allowlist is localhost-only
Severity: LOW
Area: API
Evidence:
- `backend/app/main.py:73-78` — CORS origins `localhost:5173` only

Problem: Fine for the demo; Compose frontend on port 80/`5173:80` may or may not match depending on how the UI calls the API.

Why it matters: Small deploy footgun, not a domain issue.

Recommendation: Configure origins from env.

Suggested task: `RISKFORGE_CORS_ORIGINS` env list.
Estimated effort: S
Dependencies: None

---

## Informational Findings

## ARCH-025 — No auth, tenancy, or entitlement model
Severity: INFO
Area: API
Evidence:
- No auth middleware in `backend/app/main.py`; routers have no user/tenant id
- Persistence models (`persistence/models.py`) have no owner/entitlement columns

Problem: Expected for an MVP demo. Not a defect relative to stated non-goals. See also `reviews/security-review.md`.

Why it matters: Any multi-user deployment needs a tenancy model **before** sharing Postgres, not after JSON blobs accumulate.

Recommendation: When persistence becomes the live path (ARCH-010), add `owner_id` on portfolio/snapshot/run in the same change. Do not bolt on later.

Suggested task: Record tenancy as a gated workstream; do not implement in the demo.
Estimated effort: XL
Dependencies: ARCH-010

## ARCH-026 — Sync FastAPI is appropriate for CPU-bound risk
Severity: INFO
Area: API
Evidence:
- `backend/app/api/risk.py` — sync `def` handlers
- `backend/app/services/risk_run_worker.py:1-10` — `ThreadPoolExecutor`, not a distributed queue

Problem: None. CPU-bound QuantLib under a process lock is a poor fit for async FastAPI. The worker split is coherent.

Why it matters: Fashionable async/microservices would make ARCH-002 worse.

Recommendation: Keep sync handlers; scale FULL_REVALUATION with processes (already ADR 007).

Suggested task: None required.
Estimated effort: S
Dependencies: None

## ARCH-027 — ROADMAP completeness vs residual architecture debt
Severity: INFO
Area: Docs
Evidence:
- `README.md` / `docs/architecture.md` describe the intended layering accurately at the QuantLib boundary
- `ROADMAP.md:39-56` architecture map omits that bump lives in domain and that live HTTP is POST-the-book
- Caps/floors listed as priced in README but “deferred” in a ROADMAP bullet and “scoped Black-76” in known limitations — three stories

Problem: Docs are directionally honest in `docs/known_limitations.md` and over-complete in ROADMAP status tables.

Why it matters: Reviewers will trust the status table over the limitations catalog.

Recommendation: Treat `docs/known_limitations.md` as the source of truth for claims; keep ROADMAP status conservative.

Suggested task: Align `docs/architecture.md` with the dependency violations listed in this review (docs-only, separate from code).
Estimated effort: S
Dependencies: ARCH-023

---

## Top 10 Recommended Architecture Actions

1. **Separate trade economics from market marks** (ARCH-001) — everything else is a workaround.
2. **Move bump/apply out of `domain/models.py`; type curves/surfaces** (ARCH-004, ARCH-013).
3. **Process-level QuantLib session; snapshot as-of drives evaluation date** (ARCH-002).
4. **Split domain entities from API DTOs** (ARCH-003).
5. **One `Scenario` type in engines and persistence** (ARCH-005).
6. **Instrument adapter registry** so new products do not clone `isinstance` ladders (ARCH-006).
7. **Per-name historical factor panel; include IR optionality in `RiskFactorEngine`** (ARCH-007).
8. **Single Greek/P&L path: always price on a snapshot; unify bump units** (ARCH-008, ARCH-012).
9. **Id-based risk APIs + runs that load portfolio and snapshot from repos** (ARCH-010, ARCH-009).
10. **Hierarchy from cached trade-level results, not N full VaR re-runs** (ARCH-011).

## Suggested Sequencing

Follow the repo’s own merge order (`AGENTS.md`):

1. **Contracts:** ARCH-001, ARCH-003, ARCH-004, ARCH-002 lock/as-of, ARCH-005 `Scenario` as the stored type. No new instruments until this lands.
2. **Reference implementation:** snapshot-mandatory pricing; factor registry; per-factor history with the 4-column CSV as a projection.
3. **Quant validation:** golden tests that a mixed USD book does not last-writer-win; bump-revalue vs analytic Greeks; as-of date frozen across a run.
4. **API:** id-based calculate + typed run requests; then drop legacy dual-mount on the existing sunset path.
5. **UI:** generated client; overview via one run (ARCH-017).
6. **Native:** ABI version; kernel consumes packed per-factor shocks only after the Python path exists (ARCH-016, ARCH-007).
7. **AI:** expand tool contracts against the new ids; keep “no invented numbers.”
8. **Do not do:** microservices, event buses, extra factory pyramids, or moving VaR into C++.

## Related

- `reviews/security-review.md` — complementary security review of the same checkout
- `docs/architecture.md` — intended (not fully observed) layering
- `docs/known_limitations.md` — honest product-claim catalog
- `docs/adr/` — accepted decisions evidenced in code
