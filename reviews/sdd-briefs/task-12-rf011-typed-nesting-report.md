# Task 12 Report — RF-011 typed curve/surface nesting (R0.4.1-B)

## Task
RF-011 typed curve/surface nesting on canonical market views (R0.4.1-B)

## Owner
Market Data & Curves Engineer

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-011)

## Summary
R0.4.1-A already pinned `snapshot.equity` / `.rates_market` / `.vol` / `.fx` as frozen views over **flat dict storage**. This slice types the remaining nesting on those views:

- `VolMarket.surfaces` is `Mapping[str, VolSurface]` via existing `vol_surface_from_dict`.
- `RateMarket.curves` exposes named `YieldCurve` (`from_zero_dict` when all key tenors are present; equivalent node reconstruction for sparse/bootstrapped curves).
- Scalar `discount` / `projection` / `spreads` / `key_rates` stay the frozen snapshot maps.
- Invalid *present* surface/curve payloads fail closed (`ValueError`/`KeyError`/`TypeError`), not `{}` skip.
- Empty `vol_surfaces` / `curves` / `fx_spots` remain valid empty mappings.
- `MarketSnapshot.fx_spots` and `FxMarket` reject non-6-letter ISO pair keys via `_require_fx_pair`.
- `MarketSnapshot.rates` default remains `{"USD": 0.04}`. No nested-Pydantic storage rewrite. Demo snapshot ids / position-id sets unchanged.

**Disposition: IN PROGRESS** — dual domain `StressScenario`/`Scenario` collapse is out of scope.

TDD: new typed-view / fail-closed cases failed first (raw dict surfaces, no `RateMarket.curves`, invalid FX keys accepted); after reconstruction + validators they passed.

## Files changed
- `backend/app/market/markets.py` — `typed_vol_surfaces` / `typed_yield_curves` / `yield_curve_from_snapshot_payload`; `VolMarket.surfaces: Mapping[str, VolSurface]`; `RateMarket.curves`; `FxMarket` pair-key check
- `backend/app/domain/models.py` — view wiring; `fx_spots` field validator
- `backend/tests/test_market_snapshot.py` — typed views + fail-closed cases
- `backend/tests/test_vol_surfaces.py` — `atm_vol()` on typed surface
- `backend/tests/test_finite_scalars.py` — invalid FX spot key; empty `fx_spots`
- `reviews/FINDINGS.md` — RF-011 **IN PROGRESS** with R0.4.1-B residual
- `reviews/REMEDIATION_MILESTONE.md` — R0.4.1-B
- `reviews/r0.4-architecture-brief.md` — R0.4.1-B row
- `reviews/r0.4.1-b-typed-curve-surface-report.md`
- `reviews/sdd-briefs/task-12-rf011-typed-nesting-report.md` — this handoff

## Public/interface changes
- Typed inspection API: `snap.vol.surfaces[name]` is a `VolSurface`; `snap.rates_market.curves[name]` is a `YieldCurve`.
- Invalid FX spot keys fail `MarketSnapshot` construction (`ValidationError`).
- Flat storage/API shape unchanged (`curves` / `vol_surfaces` remain dict payloads).

## Numerical conventions
- Units: unchanged (reconstruction only; no pricing formula edits)
- Sign convention: unchanged
- Day count/calendar if relevant: Actual/365-style year fractions (existing)
- Tolerances/reference: existing bump/apply/identity/goldens; QuantLib goldens not loosened

## Tests added/updated
- Typed `VolSurface` on `snap.vol.surfaces`; empty `vol_surfaces` stays `{}`
- Fail-closed invalid/missing-`asset_class` surface payloads
- Typed `YieldCurve` on `snap.rates_market.curves` (standard USD + bootstrapped)
- Empty `curves` stays `{}`; missing/empty zeros fail closed
- Invalid FX spot keys fail closed; empty `fx_spots` valid
- R0.4.1-A grouped-view test updated off raw surface dict identity

## Commands executed
TDD red (new/updated cases, before production change): 12 failed as expected (surfaces still dicts; no `RateMarket.curves`; invalid FX keys accepted).

Brief (required):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_market_snapshot.py \
  tests/test_finite_scalars.py \
  tests/test_curve_pricing.py
```

Covering market/pricing:

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_market_snapshot.py \
  tests/test_finite_scalars.py \
  tests/test_curve_pricing.py \
  tests/test_curves.py \
  tests/test_vol_surfaces.py \
  tests/test_surface_vol_pricing.py \
  tests/test_builtin_pricing.py

PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_quantlib_pricing.py \
  tests/test_quantlib_golden.py
```

## Results
- Backend brief suite: **68 passed** (4.08s). No skips.
- Covering market/pricing: **141 passed** (5.29s). No skips.
- QuantLib pricing + goldens: **92 passed** (3.02s). No skips.
- Frontend: n/a
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push)

## MET vs PARTIAL vs UNMET (this gate)

| Cell | Score |
|---|---|
| `VolMarket.surfaces` is `Mapping[str, VolSurface]` | **MET** |
| `RateMarket` exposes named `YieldCurve` | **MET** |
| Invalid present surface/curve payloads fail closed | **MET** |
| Empty `vol_surfaces` / `curves` / `fx_spots` remain valid | **MET** |
| Invalid FX pair keys fail closed (`_require_fx_pair`) | **MET** |
| Flat dict storage / `rates` default `{"USD": 0.04}` | **MET** |
| Dual `StressScenario`/`Scenario` collapse | **OUT OF SCOPE** |
| CLOSE RF-011 | **UNMET** (required KEEP OPEN) |

## Why IN PROGRESS (not CLOSE)
Would not defend CLOSE. Residual:

1. Dual domain `StressScenario` / `Scenario` models (and deprecated StressScenario POST routes)
2. Pricing still reads flat `curves` / `vol_surfaces` dicts (`curve_from_payload` remains lenient)
3. FINDINGS acceptance still wants one canonical Scenario across historical/stress/custom/reverse/persistence/API

## Known limitations / risks
- Views reconstruct on each property access (no cache); storage stays frozen MappingProxy dicts.
- `snap.vol.surfaces` is no longer identity-equal to `snap.vol_surfaces`.
- Callers that treated `vol.surfaces[name]` as a dict must use `VolSurface`.
- RF-010 / RF-012 / RF-013 / RF-014 / RF-016 untouched.

## Follow-up / next owner
- Owner: independent reviewer (Task 12 review), then later RF-011 dual-model slice
- Requested action: KEEP OPEN; do not CLOSE RF-011
- Blocking?: no
