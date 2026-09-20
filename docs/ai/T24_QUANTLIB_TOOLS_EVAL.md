# T24 — Evaluate new direct QuantLib tools

Status: **Decided** (2026-09-20); **`get_position_greeks` implemented** on follow-up  
Scope: Original task was design only. Position Greeks later shipped via `TOOL_CONTRACTS` (no raw QuantLib exposure).

## Question

Do missing Risk Query / assistant use cases justify new allowlisted tools such as:

- `price_instrument`
- `calculate_greeks`
- curve inspection / dump tools

Any future tool must still enter `TOOL_CONTRACTS`, use typed schemas, call existing pricing abstractions via `PortfolioService`, include provenance, and pass the same security gate (ADR 006).

## Evidence reviewed

| Area | Finding |
|---|---|
| Assistant allowlist | Originally 16 tools; now includes `get_position_greeks` |
| Option Greeks UX | Valuation already carries delta/gamma/vega/dv01/fx_delta from PricingEngine |
| Pricing stack | No new QuantLib path — `PortfolioService.position_greeks` uses `value_portfolio` |
| Existing rates tools | `get_key_rate_dv01` covers KR-DV01 without a generic curve dump |
| ADR 006 | Model may only select tools; numbers must come from deterministic engines |

## Decisions

### 1. `calculate_greeks` / `get_position_greeks` — **Approved and implemented**

Shipped as `get_position_greeks`:

- `PortfolioService.position_greeks` ranks positions by a Valuation Greek
- Typed args: `greek` ∈ {delta, gamma, vega, dv01, fx_delta}, `top_n`
- Deterministic router + `answer_with_model` short-circuit “Biggest options delta?” to this tool
- Policy v1.0.2 directs the model to select `get_position_greeks` (never `get_contributors`)

Theta/rho remain unsupported (not on `Valuation`).

### 2. `price_instrument` — **Defer**

Not justified for the assistant milestone (catalog + history + portfolio summary cover current needs).

### 3. Curve tools — **Reject for now**

KR-DV01 / rates showcase suffice; raw curve dumps enlarge context and exfiltration risk.

## Summary table

| Candidate | Decision | Implement now? |
|---|---|---|
| `get_position_greeks` | Approved | **Yes** (shipped) |
| `price_instrument` | Not justified | **No** |
| Curve dump / raw QL curve tools | Reject | **No** |

## Explicit non-actions

- No raw QuantLib objects in API responses, logs, or model context.
- No free-form `calculate_greeks(symbol, model_params…)` bypassing `PortfolioService`.

## Follow-up status

- **Implemented:** `get_position_greeks` + routing + policy v1.0.2
- `BoundedRiskAssistant` HTTP wiring when `AI_MAX_TOOL_ROUNDS > 1` (separate commit on branch)
- Still deferred: `price_instrument`, curve dump tools
