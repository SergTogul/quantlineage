# Task 29 Report — RF-018 frontend contracts (not TypeScript rewrite)

## Task
RF-018 frontend contracts: OpenAPI scenario snapshot, request-boundary %/bp assertions, dependency pins

## Owner
Frontend / Risk UX Engineer (`docs/agents/08_FRONTEND_RISK_UX_ENGINEER.md`)

## Status
**CLOSED.** RF-018 **CLOSED** as **MET** without a TypeScript rewrite. Milestone R0 remains **IN PROGRESS** (RF-014 leftovers). Do not restore COMPLETE.

## Summary
Pinned scenario POST paths from a committed OpenAPI snapshot (`/api/v1/risk/stress/formal/evaluate/custom`, `/formal/compare`, `/reverse/multi`). UI builders convert display % → fraction and bp → decimal on the wire. Click/request-boundary tests require −20% equity → `-0.20` and 100 bp → `0.01`; sending `-20` as a shock amount fails closed before fetch. `npm ci` / no-`"latest"` pins re-locked in frontend tests. No pricing formulas in the UI.

## Files changed
- `frontend/src/contracts/openapi-scenario.json` — committed scenario OpenAPI snapshot
- `frontend/src/contracts/scenarioApi.js` — consumes snapshot POST paths
- `frontend/src/contracts/wireUnits.js` — display %/bp conversion + wire assertions
- `frontend/src/contracts/*.test.js` — contract, units, dependency pins
- `frontend/src/api.js` — formal paths + fail-closed unit guards
- `frontend/src/lib/risk.mjs` — builders use shared conversion helpers
- `frontend/src/api.test.js`, `ScenarioBuilder.test.jsx`, `ReverseStressMulti.test.jsx`, `HedgeCompare.test.jsx`
- `backend/tests/test_rf018_frontend_openapi_snapshot.py` — snapshot vs `app.openapi()`
- `backend/tests/test_rf020_r0_exit.py` — RF-018 dropped from `OPEN_LEFTOVERS`; closed pin
- `reviews/FINDINGS.md`, `reviews/REMEDIATION_MILESTONE.md`, `ROADMAP.md`, `docs/known_limitations.md`

## Public/interface changes
- UI still POSTs formal `ScenarioWire` (no TS client). Wire amounts are bump units (relative fraction; rate decimal).
- `evaluateCustomScenario` / `compareHedge` / `reverseStressMulti` reject display-unit leaks.

## Numerical conventions
- Units: equity/FX/vol display % → fraction (`-20` → `-0.20`); rates display bp → decimal (`100` → `0.01` = `0.0001` per bp)
- Sign convention: form equity crash is negative; wire amount matches
- Day count/calendar if relevant: n/a
- Tolerances/reference: exact equality on captured POST JSON

## Tests added/updated
- OpenAPI snapshot path/schema pins; FactorShockWire amount is bump units
- Click-boundary: Scenario Builder, hedge compare, reverse-multi POST bodies
- API guards: `-20` equity / `100` rate / reverse-multi `5` fail
- `package.json` no `"latest"`; Dockerfile `npm ci`
- `test_rf018_frontend_contracts_closed`; snapshot drift vs FastAPI

TDD: missing snapshot/module and missing wire guards failed first; then green.

## Commands executed
```bash
cd /Users/user/src/riskforge-mvp/frontend && npm test
# 16 files / 114 passed

cd /Users/user/src/riskforge-mvp/frontend && npm run lint
# exit 0

cd /Users/user/src/riskforge-mvp/frontend && npm run build
# vite build OK

cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_rf018_frontend_openapi_snapshot.py \
  tests/test_rf020_r0_exit.py \
  tests/test_container_hardening.py
# 17 passed

.venv/bin/ruff check tests/test_rf018_frontend_openapi_snapshot.py tests/test_rf020_r0_exit.py
# All checks passed
```

## Results
- Backend required suite: **17 passed**
- Frontend: **114 passed** (16 files); lint exit 0; production build OK
- QuantLib: n/a
- C++: n/a
- Build: vite production build OK (`dist/assets/index-CUDA6T4-.js`)
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## Known limitations / risks
- Not a generated TypeScript client. Snapshot covers the three UI scenario POST paths, not the full OpenAPI surface.
- Relative |amount| ≥ 2 and rate |amount| ≥ 1 are treated as display-unit leaks (catches −20 / 100 / −5).
- RF-014 shared ACLs/TLS remain open. Do not stamp Milestone R0 COMPLETE.

## Follow-up / next owner
- Owner: Lead Architect / remaining leftover owners (RF-014)
- Requested action: independent review of RF-018 close
- Blocking?: no
