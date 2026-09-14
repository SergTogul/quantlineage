# Task 14 Report — RF-011 explicit equity-currency / rate selection

## Task
RF-011 explicit equity-currency / rate selection (R0.4.1-C)

## Owner
Market Data & Curves Engineer (Quant Pricing for Builtin / QuantLib lookup)

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-011)

## Summary
Equity / equity-future / European-option Positions now carry explicit
`currency` (default `"USD"`). Production valuation selects
`market.rates[terms.currency]`. EUR option/future with `rates={}` or USD-only
rates fail closed (`MissingMarketDataError`), not silent USD 0.04. Snapshot
constructor default when `rates` is omitted remains `{"USD": 0.04}`. Empty
`rates={}` still injects nothing. Demo snapshot ids and position-id sets
unchanged.

**Disposition: IN PROGRESS** — Task 13 residuals remain: libraries/persistence
still store `StressScenario`; historical `MarketScenario` and reverse-stress
factor families are not the stored canonical type.

TDD: new EUR Position construction failed first (`extra_forbidden` on
`currency`). After the DTO field, missing-EUR lookup failed closed as
required.

## Files changed
- `backend/app/domain/models.py` — `currency` on equity families
- `backend/app/domain/instrument_terms.py` — `_equity_currency` uses the field
- `backend/app/pricing/builtin.py` — fail closed if settlement ccy missing
- `backend/app/risk/attribution.py` — `_rate_currency` uses `position.currency`
- `backend/tests/test_explicit_currency_rate.py` — new fail-closed tests
- `backend/tests/test_instrument_terms.py` — round-trip `position.currency`
- `reviews/FINDINGS.md` — RF-011 **IN PROGRESS** with R0.4.1-C residual
- `reviews/REMEDIATION_MILESTONE.md` — R0.4.1-C
- `reviews/r0.4-architecture-brief.md` — R0.4.1-C row
- `reviews/r0.4.1-c-explicit-currency-rate-report.md`
- `reviews/sdd-briefs/task-14-rf011-explicit-currency-report.md` — this handoff

## Public/interface changes
- Equity-family Positions: optional `currency` (default `"USD"`).
- Missing rate for that currency: `MissingMarketDataError` / `rates[CCY]`.
- Snapshot `rates` omitted default unchanged. `rates={}` unchanged.

## Numerical conventions
- Units: unchanged (scalar snapshot rates for equity option r / future carry)
- Sign convention: unchanged
- Day count/calendar if relevant: n/a (no formula change for matching-ccy books)
- Tolerances/reference: EUR vs USD isolation abs/rel `1e-12`; USD demo books
  still price from existing demo snapshots

## Tests added/updated
- EUR option/future fail-closed on `rates={}` and USD-only rates
- EUR option PV isolated from USD rate moves when EUR is present
- USD option + omitted snapshot rates still uses constructor default 0.04
- USD option + `rates={}` still `rates[USD]`
- terms copy explicit EUR; attribution `_rate_currency` uses EUR
- demo snapshot ids + position-id sets pinned
- QuantLib EUR option missing-EUR fail-closed

## Commands executed
TDD red (new file, before production change): 8 failed as expected
(`currency` extra_forbidden). 4 already-green pins (USD empty-rates,
constructor default, demo ids).

Brief (required):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_omit_market.py tests/test_builtin_pricing.py \
  tests/test_curve_pricing.py tests/test_quantlib_terms_value.py \
  tests/test_explicit_currency_rate.py tests/test_instrument_terms.py
```

Covering:

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_market_authority.py tests/test_quantlib_pricing.py \
  tests/test_attribution.py tests/test_builtin_terms_value.py \
  tests/test_demo_portfolios.py tests/test_demo_snapshot_adapter.py \
  tests/test_market_snapshot.py tests/test_value_requires_market.py
```

## Results
- Backend brief + new currency + terms: **124 passed**, 3.02s. No skips.
- Covering authority/demo/attribution/snapshot: **175 passed**, 1 warning
  (Starlette TestClient deprecation). No skips.
- Frontend: n/a
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push)

## MET vs PARTIAL vs UNMET (this gate)

| Cell | Score |
|---|---|
| Explicit equity-currency / rate selection | **MET** |
| Missing non-USD rate on explicit snapshot fails closed | **MET** |
| Constructor `rates` default `{"USD": 0.04}` preserved | **MET** |
| Missing-rate tests with `rates={}` stay valid | **MET** |
| Demo snapshot ids / position-id sets unchanged | **MET** |
| Typed curves/FX from Task 12 | **MET** (prior slice) |
| Engine-facing Scenario-only from Task 13 | **MET** (prior slice) |
| Historical / stress / custom / reverse / persistence / API all store one typed model | **PARTIAL** (Task 13 residual) |
| CLOSE RF-011 | **UNMET** (required KEEP OPEN) |

## Why IN PROGRESS (not CLOSE)
Would not defend CLOSE. Residual:

1. Libraries / persistence still store `StressScenario` (adapted at the boundary).
2. Historical `MarketScenario` and reverse-stress factor-family solvers are not the stored canonical `Scenario`.
3. Deprecated StressScenario POST routes remain (adapter).
4. Snapshot omitted-`rates` constructor default is still USD 0.04 (required preserve, not a silent EUR fallback).

## Known limitations / risks
- Position `currency` omitted still defaults to USD (bond-style).
- Cash equity does not consume rates.
- Equity option/future still use scalar `rates[ccy]`, not curve lookup (methodology unchanged for matching-ccy books).

## Follow-up / next owner
- Owner: independent reviewer (Task 14 review), then RF-011 close-gate only after stored dual types are retired
- Requested action: KEEP OPEN; do not CLOSE RF-011
- Blocking?: no
