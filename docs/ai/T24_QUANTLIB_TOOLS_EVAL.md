# T24 — Evaluate new direct QuantLib tools

Status: **Decided** (2026-09-20)  
Scope: Design only. This document does **not** authorize implementing or exposing raw QuantLib APIs.

## Question

Do missing Risk Query / assistant use cases justify new allowlisted tools such as:

- `price_instrument`
- `calculate_greeks`
- curve inspection / dump tools

Any future tool must still enter `TOOL_CONTRACTS`, use typed schemas, call existing pricing abstractions via `PortfolioService`, include provenance, and pass the same security gate (ADR 006).

## Evidence reviewed

| Area | Finding |
|---|---|
| Assistant allowlist | 16 `RiskToolName` entries in `TOOL_CONTRACTS`; no Greeks or single-instrument price tool |
| Option Greeks UX | `_is_greeks_question` + policy rule 7 refuse delta/gamma/vega/theta; prior misroute to `get_contributors` was fixed |
| Pricing stack | `PricingEngine` / QuantLib + builtin adapters already write `Valuation.delta/gamma/vega/dv01/fx_delta` |
| Capabilities registry | `european_option` / `fx_option` declare delta/gamma/vega; rates families declare dv01 |
| Existing rates tools | `get_key_rate_dv01` (+ rates-showcase HTTP) already covers KR-DV01 without a generic curve dump |
| Book-level risk | `get_portfolio_summary`, `get_var_es`, `get_contributors`, stress/limits cover portfolio risk, not Greek ranking |
| ADR 006 | Model may only select tools; numbers must come from deterministic engines |

## Decisions

### 1. `calculate_greeks` — **Approve as a future candidate; do not implement in this milestone**

**Justification:** The gap is real and user-visible. Greeks already exist on deterministic `Valuation` objects, but the assistant has no allowlisted way to surface them. Refusing “biggest options delta?” is correct today; it is not a product end-state.

**Required shape if implemented later (follow-up task, not T24):**

1. Add a `PortfolioService` method that ranks or returns position-level Greeks from existing valuations (no new QuantLib call path invented in the assistant layer).
2. Add `RiskToolName.CALCULATE_GREEKS` (or a clearer name such as `get_position_greeks`) to `TOOL_CONTRACTS` with:
   - typed args (e.g. optional `greek` enum: delta|gamma|vega|theta|rho, optional `top_n`);
   - `numeric_source` pointing at the service payload;
   - provenance fields (`portfolio_id`, `market_snapshot_id`, `as_of`, methodology/identity as available).
3. Extend deterministic formatters and narration grounding allowlists.
4. Keep MCP/HTTP on the same contract; never hand the model a QuantLib handle or curve object.
5. Pass the same security/eval gate as other tools (allowlist, schema, no secret leakage, no advisory).

**Not approved:** free-form `calculate_greeks(symbol, model_params…)` that bypasses `PortfolioService` or accepts arbitrary QuantLib settings.

### 2. `price_instrument` — **Defer; not justified for the assistant milestone**

**Rationale:** Instrument discovery (`search_instruments`) and history (`get_market_history`) already cover catalog/price-series questions. Book market value comes from `get_portfolio_summary`. A one-off mark-to-market tool would mostly duplicate pricing already performed inside portfolio valuation, and invites ad-hoc parameter sets that are hard to provenance.

Revisit only if a concrete product flow needs single-instrument NPV with a frozen snapshot identity that existing tools cannot return.

### 3. Curve tools — **Reject for now**

**Rationale:** Key-rate DV01 and rates showcase already expose the rates sensitivities users need for Risk Query. A generic “dump curve / zeros / surface” tool would:

- enlarge prompt/context with low-value dense numeric blobs;
- raise exfiltration and hallucination surface area;
- overlap snapshot/lineage endpoints better served by provenance + existing market APIs.

Do not add assistant-facing curve dump tools unless a later investigation use case requires a **narrow**, schema-bound curve metadata tool (identity + as-of + hash), not raw pillar arrays in model context.

## Summary table

| Candidate | Decision | Implement now? |
|---|---|---|
| `calculate_greeks` / position Greeks | Future `TOOL_CONTRACTS` candidate via `PortfolioService` | **No** (design only) |
| `price_instrument` | Not justified for current assistant scope | **No** |
| Curve dump / raw QL curve tools | Reject | **No** |

## Explicit non-actions

- No new tool code, schemas, or MCP exposures in this task.
- No raw QuantLib objects in API responses, logs, or model context.
- No change to the current Greeks refusal until a grounded tool ships.

## Follow-up (out of T24 / optional)

1. Spec + implement `get_position_greeks` (preferred name) behind `TOOL_CONTRACTS`.
2. Optionally wire `BoundedRiskAssistant` into `answer_with_model` when `AI_MAX_TOOL_ROUNDS > 1` (library already exists from T21–T22).
