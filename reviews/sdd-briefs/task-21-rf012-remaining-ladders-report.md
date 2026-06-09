# Task 21 Report — RF-012 remaining capability ladders (R0.5.7)

## Task
RF-012 remaining capability ladders (R0.5.7)

## Owner
Quant Pricing Engineer (`docs/agents/02_QUANT_PRICING_ENGINEER.md`) coordinating with Portfolio Risk for `required_factors_for_position` / `calculate_typed`.

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-012)

## Summary
R0.5.6 made `get_capability` a fail-closed *gate*. This slice consumes the
registry for the remaining extraction/cache ladders:

1. **`calculate_typed`** extracts every `PRODUCTION_FAMILIES` family. After
   `named_risk_factors` succeeds, cap/floor/swaption are not skipped. IR
   options contribute `dv01` onto typed `RateZero` (tenor `round(maturity_years)Y`;
   swaption uses `option_maturity_years`). Vega is **not** mixed into `RateZero`
   (no `IRVol` class; units would be wrong). Builtin cap `dv01` matches the
   typed exposure.
2. **`required_factors_for_position`** is no longer an isinstance ladder. It
   returns `named_risk_factors(position)`. Cap/floor and swaption map to
   `RateZero`. Unknown families raise `KeyError`/`TypeError` matching
   `unknown instrument family`.
3. **`_TRADE_CACHE_SCHEMAS`** was removed from `cache.py`. Schema ids live on
   `InstrumentCapability.trade_cache_schema`. Deny-list hashes unchanged.
4. **`position_label`** left as a UX ladder (collapsing it is cosmetic).

Funding `RateZero` on equity/FX families stays snapshot-map-only (spot/vol
identity) so SAMPLE panel VaR numbers do not change. No plugin framework. No
rewrite of Builtin/QuantLib `value()`.

TDD: nine new cases failed first; after implementation they passed.

## Files changed
- `backend/app/pricing/instrument_capabilities.py`
- `backend/app/pricing/cache.py`
- `backend/app/risk/factors.py`
- `backend/app/risk/historical.py`
- `backend/tests/test_instrument_capabilities.py`
- `reviews/FINDINGS.md`
- `reviews/REMEDIATION_MILESTONE.md`
- `reviews/r0.5.7-rf012-remaining-ladders-report.md`
- `reviews/sdd-briefs/task-21-rf012-remaining-ladders-report.md` — this handoff

Not edited: `quantlib.py` / `builtin.py` `value()` and overlay, `models.py`,
`instrument_terms.py`, `portfolio_service.position_label`, C++, frontend,
demo snapshot ids.

## Public/interface changes
- `InstrumentCapability.trade_cache_schema`
- `named_risk_factors(position) -> tuple[RiskFactor, ...]`
- Unknown-family error on the panel path aligns with `get_capability`
- No HTTP/DTO/snapshot schema change

## Numerical conventions
- Units: `RateZero` exposure = `Valuation.dv01` (per 1bp). IR vega per 1 vol
  point stays on `Valuation` only.
- Sign convention: engine `dv01` as priced.
- Tenor: `round(maturity_years)Y`; swaption `option_maturity_years`.
- Tolerances/reference: existing QuantLib goldens; cache hashes in
  `test_pricing_cache.py` unchanged.

## Tests added/updated
- `test_trade_cache_schema_lives_on_capability_registry`
- `test_calculate_typed_includes_cap_floor_rate_zero` — exposure is `dv01`, not `dv01+vega`
- `test_calculate_typed_includes_swaption_rate_zero` — tenor `1Y` from option expiry
- `test_calculate_typed_extracts_every_production_family`
- `test_required_factors_for_position_maps_cap_floor_and_swaption`
- `test_required_factors_unknown_family_fails_closed`
- `test_required_factors_driven_from_registry_not_isinstance_ladder`
- `test_builtin_ir_option_calculate_typed_matches_valuation_dv01`

## Commands executed
TDD red:

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_instrument_capabilities.py \
  -k "trade_cache_schema or calculate_typed_includes or calculate_typed_extracts or required_factors or builtin_ir_option"
```

Result: **9 failed**, 8 passed, 10 deselected (expected).

Required + affected:

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_instrument_capabilities.py \
  tests/test_quantlib_unknown_instrument.py \
  tests/test_pricing_cache.py \
  tests/test_ir_options_pricing.py \
  tests/test_factor_types.py \
  tests/test_factor_panel_historical.py \
  tests/test_factor_panel.py \
  tests/test_risk_factories.py \
  tests/test_panel_contributions.py \
  tests/test_quantlib_pricing.py \
  tests/test_quantlib_golden.py \
  tests/test_builtin_pricing.py \
  tests/test_instrument_terms.py \
  tests/test_var_es_golden.py

.venv/bin/ruff check \
  app/pricing/instrument_capabilities.py \
  app/pricing/cache.py \
  app/risk/factors.py \
  app/risk/historical.py \
  tests/test_instrument_capabilities.py

PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line \
  tests/test_demo_scripts.py tests/test_risk.py tests/test_historical_data.py
```

## Results
- Backend required + affected: **300 passed** (4.16s). No skips.
- Extra demo/risk: **24 passed** (2.32s).
- Isolated capabilities after green: **27 passed** (included in the 300).
- Ruff: all checks passed.
- Frontend: not run.
- QuantLib: goldens included; not weakened.
- C++: not run.
- All tests pass (applicable/affected suites): yes
- Unexplained failures or skips: none
- CI is green: not started (commit this slice; no push)

## MET vs PARTIAL vs UNMET

| Acceptance | Score |
|---|---|
| Cap/floor and swaption in `calculate_typed` and `required_factors_for_position` | **MET** |
| Unknown family fail-closed | **MET** |
| Cache schema on registry; hashes unchanged | **MET** |
| Goldens / SAMPLE VaR / demo snapshot ids unchanged | **MET** |
| Adding a family is one registration plus tests | **UNMET** |

## Why IN PROGRESS (not CLOSE)
Brief constraint: do not CLOSE if Builtin/QuantLib `value()` isinstance ladders
or overlay still require a parallel edit per family. They do.

Remaining ladders:
1. Builtin `value()` isinstance chain
2. QuantLib `value()` isinstance chain
3. Duplicated `_snapshot_marks_from_terms` overlay (both adapters)
4. `position_label` UX ladder
5. Domain `Position` / `InstrumentTerms` unions (new product types)

## Known limitations / risks
- No typed `IRVol`; IR option vega is not a typed factor.
- Equity/FX funding `RateZero` not extracted (preserves SAMPLE VaR).
- `named_risk_factors` duck-types position fields (`symbol` / `pair` / `currency` / tenor).
- Not a plugin registry.

## Follow-up / next owner
- Owner: independent reviewer, then Lead Architect for pricer/overlay consolidation
- Requested action: KEEP OPEN; do not CLOSE RF-012
- Blocking?: no
