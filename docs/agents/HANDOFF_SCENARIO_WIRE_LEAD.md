# Handoff — disposition + formal Scenario wire

## Task
Lead Architect: close Workstream 9 honestly ( Redis/RQ disposition); implement formal Scenario HTTP wire

## Owner
Lead Architect / Orchestrator (implemented Backend/API + ROADMAP; DevOps consulted for — no Redis/RQ code)

## Summary
- ** remaining open (pre-disposition):** only (Redis/RQ optional). + already DONE.
- ** decision:** ROADMAP treated Redis/RQ as **optional**. Compose already ships `postgres` + `backend` + `worker` + `frontend` with Postgres `SKIP LOCKED` claim ( / ADR 005). **Did not** add Redis/RQ (would be ceremony without product semantics; must not regress claim path). Marked ** containers DONE**; Redis/RQ **DEFERRED** accepted residual (not fake Redis `[x]`). **Workstream 9 COMPLETE**.
- formal `ScenarioWire` HTTP under `/api/v1/risk/stress/formal/*` + `GET .../scenarios/formal`; adapters project to legacy `StressScenario` for `StressEngine`. Legacy endpoints unchanged. PricingEngine / VaR math / SKIP LOCKED untouched.

## Files changed
- `ROADMAP.md` — COMPLETE + disposition; DONE
- `docs/adr/004-formal-scenario-domain-model.md` — consequences
- `backend/app/api/scenario_wire.py` — wire DTOs + adapters (new)
- `backend/app/api/stress.py` — formal routes
- `backend/app/api/openapi_examples.py` — formal OpenAPI examples
- `backend/app/risk/scenario_model.py` — docstring ( pointer)
- `backend/tests/test_scenario_wire_api.py` — adapter + API parity tests (new)
- `docs/agents/HANDOFF_SCENARIO_WIRE_LEAD.md` (this file)

## Public/interface changes
- **New** (dual-mount `/api/v1` + legacy):
 - `GET /risk/stress/scenarios/formal` → `list[ScenarioWire]`
 - `POST /risk/stress/formal/custom` → `list[StressResult]`
 - `POST /risk/stress/formal/evaluate/custom` → threat evaluation report
- Legacy `StressScenario` routes unchanged

## Numerical conventions
- Units: same as `MarketSnapshot.bump` / `FactorShock` (equity/FX/vol relative; RateZero absolute decimal rate)
- Tolerances/reference: formal vs legacy custom stress P&L abs `1e-9`; content_hash equality via `scenario_to_stress` / `shock_snapshot`

## Tests added/updated
- `test_scenario_wire_api.py`: wire round-trip, wire→stress hash parity, formal vs legacy custom P&L, formal evaluate, formal list, legacy regression

## Commands executed
```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest \
 tests/test_scenario_wire_api.py tests/test_durable_worker.py -q --tb=short
# → 15 passed

cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest \
 tests/test_scenario_wire_api.py tests/test_durable_worker.py tests/test_api.py \
 tests/test_scenario_model.py tests/test_scenario_engine.py tests/test_stress_scenarios_di.py \
 tests/test_reverse_stress.py tests/test_hedge_comparison.py -q --tb=line
# (re-run after handoff if needed)

.venv/bin/ruff check app/api/scenario_wire.py app/api/stress.py tests/test_scenario_wire_api.py
```

## Results
- Backend: focused + durable worker **15 passed**; stress/API suite **72 passed** (1 Starlette/httpx deprecation warning)
- Frontend: unchanged
- QuantLib: preferred for broader suite when `RISKFORGE_PRICING_ENGINE=quantlib`
- C++: N/A
- Build: N/A
- Ruff: clean on new/changed API + test files
- Workstream 9: **COMPLETE** (Redis/RQ deferred residual)
- **DONE**
- CI/push: feature SHA `9fd2884` (handoff note `0d87f0f`) on `origin/master` (https://github.com/SergTogul/riskforge-mvp)

## Known limitations / risks
- Redis/RQ still not implemented — deferred for fair scheduling/ops only; Postgres SKIP LOCKED remains the claim path
- Hedge-compare / what-if / ScenarioBuilder UI still use legacy `StressScenario` shape
- Declared wire `severity` is metadata; realized severity still from post-reval classification

## Follow-up / next owner
- Owner: Frontend (optional) — ScenarioBuilder emit formal wire; or Stress — methodology docs; or C++ — risk-path SLA; or Demo —
- Requested action: pick next highest-value residual (prefer docs, SLA evidence, or demo data)
- Blocking?: no
