# Agent Handoff — Demo artifact float drift CI failure

## Task
Fix `backend-pytest` failure on master: `test_committed_artifact_matches_rebuild`.

## Owner
Backend/API + QA (DevOps for push/watch)

## Failure (exact)
- CI run: https://github.com/SergTogul/riskforge-mvp/actions/runs/33708507094
- Job: `backend-pytest` / Run pytest
- Test: `tests/test_demo_scripts.py::test_committed_artifact_matches_rebuild`
- Cause: exact JSON equality between committed `data/demo_risk_artifact.json` (macOS rebuild after M1.12) and Linux GHA rebuild differed by ~1e-11–1e-14 ULP on stress PnLs (e.g. `4861.095921907545` vs `4861.095921907533`). Other jobs (lint, frontend, e2e, postgres) were green.

## Fix
Round floats to 8 decimal places in `dumps_demo_artifact` via `_stabilize_floats` so golden dumps are cross-platform stable; regenerate committed artifact; add ULP-pair regression test.

## Files changed
- `backend/app/demo/run_demo_risk.py` — `DEMO_ARTIFACT_FLOAT_DECIMALS=8`, `_stabilize_floats`, dump path
- `backend/tests/test_demo_scripts.py` — ULP collapse test
- `data/demo_risk_artifact.json` — regenerated with 8 dp rounding

## Public/interface changes
- Dump formatting only (JSON numeric precision). No PricingEngine / risk math changes.

## Numerical conventions
- Demo artifact floats quantized to **8 dp** (sub-cent for dollar PnL; absorbs observed GHA ULP drift). Same-machine re-runs remain byte-identical.

## Tests added/updated
- `test_stabilize_floats_collapses_platform_ulp` — known CI ULP pairs must dump equal

## Commands executed
```bash
gh run list -L 5   # worked after sibling re-auth
gh run view 33708507094 --log-failed

cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin RISKFORGE_PRICING_CACHE=0 \
  RISKFORGE_CURVE_CACHE=0 RISKFORGE_SCENARIO_CACHE=0 RISKFORGE_SCENARIO_KERNEL=python \
  .venv/bin/python -m app.demo.run_demo_risk --check -o ../data/demo_risk_artifact.json

cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q --tb=line
cd backend && .venv/bin/ruff check app tests && .venv/bin/mypy app
cd frontend && npm test && npm run lint && npm run build
```

## Results (local green evidence)
- Backend: **620 passed**, 1 Starlette/httpx warning
- Ruff / mypy: OK
- Frontend: **70** Vitest; ESLint OK; Vite build OK
- Push: `926ed55` → `origin/master`

## Known limitations / risks
- Artifact is demo-grade (8 dp), not a production risk report.
- Local e2e may fail if Vite is not started / port conflict; GHA e2e was already green on the failing run.

## Follow-up / next owner
- Confirm GHA green on SHA `926ed55` via `gh run watch` / Actions URL
- Blocking?: no for product code; watch CI for confirmation only
