# Handoff: Final Demo Runbook, Screenshots, And Smoke

## Owner
Lead Architect / Orchestrator coordinating Frontend / Risk UX, DevOps / Platform, and QA & Quant Validation.

## Summary
- Added a final-demo runbook at `docs/demo/final_demo.md`.
- Captured durable screenshots for Overview, Portfolio, VaR & ES, and Stress under `docs/demo/`.
- Added artifact-derived expected output ranges from `data/demo_risk_artifact.json`.
- Added `scripts/check_final_demo.py`, a CI-style clean-checkout smoke that verifies required demo files exist, regenerates the deterministic risk artifact with `--check`, and asserts byte equality with `data/demo_risk_artifact.json`.
- Added focused QA coverage for the smoke in `backend/tests/test_final_demo_check.py`.
- Updated `ROADMAP.md`: the final demo setup, screenshots/runbook, and clean-checkout smoke are marked complete locally.
- No quant/pricing/risk formulas changed. No postponed AI assistant or portfolio presentation work. No live market-data integrations.

## Files changed
- `docs/demo/final_demo.md`
- `scripts/check_final_demo.py`
- `backend/tests/test_final_demo_check.py`
- `docs/demo/riskforge_demo_01_overview.png`
- `docs/demo/riskforge_demo_02_portfolio.png`
- `docs/demo/riskforge_demo_03_var_es.png`
- `docs/demo/riskforge_demo_04_stress.png`
- `docs/agents/HANDOFF_FINAL_DEMO_SMOKE.md`
- `ROADMAP.md`

## Public/interface changes
- New repo-root CLI smoke: `scripts/check_final_demo.py`
- No HTTP, DTO, PricingEngine, risk-engine, or frontend interface changes.

## Numerical conventions
- Units: unchanged from existing `run_demo_risk` / Historical VaR / StressEngine output.
- Sign convention: unchanged from generated artifact.
- Day count/calendar if relevant: N/A.
- Tolerances/reference: byte equality to committed `data/demo_risk_artifact.json`; float stabilization remains owned by the deterministic demo artifact path (`DEMO_ARTIFACT_FLOAT_DECIMALS = 8`).

## Tests added/updated
- `backend/tests/test_final_demo_check.py`: validates the final-demo smoke writes a deterministic artifact, checks expected demo portfolio ids / scenario count / builtin pricing / demo historical dataset, and matches the committed golden artifact byte-for-byte.

## Commands executed

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/check_final_demo.py
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin RISKFORGE_SCENARIO_KERNEL=python .venv/bin/python -m pytest tests/test_final_demo_check.py tests/test_demo_scripts.py tests/test_demo_historical_dataset.py tests/test_demo_portfolios.py -q --tb=line
cd backend && .venv/bin/ruff check ../scripts/check_final_demo.py tests/test_final_demo_check.py
cd e2e && npm test
```

## Results
- Final-demo smoke: exit 0; JSON included `"status": "ok"`, portfolios `["equity-vol", "rates-macro", "global-macro"]`, `pricing_engine="builtin"`, `historical_dataset="demo-historical-factors"`, `methodology="DELTA_GAMMA"`, `scenario_count=5`.
- Focused demo pytest: initial run exposed one expected-string mismatch; fixed to the committed dataset id. Re-run: **9 passed** .
- Affected demo suite: **26 passed** , 1 existing Starlette/httpx deprecation warning.
- Documented artifact command: exit 0; wrote `/tmp/riskforge_demo_risk_artifact.json`; stderr summary `portfolios=3 pricing=builtin dataset=demo-historical-factors`.
- Ruff: final touched-file check passed.
- Backend: affected demo tests passed.
- Frontend: UI screenshot pass captured live app views for the demo runbook; parent integration ran frontend tests/lint/build successfully.
- QuantLib: not required for this deterministic smoke; builtin pricing is the documented artifact path.
- C++: not required; scenario kernel forced to Python for artifact determinism.
- Build: frontend production build passed in parent integration.
- E2E: Playwright `12 passed`.
- All tests pass (all applicable/affected suites required by the task): yes.
- Unexplained failures or skips: none. Existing Starlette/httpx deprecation warning remains.
- CI is green (all required checks): not started in this task; no push/PR requested.

## Status
- `[x]` Seed data + deterministic setup for 3-5 minute demo flow.
- `[x]` Screenshots + demo instructions + expected output ranges.
- `[x]` Clean-checkout verification of demo path.

## Known limitations / risks
- `scripts/check_final_demo.py` validates artifact generation only; browser screenshots are separate committed assets.
- The clean-checkout smoke assumes backend dependencies are installed in `backend/.venv` (or another Python can be substituted in the documented command).

## Follow-up / next owner
- Owner: Frontend/Risk UX + QA, coordinated by Lead Architect.
- Requested action: parent integrator should run full affected suites and push only after required CI is green.
- Blocking?: no.
