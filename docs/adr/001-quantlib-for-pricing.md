# ADR 001: QuantLib for pricing behind PricingEngine

- Status: Accepted (codified from existing implementation)
- Date: 2026-09-02
- Owners: Lead Architect; Quant Pricing Engineer

## Context

QuantLineage is a portfolio-risk platform. Instrument valuation must come from a mature pricing library, not from ad-hoc formulas scattered across risk, API, or UI layers. The codebase already separates pricing behind an abstract seam and ships two adapters.

Evidence in repo:

- `backend/app/interfaces/pricing.py` defines `PricingEngine` (`value`, `shocked_value`, `value_portfolio`).
- `backend/app/pricing/quantlib.py` implements `QuantLibPricingEngine` (default production path).
- `backend/app/pricing/builtin.py` implements `BuiltinPricingEngine` as a full-coverage reference / test fallback.
- `backend/app/pricing/factory.py` selects the engine via `QUANTLINEAGE_PRICING_ENGINE` (default `"quantlib"`; tests force `"builtin"` in `conftest.py`).
- QuantLib coverage is partial: unsupported instruments fall back to Builtin inside the QuantLib adapter (documented in `ROADMAP.md` ).
- Risk modules depend on `PricingEngine`, not QuantLib types (e.g. sensitivities docstring / imports).

## Decision

1. All instrument valuation and analytic Greeks go through `PricingEngine`.
2. **QuantLib** is the intended production pricing backend (`QuantLibPricingEngine`).
3. **Builtin** remains a first-class reference implementation for development, tests, golden/property cross-checks, and temporary fallback where QuantLib adapters are incomplete.
4. QuantLineage does **not** invent a general replacement pricing library; portfolio risk owns aggregation, scenarios, VaR/ES, stress, attribution, and workflow around the pricing seam.

## Alternatives considered

| Alternative | Why rejected (given current code) |
|-------------|-----------------------------------|
| Embed QuantLib types directly in risk/API layers | Would couple portfolio risk to library globals and break the documented boundary (“pricing library prices; QuantLineage manages portfolio risk”). |
| Builtin-only forever | Insufficient for institutional-style derivatives coverage; factory already defaults to QuantLib. |
| Call QuantLib from the frontend or LLM | Violates non-goals; UI must not duplicate pricing formulas; AI must not calculate. |
| Replace QuantLib with another library now | No evidence of a second production adapter; would be a new architectural change, not a recorded decision. |

## Consequences

- Parallel agents must not bypass `PricingEngine` or move QuantLib imports into risk/UI/AI modules without Lead Architect approval.
- Incomplete QuantLib instrument coverage (EquityFuture / FXForward / FXOption fallback; missing IR future / cap-floor / swaption) is tracked under , not as a change to this ADR.
- Golden and property tests that compare Builtin vs QuantLib remain the validation strategy for adapter work.
- Process-global QuantLib evaluation date / concurrency is recorded in
 `docs/adr/007-quantlib-concurrency.md` (adapter `RLock`, prefer process
 isolation for parallel QL reval, native kernels separate from QL globals).
 This ADR only records the pricing-backend choice.
