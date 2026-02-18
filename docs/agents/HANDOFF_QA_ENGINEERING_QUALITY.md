# Handoff — QuantLib golden expand (QA)

## Task
 — Expand QuantLib golden coverage with documented tolerances/reference

## Owner
QA & Quant Validation Engineer

## Summary
- Expanded `backend/tests/test_quantlib_golden.py` from a thin slice to ~49 golden cases across equity/FX options, ZC bonds, IRS, equity futures, FX forwards, IR futures, edge evaluation dates, and PricingEngine seam checks.
- Bond day-count gap **documented and closed for validation**: tight continuous Actual365Fixed golden replaces reliance on annual-compound parity (wide band retained as documentation).
- **No production/adapter code changes** — PricingEngine seams preserved.
- ** DONE**. Workstream 9 remains **PARTIAL** ( Redis optional; reverse-multi UI/E2E open). Do **not** mark Workstream 9 COMPLETE.

## Files changed
- `backend/tests/test_quantlib_golden.py`
- `ROADMAP.md`
- `docs/agents/HANDOFF_QA_ENGINEERING_QUALITY.md` (this file)

## Public/interface changes
- None (tests + docs only)

## Numerical conventions
- Options: analytic BS/GK via `statistics.NormalDist`; QL `AnalyticEuropeanEngine`; **rel=2e-3**, abs=1e-6 (date-rounded exercise vs continuous T)
- Equity future / FX forward: CIP via FlatForward Time DFs ≡ Builtin → **rel=1e-12**, abs=1e-9
- IR future: STIR algebra `qty*pv01*(quoted-forward)*1e4` → **rel=1e-12**, abs=1e-9
- Bond (tight): `face * exp(-y * Actual365Fixed.yearFraction(eval, round(T*365)))` → **rel=1e-10**
- Bond (documented gap): annual compound vs QL continuous → **rel=5e-2** only
- IRS ATM residual: Actual365Fixed fixed vs Actual360 float → **|PV|/notional < 50bp**; payer DV01 > 0
- Eval dates pinned (weekday / Saturday / leap day / year-end) — no wall-clock flakiness

## Tests added/updated
- Equity option moneyness + edge eval dates + 1-day tenor finite
- Continuous ZC bond ladder + annual-compound gap documentation + yield monotonicity
- IRS ATM residual, receive=-payer, tenor DV01
- Equity future CIP ladder; FX forward CIP + market snapshot
- FX option moneyness ladder; IR STIR algebra + forward shock
- Deterministic replay + `isinstance(..., PricingEngine)`

## Commands executed
```bash
cd backend && RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_quantlib_golden.py -v
# → 49 passed

cd backend && RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_quantlib_golden.py tests/test_quantlib_pricing.py -q
# → 60 passed

cd backend && RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q
# → 564 passed, 1 warning (Starlette/httpx deprecation)
```

## Results
- Golden focused: 49 passed
- Full backend QuantLib: 564 passed, 0 unexpected skips
- Workstream 9: still PARTIAL

## Known limitations / risks
- Very short option tenors (`T ≲ 0.05`) and sub-day clamp policy remain in `test_quantlib_pricing.py` (wider bands) — not asserted at 2e-3 in golden file
- IRS NPV not identical to Builtin annuity model (QL VanillaSwap schedule/day-count)
- Caps/floors/swaptions still deferred product gap (not )

## Follow-up / next owner
1. **Owner: Frontend — reverse-multi UI** — Stress section multi-factor reverse panel wired to `POST /risk/stress/reverse/multi`; then QA closes residual E2E. **Blocking?: yes** for that E2E gap / honest close path.
2. **Owner: DevOps — ** — Optional Redis/RQ worker path in compose (Postgres SKIP LOCKED path already exists). **Blocking?: no** (optional) — but ROADMAP should stay PARTIAL until is DONE or explicitly deferred with Lead Architect note.
3. Do **not** mark Workstream 9 COMPLETE until honesty + reverse-multi E2E (or explicit deferral) are settled.
