# Agent Handoff — M5.5 Caching polish

## Task
M5.5 — close remaining cache polish (curve-construction + scenario memo)

## Owner
Quant Pricing Engineer (02); scenario memo touches Stress/Scenario surface in `scenario_engine` (minimal wiring only)

## Summary
Closed M5.5 beyond the existing valuation LRU:

1. **Curve-construction cache** (`backend/app/pricing/curve_cache.py`) — LRU for `select_yield_curve` keyed by currency-relevant market fingerprint (rates / key_rates / curves / projection). Equity/FX/vol bumps that leave rate marks unchanged hit; rate bumps miss.
2. **Scenario-result memo** (`backend/app/risk/scenario_memo.py`) — LRU for `apply_scenario` keyed by `base.id` + `content_hash` + shock fingerprint + id tag. Defensive `model_copy` on get/put.
3. Env flags mirror `RISKFORGE_PRICING_CACHE`:
   - `RISKFORGE_CURVE_CACHE` / `RISKFORGE_CURVE_CACHE_SIZE` (default on / 256)
   - `RISKFORGE_SCENARIO_CACHE` / `RISKFORGE_SCENARIO_CACHE_SIZE` (default on / 1024)
4. Process-wide caches reset in `tests/conftest.py`; demo artifact tests disable all three caches for determinism.
5. ROADMAP M5.5 marked **DONE**. No numerical methodology change; `PricingEngine` seams preserved. No Market Data handoff (cache lives under `pricing/`, not `market/`).

## Files changed
- `backend/app/pricing/curve_cache.py` (new)
- `backend/app/pricing/curve_rates.py`
- `backend/app/risk/scenario_memo.py` (new)
- `backend/app/risk/scenario_engine.py`
- `backend/tests/conftest.py`
- `backend/tests/test_curve_cache.py` (new)
- `backend/tests/test_scenario_memo.py` (new)
- `backend/tests/test_demo_scripts.py`
- `ROADMAP.md` (M5.5 lines only)

## Public/interface changes
- None to `PricingEngine`. Optional env flags only.
- `select_yield_curve` / `apply_scenario` behavior unchanged when caches disabled or on miss.

## Numerical conventions
- Units: unchanged (continuous zeros; scenario bump units as before)
- Tolerances: equality of marks / zeros with vs without cache; hit/miss counters
- No risk numbers invented

## Tests added/updated
- `test_curve_cache.py` — hit, miss on rate bump, hit on equity bump, prefer_projection keys, disabled env, matches uncached
- `test_scenario_memo.py` — hit, miss on base/shock change, matches uncached, disabled env
- `conftest.py` — autouse reset of process caches
- `test_demo_scripts.py` — disable curve/scenario caches

## Commands executed
```bash
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest tests/test_curve_cache.py tests/test_scenario_memo.py tests/test_pricing_cache.py -q --tb=line
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q --tb=line
```

## Results
- Focused cache tests: **24 passed**
- Full backend QuantLib suite: **619 passed**, 1 Starlette/httpx deprecation warning
- Commit: (see push SHA below)
- Push: origin/master

## Known limitations / risks
- Process-wide LRUs require test resets (done in conftest).
- Scenario memo includes `base.id` in the key (correct for id-tagged results; same marks / different ids do not share).
- QL `ZeroCurve` handle construction inside the adapter is still per-call (YieldCurve construction is what is memoized).

## Follow-up / next owner
- Owner: none required for M5.5
- Optional later: QuantLib term-structure handle cache inside `QuantLibPricingEngine` (still no QuantLib leakage outside adapter)
- Blocking?: no
