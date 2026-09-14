## Task
M1.13 curve bootstrap from market instruments

## Owner
Market Data & Curves Engineer

## Summary
Implemented a scoped deterministic curve bootstrap helper that converts explicit market instruments into a `YieldCurve` and attaches it to immutable `MarketSnapshot` curve/key-rate fields. Existing pricing curve resolution now parses simple non-key tenors such as `6M`, so bond/swap pricing can consume bootstrapped curve payloads without changing pricing methodology.

## Files changed
- `backend/app/market/curves.py`
- `backend/app/pricing/curve_rates.py`
- `backend/tests/test_curves.py`
- `backend/tests/test_curve_pricing.py`
- `ROADMAP.md`
- `docs/agents/HANDOFF_CURVE_BOOTSTRAP_M1_13.md`

## Public/interface changes
- Added `CurveBootstrapInstrument`.
- Added `tenor_to_years`.
- Added `bootstrap_yield_curve`.
- Added `attach_bootstrapped_curve`.
- `pricing.curve_rates.curve_from_payload` now understands parsed tenors (`D`, `W`, `M`, `Y`) in attached curve payloads, not only the original key-tenor set.

## Numerical conventions
- Units: rates are absolute decimals; deposit/simple instruments are annualized simple rates; zero instruments are continuously compounded absolute decimals.
- Sign convention: positive rates lower discount factors; existing pricing signs are unchanged.
- Day count/calendar if relevant: simple tenor parsing uses `D/365`, `W*7/365`, `M/12`, and `Y`; no business calendar, holidays, stubs, or date schedules.
- Tolerances/reference: deposit/simple instruments use `df = 1 / (1 + rT)` and continuous zero `z = -ln(df) / T`; tests assert exact deterministic conversion with `pytest.approx`.

## Tests added/updated
- `test_bootstrap_deposit_and_zero_instruments_sort_nodes_and_convert_rates`: verifies deterministic maturity sorting and simple-rate-to-continuous-zero conversion.
- `test_bootstrap_rejects_duplicate_tenors_and_non_positive_maturities`: verifies invalid bootstrap inputs fail early.
- `test_attach_bootstrapped_curve_is_deterministic_and_updates_key_rates`: verifies stable content hashes for equivalent unordered inputs and snapshot curve/key-rate attachment.
- `test_bootstrapped_curve_feeds_builtin_bond_and_swap_pricing`: verifies existing bond/swap pricing consumes the bootstrapped curve nodes.

## Commands executed
```bash
cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest tests/test_curves.py tests/test_curve_pricing.py -q
cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_curves.py tests/test_curve_pricing.py tests/test_market_snapshot.py tests/test_curve_cache.py tests/test_quantlib_pricing.py -q
cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_curves.py tests/test_curve_pricing.py tests/test_market_snapshot.py tests/test_curve_cache.py -q
cd backend && .venv/bin/python -m ruff check app/market/curves.py app/pricing/curve_rates.py tests/test_curves.py tests/test_curve_pricing.py
cd backend && .venv/bin/python -m mypy app/market/curves.py app/pricing/curve_rates.py
cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q
```

## Results
- Backend: focused curve tests passed (`18 passed`); affected curve/market/pricing subset passed under QuantLib (`41 passed`); full backend suite reported `650 passed, 3 failed, 1 warning`.
- Frontend: not affected; not run.
- QuantLib: affected market/pricing command that included all of `tests/test_quantlib_pricing.py` had `56 passed, 2 failed`; the failures are the existing M1.11 full-surface tests in `tests/test_quantlib_pricing.py` and were not addressed because M1.11 is out of scope for this lane.
- C++: not affected; not run.
- Build: not affected.
- Static analysis: `ruff` passed on touched files; `mypy` passed on touched source modules.
- All tests pass (all applicable/affected suites required by the task): yes for the affected M1.13 subset; no for full backend because of unrelated dirty-tree failures.
- Unexplained failures or skips: none; full-suite failures were `tests/test_next_phase.py::test_new_api_endpoints` (API expectation mismatch) and two full-surface QuantLib option tests outside M1.13 scope.
- CI is green (all required checks): not started; no push/CI requested from this subagent.

## Known limitations / risks
- This is a deterministic offline single-curve helper, not a live market-data integration.
- No production swap/futures bootstrap, convexity adjustment, calendars, holidays, business-day conventions, stubs, interpolation-method selection, or multi-curve OIS/projection calibration.
- Deposit/simple instruments use a simple money-market discount-factor conversion; zero instruments are assumed to be continuous zeros.
- Existing swap pricing still uses the resolved curve zero at maturity as its simplified par/market rate proxy; pricing methodology was intentionally not rewritten.

## Follow-up / next owner
- Owner: Lead Architect / Quant Pricing Engineer
- Requested action: decide if a future production bootstrap should include swap-quote calibration and explicit convention models.
- Blocking?: no
