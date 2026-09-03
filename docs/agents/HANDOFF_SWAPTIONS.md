# Handoff: Swaption Pricing Slice

## Task completion: vanilla European swaption pricing

## Owner
Quant Pricing Engineer

## Summary
Added a vanilla `SwaptionPosition` and priced long payer/receiver swaptions as flat-forward Black-76 options on a generated fixed-leg par-swap annuity behind both Builtin and QuantLib pricing engines. This completes the scoped vanilla caps/floors/swaptions pricing slice while documenting that richer IR volatility cubes, smiles, Bermudan/callable structures, and explicit date schedules remain outside this lane.

## Files changed
- `backend/app/domain/models.py`
- `backend/app/market/snapshot.py`
- `backend/app/pricing/builtin.py`
- `backend/app/pricing/quantlib.py`
- `backend/tests/test_ir_options_pricing.py`
- `backend/tests/test_quantlib_pricing.py`
- `README.md`
- `ROADMAP.md`
- `docs/agents/HANDOFF_SWAPTIONS.md`

## Public/interface changes
- New portfolio position discriminator: `type="swaption"`.
- New fields: `currency`, `notional`, `quantity`, `strike`, `option_maturity_years`, `swap_tenor_years`, `volatility`, `option_type`, `forward_swap_rate`, `discount_rate`, `payment_frequency_per_year`.
- `PricingEngine.value(position, market=None)` interface is unchanged.

## Numerical conventions
- Units: rates, strike, and volatility are decimals; notional is currency notional; vega is reported per 1 vol point.
- Sign convention: `option_type="payer"` is a long call on the forward swap rate; `option_type="receiver"` is a long put; signed `quantity` scales exposure.
- Day count/calendar if relevant: no explicit dates/calendars in this slice. `option_maturity_years` is the European expiry tenor. `swap_tenor_years` and `payment_frequency_per_year` generate equal fixed-leg annuity periods paid after expiry and discounted continuously at `discount_rate`.
- Tolerances/reference: Builtin analytical Black-76 annuity reference is cross-checked against QuantLib `blackFormula`; parity asserted at tight deterministic floating tolerance (`rel=1e-12`, `abs=1e-8`).

## Tests added/updated
- `test_swaption_position_round_trips_through_discriminated_union`: serialization/union round trip.
- `test_builtin_swaption_matches_independent_black76_reference`: Builtin reference valuation parity.
- `test_builtin_swaption_payer_receiver_sign_and_parity_invariants`: payer/receiver positive value, positive vega, ATM parity.
- `test_builtin_swaption_rate_and_vol_monotonicity`: payer/receiver rate monotonicity and volatility monotonicity.
- `test_builtin_swaption_respects_snapshot_rate_inputs`: snapshot projection/discount marks affect valuation.
- `test_position_market_snapshot_preserves_swaption_forward_and_discount_marks`: generated snapshot preserves trade-local marks.
- `test_swaption_matches_builtin_without_fallback`: QuantLib adapter parity and no Builtin fallback.

## Commands executed

```bash
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_ir_options_pricing.py tests/test_quantlib_pricing.py::test_swaption_matches_builtin_without_fallback -q --tb=short
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_ir_options_pricing.py tests/test_quantlib_pricing.py::test_swaption_matches_builtin_without_fallback -q --tb=short
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_ir_options_pricing.py tests/test_quantlib_pricing.py tests/test_pricing.py tests/test_curve_pricing.py tests/test_surface_vol_pricing.py tests/test_quant_properties.py tests/test_quantlib_golden.py tests/test_sensitivities.py -q --tb=short
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_ir_options_pricing.py tests/test_quantlib_pricing.py tests/test_pricing.py tests/test_curve_pricing.py tests/test_quant_properties.py tests/test_quantlib_golden.py tests/test_sensitivities.py -q --tb=short
cd backend && .venv/bin/ruff check app tests && .venv/bin/mypy app
cd backend && .venv/bin/ruff check app tests/test_ir_options_pricing.py tests/test_quantlib_pricing.py && .venv/bin/mypy app
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q --tb=short
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_surface_vol_pricing.py -q --tb=short
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_ir_options_pricing.py tests/test_quantlib_pricing.py tests/test_pricing.py tests/test_curve_pricing.py tests/test_surface_vol_pricing.py tests/test_quant_properties.py tests/test_quantlib_golden.py tests/test_sensitivities.py -q --tb=short

```

## Results
- Backend: focused red run failed as expected on missing `SwaptionPosition`; focused green run `13 passed`; affected pricing/property/sensitivity suite final rerun `119 passed`; full backend suite `639 passed`, 1 known Starlette/httpx deprecation warning.
- Frontend: n/a.
- QuantLib: swaption no-fallback parity test included in focused green run and passed.
- C++: n/a.
- Build: scoped backend static checks passed (`ruff check app tests/test_ir_options_pricing.py tests/test_quantlib_pricing.py`; `mypy app`). A full `ruff check app tests` attempt stopped on a pre-existing unrelated import-format issue in `tests/test_market_snapshot.py`.
- All tests pass (all applicable/affected suites required by the task): yes; full backend pytest passed.
- Unexplained failures or skips: none. One earlier affected-suite attempt transiently failed `tests/test_surface_vol_pricing.py::test_builtin_flat_surfaces_match_scalar_after_typed_vol_apply`; the same file passed in isolation (`6 passed`) and the original affected suite passed on rerun (`119 passed`).
- CI is green (all required checks): not started for this local integration batch.

## Known limitations / risks
- Swaption valuation is flat positive-rate Black-76 on a generated annuity, not a production IR-vol cube/smile implementation.
- European payer/receiver only; no Bermudan exercise, callable structures, physical/cash settlement variation, or explicit calendar/date schedules.
- Snapshot rate input uses scalar discount/projection marks; richer IR volatility market-data schema remains a future Market Data / Quant handoff.

## Follow-up / next owner
- Owner: Market Data & Curves plus Quant Pricing Engineer.
- Requested action: design and implement richer IR volatility market data/cube and explicit swaption date/schedule conventions when product scope requires them.
- Blocking?: no for the scoped vanilla pricing slice.
