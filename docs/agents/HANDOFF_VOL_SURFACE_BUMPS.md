# Agent Handoff - Vol Surface Bumps

## Task
 surface-aware EquityVol / FXVol bumps rewrite attached `vol_surfaces` grids.

## Owner
Market Data & Curves Engineer.

## Summary
Implemented `MarketSnapshot.bump` / `apply` semantics so typed `EquityVol` and `FXVol` shocks update matching attached `vol_surfaces` payload grids as well as scalar ATM marks. Generic vol factors preserve existing relative scalar bump units; explicit expiry bucket bumps scale that expiry's nodes; `moneyness="SKEW"` and `expiry="TERM"` delegate to the existing RiskForge `VolSurface` skew / term-structure shock model.

## Files changed
- `backend/app/domain/models.py`
- `backend/app/market/vol_surfaces.py`
- `backend/app/pricing/surface_vol.py`
- `backend/tests/test_market_snapshot.py`
- `backend/tests/test_surface_vol_pricing.py`
- `ROADMAP.md`
- `docs/agents/HANDOFF_VOL_SURFACE_BUMPS.md`

## Public/interface changes
- No API/DTO endpoint changes.
- Added market-data helper `vol_surface_from_dict` and surface relative-shift helpers for snapshot-owned transformations.
- Pricing engines still consume a point sigma via `surface_vol.option_vol_from_snapshot`; full QuantLib surface/smile engine remains open.

## Numerical conventions
- Units: typed `EquityVol` / `FXVol` generic bumps remain relative vol-level changes (`0.25` = +25%).
- Surface-grid generic bumps: every grid node is scaled by `1 + amount`, then floored at `MIN_VOL`.
- Expiry bucket bumps: nodes in the requested expiry bucket are scaled by `1 + amount`; other expiries are unchanged.
- Skew shocks: `moneyness="SKEW"` uses existing `VolSurface.skew_shock(amount)`, with `dvol = amount * (moneyness - 1.0)`.
- Term shocks: `expiry="TERM"` uses existing `VolSurface.term_structure_shock(amount)`, with `dvol = amount * expiry_years`.
- Scalar vol maps are refreshed from bumped surface `atm_vol` when a matching surface exists; without a surface, previous scalar-only behavior remains.
- Tolerances/reference: pytest `approx` against deterministic grid transforms and Builtin pricing parity between scalar-only bumped snapshots and flat attached-grid bumped snapshots.

## Tests added/updated
- `test_bump_vol_rewrites_attached_surface_grids_and_keeps_copies_frozen`: direct `bump` grid rewrite for equity/FX surfaces plus deep-freeze on bumped copy.
- `test_apply_vol_shock_updates_attached_surface_grids`: typed `apply` path rewrites attached grids.
- `test_surface_vol_bucket_skew_and_term_shocks_use_surface_model`: expiry bucket, skew, and term surface semantics.
- `test_builtin_flat_surfaces_match_scalar_after_typed_vol_apply`: representative equity and FX flat attached-grid pricing stays aligned with scalar-only typed vol bumps.

## Commands executed
```bash
cd backend
PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest tests/test_market_snapshot.py tests/test_surface_vol_pricing.py -q
PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest tests/test_market_snapshot.py tests/test_vol_surfaces.py tests/test_surface_vol_pricing.py tests/test_scenarios.py tests/test_scenario_model.py tests/test_scenario_engine.py tests/test_sensitivities.py -q
PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest tests/test_pricing_cache.py tests/test_quantlib_pricing.py -q
PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest tests/test_market_snapshot.py tests/test_vol_surfaces.py tests/test_surface_vol_pricing.py tests/test_scenarios.py tests/test_scenario_model.py tests/test_scenario_engine.py tests/test_sensitivities.py tests/test_pricing_cache.py tests/test_quantlib_pricing.py -q
.venv/bin/ruff check app tests
.venv/bin/mypy app
PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_risk_run_api.py::test_create_returns_202_queued tests/test_risk_run_api.py -q
PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q
```

## Results
- Red test proof: focused market/surface tests initially failed as expected with four failures showing scalar vols changed while `vol_surfaces` grids stayed unchanged, and flat attached-surface pricing diverged from scalar-only bumped pricing.
- Focused market/surface after implementation: `23 passed in 1.09s`.
- Affected market/scenario/sensitivity suite: `88 passed in 1.34s`.
- Affected pricing/cache suite: `25 passed in 0.94s`.
- Final combined affected market/scenario/sensitivity/pricing suite after compatibility fallback: `113 passed in 2.43s`.
- Backend static analysis: `ruff check app tests` passed; `mypy app` passed with no issues in 82 source files.
- Full backend QuantLib suite: final run `639 passed, 1 warning in 96.80s`; warning is existing Starlette/httpx deprecation from `fastapi.testclient`.
- One earlier full-suite run had a non-reproducing async timing failure in `test_create_returns_202_queued` where a queued risk run completed before assertion; targeted rerun of `tests/test_risk_run_api.py` passed (`10 passed, 1 warning`), and final full suite passed.
- QuantLib: available locally; full backend suite ran with `RISKFORGE_PRICING_ENGINE=quantlib`.
- Frontend: not affected, not run.
- C++: not affected, not run.
- Build: not affected, not run.
- All tests pass (all applicable/affected suites required by the task): yes locally.
- Unexplained failures or skips: none. The one async full-suite failure was investigated and did not reproduce.
- CI is green (all required checks): not started in this subagent lane; requires parent/Lead push and CI verification if required before integration.

## Known limitations / risks
- remains open: QuantLib still receives a looked-up point sigma and builds `BlackConstantVol`; this change does not implement a full QL surface/smile engine.
- Surface dimension encoding uses existing typed factor fields (`expiry`, `moneyness`) with controlled values for `TERM` and `SKEW`; public API examples still default to `GENERIC` / `ATM`. Unknown future dimensions preserve prior behavior by falling back to generic relative grid scaling.
- The unrelated async risk-run timing behavior should be watched by Backend/API if it recurs in CI, but it is outside this Market Data lane.

## Follow-up / next owner
- Owner: Quant Pricing Engineer for the full-surface follow-up.
- Requested action: replace point-vol `BlackConstantVol` consumption with a full QuantLib surface/smile engine when that follow-up is explicitly started.
- Blocking?: no for the surface-bump cleanup.
