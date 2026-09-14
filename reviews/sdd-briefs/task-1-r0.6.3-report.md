# Task 1 Report - R0.6.3 Reuse QuantLib Structures Where Safe

## Task

R0.6.3 - Reuse QuantLib structures where safe.

## Owner

Quant Pricing Engineer.

## Summary

Implemented safe QuantLib adapter reuse for scalar equity/FX option full-revaluation paths. `QuantLibPricingEngine` now caches contract terms, scalar option QuantLib structures with live `SimpleQuote` market inputs, and swap schedules keyed by evaluation date and contract shape. RF-007 remains `IN PROGRESS`.

## Files Changed

- `backend/app/pricing/quantlib.py`
- `backend/tests/test_quantlib_reuse.py`
- `reviews/FINDINGS.md`
- `reviews/REMEDIATION_MILESTONE.md`
- `reviews/r0.6.3-quantlib-reuse-report.md`
- `reviews/sdd-briefs/task-1-r0.6.3-report.md`

## Public / Interface Changes

- None. `PricingEngine` and domain/API contracts are unchanged.
- Reuse is private to the QuantLib adapter.

## Numerical Conventions

- Units: unchanged; option vega remains per one vol point.
- Sign convention: unchanged.
- Day count/calendar: unchanged; cached structures are keyed by evaluation date.
- Tolerance/reference: new cold-path parity test uses absolute `1e-12` against fresh-engine shocked valuations.

## Tests Added / Updated

- Added `test_scalar_option_full_reval_reuses_vanilla_option_structure` to prove scalar option structure reuse under full revaluation.
- Added `test_scalar_option_full_reval_reuse_matches_cold_valuations` to prove no stale market state versus fresh-engine shocked valuations.

## Commands Executed

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_quantlib_reuse.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_quantlib_reuse.py tests/test_quantlib_pricing.py tests/test_quantlib_terms_value.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py tests/test_historical_scenario_kernel.py tests/test_quantlib_*.py tests/test_pricing*.py
.venv/bin/python -m ruff check app/pricing/quantlib.py tests/test_quantlib_reuse.py && .venv/bin/python -m mypy app
.venv/bin/python -m mypy app/pricing/quantlib.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py tests/test_historical_scenario_kernel.py tests/test_quantlib_*.py tests/test_pricing*.py && .venv/bin/python -m ruff check app/pricing/quantlib.py tests/test_quantlib_reuse.py && cd /Users/user/src/quantlineage && /usr/bin/git diff --check
```

## Results

- New reuse test RED before implementation: failed as expected (`ql.VanillaOption` constructed `5`, expected `1`).
- New reuse tests after implementation: `2 passed`.
- Affected QuantLib pricing subset: `44 passed`.
- Brief focused suite: `179 passed`.
- Ruff on touched files: passed.
- `mypy app`: blocked by pre-existing non-Quant errors in `app/risk/historical_data.py` and `app/services/risk_factories.py`.
- `mypy app/pricing/quantlib.py`: blocked by imported `app/risk/historical_data.py`; no touched-file diagnostics were emitted.
- Final verification: brief focused suite `179 passed`, touched-file Ruff passed, and `git diff --check` exited 0.
- CI green: not started from this subtask; local focused verification above.

## Known Limitations / Risks

- RF-007 is not closed. N x S pricing, process partitioning, contribution reuse, cache-policy work, and larger N/S benchmarking remain later tasks.
- Attached vol surfaces and snapshot curves/key rates still rebuild from current market state to avoid stale shocked data.
- Repo-wide mypy has unrelated failures outside this Quant Pricing slice.

## Follow-Up / Handoff

- Owner: Lead Architect / later assigned owners for R0.6.4-R0.6.6 and RF-007 close gate.
- Requested action: independent review of R0.6.3; keep RF-007 open.
- Blocking: no for this slice, but repo-wide mypy remains a broader integration concern.
