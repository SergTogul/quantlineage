# Task 2 Report — R0.6.4 Remove Anti-Cache Behavior

## Task

R0.6.4 — Remove anti-cache behavior.

## Owner

Quant Pricing Engineer.

## Summary

Disabled the per-snapshot valuation LRU for unique-shock / FULL_REVALUATION execution. `CachedPricingEngine` bypasses hash/get/put while `bypass_valuation_lru` is active; production full-reval loops and `shocked_value` take that path. Repeated base-snapshot valuations still hit. RF-007 remains `IN PROGRESS`.

## Files Changed

- `backend/app/pricing/cache.py`
- `backend/app/pricing/factory.py`
- `backend/app/risk/historical.py`
- `backend/app/risk/var.py`
- `backend/app/risk/es.py`
- `backend/tests/test_pricing_anti_cache.py`
- `reviews/FINDINGS.md`
- `reviews/REMEDIATION_MILESTONE.md`
- `reviews/r0.6.4-anti-cache-report.md`
- `reviews/sdd-briefs/task-2-r0.6.4-report.md`

## Public / Interface Changes

- Added `bypass_valuation_lru()` / `valuation_lru_bypassed()` on the pricing cache module. `PricingEngine.value` signature is unchanged.
- `CachedPricingEngine.shocked_value` now bypasses the LRU.
- Full-reval callers wrap unique-shock loops in the bypass context; no DTO/API change.

## Numerical Conventions

- Units: unchanged.
- Sign convention: unchanged.
- Day count/calendar: unchanged.
- Tolerance/reference: unique-shock P&L vs inner/cold engine and existing unit-equity golden `[-100, 0, 50]` at absolute `1e-12`.

## Tests Added / Updated

- Added `test_bypass_context_does_not_consult_or_populate_lru`.
- Added `test_bypass_does_not_build_per_snapshot_cache_keys`.
- Added `test_unique_shock_full_reval_does_not_consult_lru` (spy get + `valuation_cache_key`).
- Added `test_unique_shock_full_reval_matches_uncached_inner`.
- Added `test_var_analytics_unique_shock_full_reval_does_not_consult_lru`.
- Added `test_base_lru_hit_survives_unique_shock_bypass`.
- Added `test_shocked_value_bypasses_per_snapshot_lru`.
- Existing repeated-base cache goldens left in place.

## Commands Executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_pricing_anti_cache.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py tests/test_quantlib_reuse.py tests/test_pricing*.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py tests/test_quantlib_reuse.py tests/test_pricing*.py tests/test_curve_cache.py tests/test_full_reval_golden.py tests/test_var_methodology.py tests/test_es_contributions.py
.venv/bin/python -m ruff check app/pricing/cache.py app/pricing/factory.py app/risk/historical.py app/risk/var.py app/risk/es.py tests/test_pricing_anti_cache.py
.venv/bin/python -m mypy app/pricing/cache.py app/risk/historical.py app/risk/var.py app/risk/es.py
cd /Users/user/src/riskforge-mvp && /usr/bin/git diff --check
```

`tests/test_cache*.py` from the brief does not exist; `tests/test_pricing_cache.py` is included via `tests/test_pricing*.py`.

## Results

- New anti-cache tests RED before wiring: unique-shock path still consulted the LRU (zero-shock cache hit; later hash/get on unique snaps).
- New anti-cache tests after implementation: `8 passed`.
- Brief focused suite: `53 passed`.
- Affected extras (curve cache, full-reval golden, VaR methodology, ES contributions): `82 passed` together with the brief set.
- Ruff on touched files: passed.
- `mypy` on touched modules: blocked by pre-existing `app/risk/historical_data.py` protocol errors; no diagnostics in `cache.py`.
- `git diff --check`: passed.
- CI green: not started from this subtask; local focused verification above.

## Known Limitations / Risks

- RF-007 is not closed. N×S pricing, process partitioning, contribution reuse, and larger N/S benchmarking remain later tasks.
- Reverse-stress / hierarchy / generic stress `value()` on unique snaps still use the LRU unless they call `shocked_value` or enter `bypass_valuation_lru`.
- Curve-construction cache was left enabled on purpose.
- Repo-wide mypy has unrelated failures outside this slice.

## Follow-Up / Handoff

- Owner: Lead Architect / later assigned owners for R0.6.5–R0.6.6 and RF-007 close gate.
- Requested action: independent review of R0.6.4; keep RF-007 open.
- Blocking: no for this slice.
