# Handoff — Builtin vs QuantLib ZC bond day-count / compounding

## Task
 — Align Builtin vs QuantLib zero-coupon bond day-count / compounding conventions

## Owner
Quant Pricing Engineer

## Summary
Closed the documented annual-vs-continuous gap by changing Builtin scalar (no-curve) ZC bond pricing to continuous compounding on an Actual365Fixed year fraction that mirrors QuantLib `ZeroCouponBond` + `FlatForward(Continuous, Actual365Fixed)`: `t = max(1, round(T*365))/365`, `PV = face * qty * exp(-y * t)`.

Tight Builtin↔QL parity and continuous golden tests use **rel=1e-10**. Historical annual `face/(1+y)^T` is no longer a reference. Regenerated `data/demo_risk_artifact.json` for the Builtin PV shift on bond books.

## Files changed
- `backend/app/pricing/builtin.py` — `_act365_fixed_years` + continuous scalar bond fallback
- `backend/tests/test_quantlib_golden.py` — parity tests; retire annual gap band
- `backend/tests/test_curve_pricing.py` — continuous Act/365 scalar expectation
- `data/demo_risk_artifact.json` — rebuilt under builtin (bond PV / VaR shift)
- `ROADMAP.md` — DONE; remove from highest-risk / bond-gap callouts
- `docs/agents/HANDOFF_BOND_DAYCOUNT.md` — this file

## Public/interface changes
- None (PricingEngine / BondPosition contracts unchanged). Numeric Builtin bond PVs without curves change (continuous Act/365 vs annual compound).

## Numerical conventions
- Units: absolute currency PV; yield decimal continuous
- Sign convention: long ZCB DV01 remains Builtin analytic `-duration * PV * 1bp` (QL still FD-bumps yield)
- Day count/calendar: Actual365Fixed on NullCalendar advance `max(1, round(T*365))` days (same as QL adapter)
- Tolerances/reference: continuous golden + Builtin↔QL **rel=1e-10**; curve-attached path still DF at domain pillar `maturity_years` (unchanged)

## Tests added/updated
- `test_builtin_ql_zero_coupon_bond_scalar_parity` — flat-market Builtin ≡ QL ≡ continuous golden
- `test_builtin_ql_bond_tenor_ladder_scalar_parity` — fractional/integer tenors
- Removed `test_ql_zero_coupon_bond_annual_compound_gap_documented` (gap closed)
- `test_bond_falls_back_to_continuous_act365_without_curves` — replaces annual assertion

## Commands executed
```bash
cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest \
 tests/test_quantlib_golden.py tests/test_curve_pricing.py tests/test_pricing.py \
 tests/test_quant_properties.py tests/test_quantlib_pricing.py -q --tb=short
# → 86 passed

cd backend && .venv/bin/python -m app.demo.run_demo_risk --check -o ../data/demo_risk_artifact.json
cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin QUANTLINEAGE_SCENARIO_KERNEL=python \
 QUANTLINEAGE_PRICING_CACHE=0 .venv/bin/python -m pytest \
 tests/test_demo_scripts.py tests/test_quantlib_golden.py tests/test_curve_pricing.py -q --tb=line
# → 67 passed

cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q --tb=line
# → 614 passed; 2 failed unrelated (see Known limitations)
```

## Results
- Backend: focused pricing/golden/curve/demo suites green (61 passed post-push recheck)
- QuantLib: golden bond continuous + Builtin parity green (**rel=1e-10**)
- Frontend / C++ / Build: not in scope
- Pushed: `f39ba6a` ( parity) + `8d3d67a` (ROADMAP highest-risk note) on `origin/master`
 - https://github.com/SergTogul/quantlineage/commit/f39ba6ad1e5294352b0e9597f354f682c1df5030

## Known limitations / risks
- Curve-attached Builtin bonds still discount at domain `maturity_years` (pillar T), not calendar-rounded Act/365; QL ZeroCurve pillars use calendar-rounded dates — residual can appear when curves are attached (covered by curve tests, not scalar gap).
- Builtin bond DV01 remains duration-analytic; QL uses 1bp yield FD — not NPV-convention work.
- Full-suite flake observed: `test_risk_run_api.py::test_create_returns_202_queued` can race (QUEUED response already has results). Passes in isolation; not caused by this change.
- Parallel cache/memo work left unstaged (`curve_cache.py` / `scenario_memo.py` / related); not part of this commit.

## Follow-up / next owner
- Owner: Lead Architect — leftovers tracker refreshed (`HANDOFF_LEFTOVERS.md`); listed under Recently closed
- Requested action: none blocking
- Blocking?: no
