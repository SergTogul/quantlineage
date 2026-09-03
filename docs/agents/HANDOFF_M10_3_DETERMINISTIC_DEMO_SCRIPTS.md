# Handoff — M10.3 Deterministic demo scripts

## Task
M10.3 — Deterministic demo scripts (VaR/stress artifacts from demo portfolios + historical dataset)

## Owner
Backend/API Engineer (Lead Architect coordinating; Market Data / Frontend not required)

## Summary
- Shipped `backend/app/demo/run_demo_risk.py` (+ `scripts/run_demo_risk.py` shim) that loads M10.1 demo portfolios and the M10.2 demo factor CSV, runs summary VaR + `DEFAULT_SCENARIOS` stress via `PortfolioService`, and emits sorted-key JSON.
- Defaults: `RISKFORGE_PRICING_ENGINE=builtin`, `RISKFORGE_SCENARIO_KERNEL=python` for cross-run byte parity; `--check` asserts two consecutive builds match.
- Frozen reference artifact committed at `data/demo_risk_artifact.json`.
- No live vendors. PricingEngine seams untouched. Milestone 10 marked **COMPLETE** (M10.1–M10.3).

## Files changed
- `backend/app/demo/__init__.py` — lazy package exports
- `backend/app/demo/run_demo_risk.py` — artifact builder + CLI
- `scripts/run_demo_risk.py` — thin repo-root entrypoint
- `backend/tests/test_demo_scripts.py` — new
- `data/demo_risk_artifact.json` — frozen builtin artifact
- `data/README.md` — M10.3 usage
- `README.md` — demo data bullet
- `ROADMAP.md` — M10.3 DONE; Milestone 10 COMPLETE
- `docs/agents/HANDOFF_M10_3_DETERMINISTIC_DEMO_SCRIPTS.md` — this file

## Public/interface changes
- **New** Python APIs: `build_demo_risk_artifact`, `dumps_demo_artifact`, `run_demo_risk`, `default_artifact_path`
- **New** CLI: `python -m app.demo.run_demo_risk` / `scripts/run_demo_risk.py`
- No new HTTP routes; no PricingEngine interface changes

## Numerical conventions
- Units / signs: same as Historical VaR + StressEngine (portfolio currency PnL)
- Tolerances/reference: byte-identical JSON for builtin + demo CSV + Python kernel; golden file under `data/`

## Tests added/updated
- `test_demo_scripts.py`: catalog coverage, byte-identical re-runs, CLI, subset portfolio, committed golden match

## Commands executed
```bash
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin RISKFORGE_PRICING_CACHE=0 \
  RISKFORGE_SCENARIO_KERNEL=python .venv/bin/python -m app.demo.run_demo_risk \
  --check -o ../data/demo_risk_artifact.json

cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin RISKFORGE_PRICING_CACHE=0 \
  RISKFORGE_SCENARIO_KERNEL=python .venv/bin/python -m pytest \
  tests/test_demo_scripts.py tests/test_demo_historical_dataset.py \
  tests/test_demo_portfolios.py tests/test_api.py tests/test_risk.py \
  tests/test_historical_data.py -q --tb=line

.venv/bin/ruff check app/demo tests/test_demo_scripts.py
```

## Results
- Backend: affected suite green (see commit message / local run)
- Frontend: unchanged
- QuantLib: not required for M10.3 artifact path (builtin default)
- C++: N/A (kernel forced to python)
- Milestone 10: **COMPLETE**

## Known limitations / risks
- Artifact omits VaR contributions and stress `by_position` (size); use API for drill-down
- QuantLib / native-kernel runs are not asserted byte-identical to the frozen builtin artifact
- Generated JSON is for demo reproducibility, not a production risk report

## Follow-up / next owner
- Owner: Lead Architect — pick next residual per ROADMAP: **M11 AI** / **M6 SLA** / **M3.9 methodology docs**
- Requested action: schedule highest-value residual; M13 can reuse `run_demo_risk` for clean-checkout demo evidence
- Blocking?: no
