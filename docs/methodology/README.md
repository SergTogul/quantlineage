# Risk Methodology

This page is the interviewer-facing methodology overview for QuantLineage. It describes implemented behavior and important assumptions at a level suitable for review; source code and tests remain the authority for exact numerical details.

## VaR And Expected Shortfall

QuantLineage supports historical-style and parametric VaR/Expected Shortfall workflows through deterministic risk engines.

### Historical Methodology Modes

| Mode | What it does | Native kernel eligibility | Main limitation |
|---|---|---|---|
| `LINEAR` | Uses first-order Greek approximation across historical factor observations. | Eligible for optional native scenario aggregation. | Ignores convexity and full repricing effects. |
| `DELTA_GAMMA` | Uses delta-gamma approximation plus vega, DV01, and FX delta terms. This is the default demo mode. | Eligible for optional native scenario aggregation. | Still an approximation; higher-order and model-specific effects remain residual. |
| `FULL_REVALUATION` | Builds shocked historical market snapshots and reprices positions through `PricingEngine`. | Not eligible. | Slower; depends on adapter coverage and market snapshot fidelity. |

Historical observations can come from the packaged demo CSV, a custom CSV, or the deterministic synthetic dataset. The packaged demo history is a synthetic replay for reproducibility, not a vendor feed or empirical market-data entitlement.

Expected Shortfall is calculated from the tail of the same P&L distribution used for the selected methodology. Contribution reports reconcile to portfolio ES within documented tolerances in tests; FULL_REVALUATION factor contributions include an interaction residual where isolated shocks do not add perfectly.

### Component, Marginal, And Incremental Risk

- Component VaR uses covariance/Euler allocation on the selected methodology P&L series and reconciles to parametric VaR.
- Marginal VaR reports the local sensitivity of portfolio VaR to a position weight at the current holdings.
- Incremental VaR compares before/after portfolios under the same methodology and reports risk deltas without mutating the input portfolio.

## Stress Testing

Stress scenarios shock `MarketSnapshot` through typed factor changes. Scenarios may be default hypothetical shocks, crisis-library approximations, custom user inputs, or formal `Scenario` definitions adapted to existing stress DTOs.

Stress P&L is base portfolio value versus shocked portfolio value through `PricingEngine`. Scenario contribution decompositions support hierarchy and factor views; factor decompositions use isolated full revaluation and an interaction residual when combined shocks are not additive.

Historical crisis presets are labeled approximations unless they are derived from explicit observation replay. They should not be presented as exact historical reconstructions.

## Reverse Stress

Single-factor reverse stress solves for one adverse factor magnitude needed to reach a target loss percentage.

Multi-factor reverse stress is documented separately in [`multi_factor_reverse_stress.md`](multi_factor_reverse_stress.md). In short, it searches a constrained adverse orthant with a deterministic ray search plus coordinate descent under an L2 box-normalized objective. It is not a certified global optimizer and does not prove monotonicity for every book.

## Pricing Engine Scope

Pricing is delegated to `PricingEngine` adapters:

- `QuantLibPricingEngine` is the intended production adapter for covered instrument paths.
- `BuiltinPricingEngine` is a deterministic reference and fallback, useful for tests, demos, and environments without QuantLib.

Current pricing scope includes equities, equity futures, European equity options, bonds, vanilla swaps, FX forwards/options, interest-rate futures, and scoped vanilla caps/floors and European swaptions. The IR optionality slice uses flat Black-76-style assumptions and does not claim production vol-cube, Bermudan/callable, or settlement-variation coverage.

Curve and volatility surface support is deterministic and local. Curve bootstrap helpers support scoped offline inputs; volatility surfaces are consumed where attached. There is no live vendor integration, SABR/local-vol calibration, or production multi-curve calibration claim.

## AI Orchestration Guardrails

QuantLineage’s natural-language risk path is deterministic today. The query engine chooses from explicit tool contracts backed by `PortfolioService` methods, executes deterministic code, and formats answers from returned payloads.

Guardrails:

- Numerical risk/pricing values must originate from deterministic tools or APIs.
- Unsupported advisory prompts refuse rather than fabricate recommendations.
- Ambiguous prompts ask for clarification instead of returning invented risk data.
- A future external LLM loop must preserve tool-call provenance and may only select tools, bind inputs, and narrate grounded results.

## Related Docs

- Architecture overview: [`../architecture.md`](../architecture.md)
- Known limitations: [`../known_limitations.md`](../known_limitations.md)
- Multi-factor reverse stress: [`multi_factor_reverse_stress.md`](multi_factor_reverse_stress.md)
- Performance report: [`../performance.md`](../performance.md)
- ADR index: [`../adr/README.md`](../adr/README.md)
