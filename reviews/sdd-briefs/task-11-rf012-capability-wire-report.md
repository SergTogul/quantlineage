# Task 11 Report — RF-012 wire capability registry into remaining dispatch

## Task
RF-012 wire capability registry into remaining production dispatch (R0.5.6)

## Owner
Quant Pricing Engineer

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-012)

## Summary
R0.5.1 already had a static ten-family table (`app.pricing.instrument_capabilities`) that nothing called. R0.5.2 already fail-closed QuantLib unknown Position types without Builtin. This slice **wires `get_capability`** into the remaining dispatch so unknown families cannot silently change methodology:

- QuantLib and Builtin `value()` look up `terms.type` after `terms_from_position`.
- Snapshot overlay (`_snapshot_marks_from_terms` in both adapters) looks up the family first and **raises** instead of `return {}`.
- `trade_cache_key` looks up the family before the schema-id map.
- `RiskFactorEngine.calculate_typed` looks up `position.type` before pricing/aggregation.

Unknown families raise `KeyError`/`TypeError` matching `unknown instrument family`. QuantLib still does not call Builtin. Existing goldens and cache-key hashes are unchanged. **Disposition: IN PROGRESS** — adding a new instrument is still parallel ladder edits, not one registration plus tests.

TDD: seven new cases failed first; after the gates, they passed. No plugin framework. No new product types. No C++/exotics.

## Files changed
- `backend/app/pricing/instrument_capabilities.py` — docstring; lookup API unchanged
- `backend/app/pricing/quantlib.py` — `get_capability` in `value()` and overlay; overlay fallthrough raises
- `backend/app/pricing/builtin.py` — same
- `backend/app/pricing/cache.py` — `get_capability` in `trade_cache_key`
- `backend/app/risk/factors.py` — `get_capability` in `calculate_typed`
- `backend/tests/test_instrument_capabilities.py` — builtin/overlay/factor/cache wires
- `backend/tests/test_quantlib_unknown_instrument.py` — QuantLib wire + unregistered-terms no-Builtin
- `reviews/FINDINGS.md` — RF-012 **IN PROGRESS** with residual list
- `reviews/REMEDIATION_MILESTONE.md` — R0.5.6
- `reviews/r0.5.6-rf012-capability-wire-report.md`
- `reviews/sdd-briefs/task-11-rf012-capability-wire-report.md` — this handoff

## Public/interface changes
- None for HTTP/DTO/snapshot schema.
- Fail-closed contract: unregistered family strings cannot be priced, overlaid as empty marks, hashed as a cache family, or silently dropped by typed factor extraction.
- `get_capability` signature and errors unchanged.

## Numerical conventions
- Units: unchanged (gate only; no formula edits)
- Sign convention: unchanged
- Day count/calendar if relevant: unchanged
- Tolerances/reference: QuantLib goldens as documented in `test_quantlib_golden.py`; cache deny-list hashes in `test_pricing_cache.py` must match pre-slice pins

## Tests added/updated
- `test_builtin_value_consults_get_capability` — Builtin `value()` calls `get_capability`
- `test_builtin_snapshot_overlay_unknown_family_fails_closed` — overlay does not return `{}`
- `test_factor_extraction_unknown_family_fails_closed` — stub pricer still cannot skip unknown types
- `test_trade_cache_key_consults_get_capability`
- `test_quantlib_value_consults_get_capability`
- `test_quantlib_snapshot_overlay_unknown_family_fails_closed`
- `test_quantlib_unregistered_terms_fail_closed_without_builtin` — monkeypatched unregistered terms raise family error; Builtin `value` is boomed

## Commands executed
TDD red (new cases, before production change):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_instrument_capabilities.py \
  tests/test_quantlib_unknown_instrument.py
```

Brief (required):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_instrument_capabilities.py \
  tests/test_quantlib_unknown_instrument.py \
  tests/test_quantlib_pricing.py
```

Affected extra:

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_instrument_capabilities.py \
  tests/test_quantlib_unknown_instrument.py \
  tests/test_quantlib_pricing.py \
  tests/test_quantlib_golden.py \
  tests/test_factor_types.py \
  tests/test_pricing_cache.py \
  tests/test_instrument_terms.py

PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_builtin_pricing.py tests/test_ir_options_pricing.py

.venv/bin/ruff check \
  app/pricing/instrument_capabilities.py \
  app/pricing/quantlib.py \
  app/pricing/builtin.py \
  app/pricing/cache.py \
  app/risk/factors.py \
  tests/test_instrument_capabilities.py \
  tests/test_quantlib_unknown_instrument.py
```

## Results
- Backend brief suite: **53 passed** (2.61s). No skips.
- Affected extra: **179 passed** (3.96s); builtin + IR options **60 passed** (1.95s).
- Ruff: all checks passed.
- Frontend: n/a
- QuantLib: goldens/pricing included; bands not loosened
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

TDD red: **7 failed** as expected (`get_capability` unused; overlay `{}`; factor skip; unregistered terms `unsupported instrument`).

## MET vs PARTIAL vs UNMET (this gate)

Acceptance: “adding a new instrument requires one coherent adapter registration plus tests, not edits to parallel ladders.”

| Cell | Score |
|---|---|
| Unknown family fail-closed in pricing | **MET** |
| Unknown family fail-closed in snapshot overlay | **MET** |
| Unknown family fail-closed in factor extraction | **MET** |
| QuantLib must not call Builtin | **MET** |
| Goldens unchanged | **MET** |
| One registration plus tests (CLOSE bar) | **UNMET** |

## Why IN PROGRESS (not CLOSE)
Would not defend CLOSE. Residual parallel ladders:

1. QuantLib `value()` `isinstance` chain (pricing bodies still per type)
2. Builtin `value()` `isinstance` chain
3. Duplicated `_snapshot_marks_from_terms` (two copies)
4. `terms_from_position` (`instrument_terms.py`)
5. `RiskFactorEngine.calculate_typed` — cap/floor/swaption still omitted after a successful registry lookup
6. `required_factors_for_position` (`historical.py`) — not wired this slice
7. `_TRADE_CACHE_SCHEMAS` parallel family→schema-id map
8. `position_label` (`portfolio_service.py`) omits cap/floor/swaption

## Known limitations / risks
- Registry is still a frozen lookup table of name strings, not adapter objects.
- Cap/floor and swaption price and are registered; typed factor extraction still skips them (ARCH-006).
- Market Data / Portfolio Risk still own snapshot construction and historical panel mapping; those ladders were not rewritten.
- RF-010 / RF-011 / RF-013 / RF-014 / RF-016 untouched.

## Follow-up / next owner
- Owner: independent reviewer (Task 11 review)
- Requested action: KEEP OPEN; do not CLOSE RF-012
- Blocking?: no
