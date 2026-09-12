# Known Limitations

This catalog is part of the portfolio-presentation package. It is intentionally explicit so RiskForge is not over-claimed in interviews, demos, or future docs.

## Market Data

- No live market-data vendor integration is implemented. There is no Bloomberg or Refinitiv plant.
- Production demo historical factors are a packaged per-factor synthetic replay (`data/demo_multi_factor_history.csv`, id `demo-multi-factor-history` / `v1`), not observed licensed market data. That packaged synthetic history remains the default (`QUANTLINEAGE_DATA_MODE=synthetic` or unset).
- An **optional** public freeze exists (`scripts/build_public_demo_data.py`, Yahoo public EOD + FRED). It is not the Compose/API default and is not a vendor feed. See [`docs/public_data_demo.md`](public_data_demo.md).
- The four-column CSV (`data/demo_historical_factors.csv`) remains an explicit `four_macro_demo` fixture for goldens and `factor_panel=None`. It is not the production demo default.
- `PositionMarketDataProvider` always raises `SampleMarksRemovedError`; it is not a last-writer constructor of market state from positions. Positions are contractual economics only. Live marks live on an explicit `MarketSnapshot` (canned demos bind `_DEMO_*` tables).
- Snapshot shock application (`shock_snapshot`) still delegates to risk-layer helpers (`app.risk.scenario_engine`); a domain-layer rewrite of that dependency is not claimed.
- Market snapshots are immutable and deterministic, but production entitlement, quality checks, market close processes, and vendor symbology are out of scope.

## Risk Factors

- Typed historical factors today are `EquitySpot`, `EquityVol`, `RateZero`, `FXSpot`, and `FXVol`. That is not a fully general taxonomy across all product families.
- IR vol, dividend yield, and funding/projection rates are not first-class typed historical factors. They appear as snapshot maps (`ir_vols`, `dividend_yields`, `projection_rates`). Caps/floors/swaptions can expose vega on valuation without an `IRVol` historical factor.

## Curves

- Curve support includes deterministic offline helpers and scoped bootstrap inputs.
- The current bootstrap is not a production multi-curve framework.
- The Stage 10.5 rates-macro showcase attaches deterministic USD OIS-style discount zeros and a SOFR-style projection map (2Y/5Y/10Y nodes) for demo KR-DV01. That is not production dual-curve calibration, futures convexity, or live quote bootstrapping.
- Futures convexity, rich calendar/stub logic, collateral/discounting policy, basis curves, and live quote calibration are not claimed.

## Volatility Surfaces

- Equity and FX option pricing can consume attached volatility-surface grids where supported.
- Surface grids are not calibrated SABR, local-vol, stochastic-vol, or vendor-smile models.
- Volatility shocks update deterministic grids and scalar fallbacks, but that is not a production vol-surface governance framework.

## Instrument Pricing

- Pricing is intentionally behind `PricingEngine`; risk, API, UI, and AI layers must not own pricing formulas.
- QuantLib coverage is not presented as exhaustive across all listed product families and conventions.
- The builtin adapter is a deterministic reference/fallback, not a production replacement for a mature pricing library.
- Caps/floors and swaptions are scoped vanilla flat Black-76-style implementations. No Bermudan exercise, callable structures, settlement variation, IR vol cube, or full date-schedule modeling is claimed.
- Interest-rate futures use scoped algebraic behavior, not a full exchange-style futures/FRA framework.

## VaR And ES

- `LINEAR` and `DELTA_GAMMA` are approximation modes; they do not capture all higher-order or model-specific repricing behavior.
- `FULL_REVALUATION` depends on available pricing-adapter coverage and market snapshot fidelity.
- Exact VaR/ES goldens cover reviewed deterministic cases in `backend/tests/test_var_es_golden.py`; they do not make the approximate `LINEAR` and `DELTA_GAMMA` methodologies exact.
- Component VaR is a covariance/Euler allocation to parametric VaR, not an additive allocation of historical quantile VaR.
- Demo VaR/ES values use packaged deterministic inputs and should not be marketed as live production analytics.

## Stress And Reverse Stress

- Crisis-library scenarios are approximations unless explicitly sourced from observation replay.
- Stress factor contributions include an interaction residual when isolated shocks do not add perfectly.
- Multi-factor reverse stress searches the adverse orthant only, assumes monotonicity, and uses ray search plus coordinate descent. It is not a certified global optimizer.
- Reverse stress operates on coarse factor families by default, not a full per-name/per-tenor optimization over all market state.

## Performance

- The accepted performance claim is limited to the native scenario-kernel SLA in [`performance.md`](performance.md) and [`benchmarks/RESULTS.md`](../benchmarks/RESULTS.md).
- No HTTP risk-run latency, multi-tenant capacity, or FULL_REVALUATION performance SLA is claimed. Stage 10.3 [`benchmarks/FULL_REVAL_RESULTS.md`](../benchmarks/FULL_REVAL_RESULTS.md) records host wall/RSS/parity for QuantLib full revaluation; those cells are observations, not floors.
- In-process QuantLib is serialized by `_QL_PROCESS_LOCK`; valuation cache keys include parseable snapshot as-of (ISO `YYYY-MM-DD` or `date`; labels such as `current` / `t0` stay equivalent and use the engine evaluation date). Parallel full revaluation is process-partitioned (R0.3.5 / R0.6.5 option B): Compose `worker` (`python -m app.worker`) is a separate OS process from the API; HEAVY `FULL_REVALUATION` summary/var refuse the request thread when `RISKFORGE_EXTERNAL_WORKER=1` (`details.use=/risk/runs`); native kernels stay QuantLib-free; there is no in-process QuantLib thread pool and no unused `ProcessPoolExecutor` job platform. R0.6.1 `pnl_checksum` is identity evidence, not a FULL_REVALUATION SLA. Stage 10.3 checksums are the same class of identity/parity evidence.

## Persistence And Workers

- Postgres-backed risk-run claim safety uses `SELECT ... FOR UPDATE SKIP LOCKED` when configured.
- Compose ships one worker for the demo. Additional Postgres-backed replicas should not double-claim the same row, but broader operations concerns such as fairness, retries across hosts, observability, and queue management are not a full production job platform.
- Redis/RQ is explicitly deferred and should not be described as implemented.
- RiskRun provenance (`GET /api/v1/risk/runs/{id}/provenance` and the nested GET-run object) copies persisted run identity fields plus an optional `RISKFORGE_RELEASE_SHA` / git describe. It does not expose secrets and does not invent a SHA when none is available.

## API And Compatibility

- `/api/v1` is canonical.
- Legacy unversioned routes remain dual-mounted with deprecation headers until the published sunset gate.
- OpenAPI examples are illustrative payloads, not guaranteed live values.

## Local Demo Security

- Default Compose binds published Postgres (`5432`), API (`8000`), and frontend (`5173`) ports to loopback (`127.0.0.1`). The local/demo profile is still unauthenticated and is not internet-ready; it must not be treated as a production security or IAM deployment (RF-014).
- A shared / non-loopback profile (`RISKFORGE_SHARED_DEPLOYMENT=1` or non-loopback `RISKFORGE_BIND`) fails closed without `RISKFORGE_API_TOKEN` or `RISKFORGE_API_TOKENS` and requires Bearer auth on API routes. Object ACLs, TLS terminator (`docker-compose.shared.yml` Caddy on 443; SPA `VITE_API_BASE_URL=same-origin`), and shared-profile secret placeholders are **MET**. That is not OIDC, SSO, in-app TLS, or a cloud secret manager. See `BUILD_NOTES.md` (R0.11.5 / R0.11.8).
- Seed/demo catalog books are owned by principal `demo` (readable; updates by other principals return 403). Local Compose may keep the demo `POSTGRES_PASSWORD=riskforge`.

## Frontend

- The React terminal is a demo-quality risk workflow UI.
- It displays API responses and helper formatting only; it does not duplicate pricing, VaR, stress, or optimization formulas.
- Screenshots in the demo docs represent a deterministic local app capture, not hosted production availability.
- TypeScript rewrite is out of scope. Centralized OpenAPI scenario POST pins and request-boundary %/bp assertions are **MET** (RF-018 **CLOSED**).

## AI Assistant

- The implemented AI slice is deterministic risk-query orchestration with explicit tool contracts.
- No full external LLM runtime, prompt stack, or model tool-calling loop is claimed as complete.
- The assistant must refuse unsupported advisory requests and ask clarification for ambiguous prompts rather than inventing risk values.
- JSON-schema tool allowlist, arg validation, and ambiguity/injection/advisory evals are **MET** (RF-019 CLOSED). No live LLM provider. The assistant still must not invent risk numbers.

## Native kernel (RF-017)

- ABI fail-closed, contiguous array P&L, and serial-below-threshold paths are **MET**. Default Historical VaR remains python/NumPy **by design** (do not move VaR or QuantLib into C++). RF-017 is CLOSED as MET for ABI; that residual is not an open ABI gap.

## CI And Verification

- Repository docs record specific local and GitHub Actions verification evidence where available.
- This limitations catalog is not a live CI badge. Before claiming a branch is merge-ready, rerun the relevant local checks and verify required CI is green.
- Suite counts in `ROADMAP.md` Current gate are the recorded Phase A baseline (**not a live** re-run).
- Labeled-runner SLA-K1 and SLA-K2 are **post-R0** (still **not MET**): no labeled runner; SLA-K1/K2 not CI-enforced; do not run `check_m6_sla.py` on `ubuntu-latest`.
- QA-024 demo-artifact range check against QuantLib is **MET** (relative 25% on market value / named stress P&Ls; `var_99` in `[0.25×, 4×]` of `data/demo_risk_artifact.json`; nightly `tests/test_qa024_ql_demo_range.py`). Not byte-equality.
