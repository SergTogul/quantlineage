# Task 24 Report — RF-012 family-keyed dispatch + shared overlay (R0.5.8)

## Task
RF-012 family-keyed dispatch + shared overlay (R0.5.8)

## Owner
Quant Pricing Engineer (`docs/agents/02_QUANT_PRICING_ENGINEER.md`)

## Status
**CLOSE** (RF-012 CLOSED; named residual: discriminated Position/Terms unions in `domain/`)

## Summary
Builtin and QuantLib `value()` dispatch by frozen `terms.type` → handler maps after `get_capability`. Existing `_bond` / `_option` / … methods remain; the isinstance ladder is gone. Snapshot marks live in one module (`app.pricing.snapshot_overlay`); both engines’ working views call the same `snapshot_marks_from_terms`. Unknown families fail closed. `position_label` fail-closes via `get_capability` and is family-keyed; labels for existing families (including cap/floor/swaption → `position.id`) stay identical.

Adding a production family is now: domain terms + one registry row + overlay handler + Builtin handler + QuantLib handler + tests. Not a second overlay copy. Not a second `isinstance` ladder in `factors.py` / `cache.py` / `historical.py`. QuantLib does not call Builtin. Not a plugin framework. Pricing goldens and cache hashes unchanged. Demo snapshot ids unchanged.

TDD: eight new cases failed first (missing overlay module; `value()` Terms isinstance; unknown label returned `id`). After the wiring landed, they passed.

## Files changed
- `backend/app/pricing/snapshot_overlay.py` — shared family-keyed overlay + `pricing_view`
- `backend/app/pricing/builtin.py` — frozen `_VALUE_HANDLERS`; overlay imported
- `backend/app/pricing/quantlib.py` — frozen `_VALUE_HANDLERS`; overlay imported; no Builtin call
- `backend/app/pricing/instrument_capabilities.py` — docstring
- `backend/app/services/portfolio_service.py` — family-keyed `position_label`
- `backend/tests/test_instrument_capabilities.py` — overlay / `value()` / label pins
- `backend/tests/test_quantlib_unknown_instrument.py` — overlay import from shared module
- `reviews/FINDINGS.md` — RF-012 **CLOSED**
- `reviews/REMEDIATION_MILESTONE.md` — R0.5.8
- `reviews/r0.5.8-rf012-family-dispatch-report.md`
- `reviews/sdd-briefs/task-24-rf012-family-dispatch-report.md` — this handoff

Not edited: `models.py` / `instrument_terms.py` unions, C++, frontend, demo snapshot ids. No golden weakening.

## Public/interface changes
- `app.pricing.snapshot_overlay.snapshot_marks_from_terms` is the overlay API (Builtin/QuantLib re-export it as `_snapshot_marks_from_terms`).
- `position_label` unknown family now raises `KeyError`/`TypeError` matching `unknown instrument family` (was fall-through to `position.id`).
- No DTO, API, or snapshot schema change.

## Numerical conventions
- Units: unchanged (dispatch only; no formula edits). Overlay mark keys/values pinned against scalar snapshot goldens.
- Sign convention: unchanged.
- Day count/calendar if relevant: unchanged.
- Tolerances/reference: existing QuantLib goldens; cache deny-list hashes in `test_pricing_cache.py` unchanged.

## Tests added/updated
- `test_snapshot_overlay_is_one_shared_module` — one module; frozen handlers cover `PRODUCTION_FAMILIES`; no engine imports; no Terms isinstance
- `test_snapshot_overlay_unknown_family_fails_closed`
- `test_snapshot_overlay_identity_for_production_families` — ten-family mark dicts
- `test_builtin_value_dispatch_is_family_keyed_not_isinstance`
- `test_quantlib_value_dispatch_is_family_keyed_not_isinstance`
- `test_position_label_dispatch_is_family_keyed_not_isinstance`
- `test_position_label_unknown_family_fails_closed`
- `test_position_label_identity_for_production_families`

## Commands executed
TDD red:

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_instrument_capabilities.py \
  -k "snapshot_overlay or family_keyed or position_label" \
  tests/test_quantlib_unknown_instrument.py::test_quantlib_snapshot_overlay_unknown_family_fails_closed
```

Required + overlay/label/goldens:

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_instrument_capabilities.py \
  tests/test_quantlib_unknown_instrument.py \
  tests/test_builtin_pricing.py \
  tests/test_quantlib_pricing.py \
  tests/test_ir_options_pricing.py \
  tests/test_pricing_cache.py \
  tests/test_quantlib_golden.py \
  tests/test_risk.py \
  tests/test_limit_drilldown.py

.venv/bin/ruff check \
  app/pricing/snapshot_overlay.py \
  app/pricing/builtin.py \
  app/pricing/quantlib.py \
  app/pricing/instrument_capabilities.py \
  app/services/portfolio_service.py \
  tests/test_instrument_capabilities.py \
  tests/test_quantlib_unknown_instrument.py
```

## Results
- Backend brief + goldens + contributor/drilldown labels: **249 passed** (4.41s). 1 pre-existing Starlette `TestClient` deprecation warning. No skips.
- Ruff: all checks passed.
- Frontend: not run (not in scope).
- QuantLib: goldens/pricing included above; not weakened.
- C++: not run (not in scope).
- Build: not run (not in scope).
- All tests pass (all applicable/affected suites required by the task): yes
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

TDD red result: **8 failed** as expected (no overlay module; `value()` Terms isinstance; unknown label did not raise).

## MET vs PARTIAL vs UNMET (this gate)

| Acceptance | Score |
|---|---|
| One overlay module; unknown families fail closed; numerical identity | **MET** |
| `value()` family-keyed frozen maps; not Terms isinstance | **MET** |
| `position_label` family-keyed via `get_capability`; labels identical | **MET** |
| Adding a family is one coherent adapter path plus tests | **MET** |
| Discriminated Position/Terms unions in `domain/` | **named residual** |

## Why CLOSE (not KEEP OPEN)
`value()` is family-keyed. Overlay is one module. A new family is registry + overlay handler + two engine handlers + tests, not parallel isinstance ladders. Would defend CLOSE.

## Known limitations / risks
- Discriminated Position/Terms unions remain in `domain/` (named residual).
- Per-family pricing *implementations* still exist as named methods (allowed).
- Unknown `position_label` now raises instead of returning `id`.
- Not a plugin/adapter object model.
- Independent review still required before the controller treats CLOSE as final.

## Follow-up / next owner
- Owner: independent reviewer (Task 24 review), then Lead Architect / controller
- Requested action: CLOSE RF-012; named residual as written
- Blocking?: no

## Review fix — unbound `value()` handlers (Important)

Task 24 review: `_VALUE_HANDLERS` stored class-captured unbound methods (`QuantLibPricingEngine._bond` at definition time). `value()` called `handler(self, working, market)`, so instance overrides such as `engine._bond = spy` never ran. Production numerical identity was unchanged; process-state spies (`observed`) stayed empty.

Fix (no RF-012 scope reopen): keep the frozen family map, store method **names**, resolve on the instance via `getattr(self, handler_name)(working, market)`. Same pattern in Builtin and QuantLib. Dispatch remains family-keyed (no Terms isinstance). Overlay stays one module. RF-012 status left as the implementer left it (CLOSE in this report; FINDINGS not re-stamped).

### Commands executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_quantlib_process_state.py \
  tests/test_quantlib_process_parallelism.py \
  tests/test_instrument_capabilities.py \
  tests/test_quantlib_unknown_instrument.py \
  tests/test_builtin_pricing.py tests/test_quantlib_pricing.py
```

### Results

- **145 passed** in 9.40s. No skips. No unexplained failures.
- Spies now fire: `test_snapshot_as_of_drives_quantlib_evaluation_date`, `test_unparseable_as_of_keeps_engine_evaluation_date`, `test_typed_date_as_of_drives_quantlib_evaluation_date`, `test_thread_pool_value_calls_remain_serialized_by_process_lock` assert non-empty `observed` and passed.
- RF-012 status: unchanged from implementer CLOSE above. FINDINGS not re-stamped.
