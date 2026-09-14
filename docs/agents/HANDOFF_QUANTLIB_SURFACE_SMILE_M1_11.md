# Agent Handoff - QuantLib Surface / Smile M1.11

## Task
QuantLib full surface / smile engine for equity and FX options.

## Owner
Quant Pricing Engineer.

## Summary
Replaced the QuantLib equity and FX option attached-surface path so matching `MarketSnapshot.vol_surfaces` grids are converted into QuantLib `BlackVarianceSurface` handles inside `app/pricing/quantlib.py`. Scalar-only market snapshots and trades without matching attached grids still use the existing `BlackConstantVol` fallback.

## Files changed
- `backend/app/pricing/quantlib.py`
- `backend/tests/test_quantlib_pricing.py`
- `ROADMAP.md`
- `docs/agents/HANDOFF_QUANTLIB_SURFACE_SMILE_M1_11.md`

## Public/interface changes
- No API, DTO, domain, or market-data schema changes.
- QuantLib objects remain contained inside `backend/app/pricing/quantlib.py`.

## Numerical conventions
- Units: vols are absolute decimals in surface grids (`0.20` = 20%); scalar vol fallback retains existing trade / `MarketSnapshot.equity_vols` / `MarketSnapshot.fx_vols` units.
- Surface coordinates: existing QuantLineage expiry years and moneyness (`K/S`) are converted to QL dates and strikes (`spot * moneyness`) using the adapter's established `Actual365Fixed` / calendar-day maturity convention.
- Sign convention: valuation, cash delta/gamma, FX delta, and 1-vol-point vega conventions are unchanged.
- Tolerances/reference: flat attached surfaces must match scalar `BlackConstantVol` valuation within `rel=1e-12, abs=1e-9`; smile/skew and term tests assert monotonic premium changes from higher interpolated vol. Existing full-suite option golden tolerances remain unchanged.

## Tests added/updated
- `test_quantlib_equity_option_uses_surface_term_structure_not_point_sigma`: proves an attached equity grid uses a QL surface path by forbidding the old point-vol helper and `BlackConstantVol`.
- `test_quantlib_fx_option_uses_surface_term_structure_not_black_constant_vol`: same guard for FX options.
- `test_quantlib_flat_surfaces_preserve_scalar_option_compatibility`: proves scalar-compatible flat equity/FX grids preserve previous values.
- `test_quantlib_surface_term_tilt_changes_longer_expiry_more`: proves term-structure grid node changes affect QuantLib valuation by expiry.

## Commands executed
```bash
cd backend
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_quantlib_pricing.py -q -k 'surface_term_structure_not_point_sigma or surface_term_structure_not_black_constant_vol or flat_surfaces_preserve_scalar_option_compatibility or surface_term_tilt_changes_longer_expiry_more'
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_quantlib_pricing.py -q -k 'surface_term_structure_not_point_sigma or surface_term_structure_not_black_constant_vol or flat_surfaces_preserve_scalar_option_compatibility or surface_term_tilt_changes_longer_expiry_more'
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_quantlib_pricing.py -q -k 'surface_term_structure_not_point_sigma or surface_term_structure_not_black_constant_vol or flat_surfaces_preserve_scalar_option_compatibility or surface_term_tilt_changes_longer_expiry_more'
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_quantlib_pricing.py tests/test_surface_vol_pricing.py -q
.venv/bin/ruff check app/pricing/quantlib.py tests/test_quantlib_pricing.py && .venv/bin/mypy app/pricing/quantlib.py
.venv/bin/ruff check app/pricing/quantlib.py tests/test_quantlib_pricing.py && .venv/bin/mypy app/pricing/quantlib.py
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q
.venv/bin/ruff check app tests && .venv/bin/mypy app
```

## Results
- Red test proof: first focused run failed as expected (`2 failed, 2 passed, 13 deselected`) because equity and FX options still called `option_vol_from_snapshot` before pricing.
- Intermediate run after implementation: focused suite initially failed because the test helper expected the removed `option_vol_from_snapshot` symbol; helper was adjusted with `raising=False`.
- Focused M1.11 tests: `4 passed, 13 deselected in 1.18s`.
- Affected QuantLib + surface pricing tests: `23 passed in 1.26s`.
- Touched-file static analysis: first run failed only for import ordering in `tests/test_quantlib_pricing.py`; rerun passed (`All checks passed!`; `Success: no issues found in 1 source file`).
- Full backend QuantLib suite: `653 passed, 1 warning in 36.98s`; warning is the existing Starlette/httpx deprecation from `fastapi.testclient`.
- Full backend static analysis: `ruff check app tests` passed; `mypy app` passed with no issues in 82 source files.
- All tests pass (all applicable/affected suites required by the task): yes locally.
- Unexplained failures or skips: none.
- CI is green (all required checks): not started in this subagent lane; requires parent/Lead push and CI verification.

## Known limitations / risks
- Vol surfaces remain scaffolded expiry × moneyness grids; no SABR/local-vol calibration or vendor surface bootstrapping was added.
- QuantLib `BlackVarianceSurface` is used for European equity/FX option valuation when a matching grid is attached; scalar fallback intentionally remains `BlackConstantVol`.
- Existing `Actual365Fixed` and rounded calendar-day maturity convention is preserved, including short-tenor behavior.

## Follow-up / next owner
- Owner: Lead Architect / QA if independent review or CI-gate verification is required.
- Requested action: push and verify required CI checks before final integration, if this lane is being merged.
- Blocking?: no local blocker; CI not run from this subagent lane.
