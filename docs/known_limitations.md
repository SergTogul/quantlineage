# Known Limitations

This catalog is part of the portfolio-presentation package. It is intentionally explicit so RiskForge is not over-claimed in interviews, demos, or future docs.

## Market Data

- No live market-data vendor integration is implemented.
- Demo historical factors are a packaged synthetic replay (`data/demo_historical_factors.csv`), not observed licensed market data.
- Market snapshots are immutable and deterministic, but production entitlement, quality checks, market close processes, and vendor symbology are out of scope.

## Curves

- Curve support includes deterministic offline helpers and scoped bootstrap inputs.
- The current bootstrap is not a production multi-curve framework.
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
- Component VaR is a covariance/Euler allocation to parametric VaR, not an additive allocation of historical quantile VaR.
- Demo VaR/ES values use packaged deterministic inputs and should not be marketed as live production analytics.

## Stress And Reverse Stress

- Crisis-library scenarios are approximations unless explicitly sourced from observation replay.
- Stress factor contributions include an interaction residual when isolated shocks do not add perfectly.
- Multi-factor reverse stress searches the adverse orthant only, assumes monotonicity, and uses ray search plus coordinate descent. It is not a certified global optimizer.
- Reverse stress operates on coarse factor families by default, not a full per-name/per-tenor optimization over all market state.

## Performance

- The accepted performance claim is limited to the native scenario-kernel SLA in [`performance.md`](performance.md) and [`benchmarks/RESULTS.md`](../benchmarks/RESULTS.md).
- No HTTP risk-run latency, multi-tenant capacity, or FULL_REVALUATION performance SLA is claimed.
- QuantLib concurrency is protected by an adapter lock inside a process; parallel full revaluation should use process isolation, not unsafe shared `ql.Settings` mutation.

## Persistence And Workers

- Postgres-backed risk-run claim safety uses `SELECT ... FOR UPDATE SKIP LOCKED` when configured.
- Compose ships one worker for the demo. Additional Postgres-backed replicas should not double-claim the same row, but broader operations concerns such as fairness, retries across hosts, observability, and queue management are not a full production job platform.
- Redis/RQ is explicitly deferred and should not be described as implemented.

## API And Compatibility

- `/api/v1` is canonical.
- Legacy unversioned routes remain dual-mounted with deprecation headers until the published sunset gate.
- OpenAPI examples are illustrative payloads, not guaranteed live values.

## Frontend

- The React terminal is a demo-quality risk workflow UI.
- It displays API responses and helper formatting only; it does not duplicate pricing, VaR, stress, or optimization formulas.
- Screenshots in the demo docs represent a deterministic local app capture, not hosted production availability.

## AI Assistant

- The implemented AI slice is deterministic risk-query orchestration with explicit tool contracts.
- No full external LLM runtime, prompt stack, or model tool-calling loop is claimed as complete.
- The assistant must refuse unsupported advisory requests and ask clarification for ambiguous prompts rather than inventing risk values.

## CI And Verification

- Repository docs record specific local and GitHub Actions verification evidence where available.
- This limitations catalog is not a live CI badge. Before claiming a branch is merge-ready, rerun the relevant local checks and verify required CI is green.
