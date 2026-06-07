# Task 20 Report — RF-011 historical + reverse use canonical Scenario

## Task
RF-011 historical + reverse use canonical Scenario (R0.4.2-G)

## Owner
Stress & Scenario Engineer (`docs/agents/05_STRESS_SCENARIO_ENGINEER.md`)

## Status
**CLOSED** (CLOSE RF-011; named residuals below)

## Summary
Historical generation (`historical_market_scenarios`, panel equivalents) and
apply (`iter_*_shocked_snapshots`) now yield/apply canonical `Scenario` with
typed `FactorShock` against the live `MarketSnapshot`. Rate bp→decimal only
via `shock_units`. `MarketScenario` / `FactorChange` remain adapters.
Reverse-stress `ReverseStressResult` carries the applied `Scenario` (zero /
bound / converged); HTTP JSON projects ScenarioWire; `required_shock` wire
units unchanged. R0.4.2-F review stamped APPROVE. Goldens / snapshot ids /
VaR numbers unchanged.

**Disposition: CLOSE** — historical, stress, custom, reverse, persistence,
and API share `Scenario` + `FactorShock` as the stored/apply model.

TDD: new tests failed first (generators returned `MarketScenario`;
`ReverseStressResult` had no `scenario`). After pipeline conversion they
passed.

## Files changed
- `backend/app/risk/scenarios.py` — generate/apply `Scenario`; MarketScenario adapter
- `backend/app/risk/crisis_library.py` — replay path consumes `Scenario`
- `backend/app/risk/reverse_stress.py` — result carries applied `Scenario`
- `backend/app/risk/historical.py` — comment
- `backend/app/risk/scenario_model.py` — R0.4.2-G docstring
- `backend/app/domain/models.py` — `ReverseStressResult.scenario`
- `backend/tests/test_scenarios.py` — identity + canonical type pins
- `backend/tests/test_reverse_stress.py` — Scenario apply vs `achieved_loss_pct`; HTTP wire
- `reviews/FINDINGS.md` — RF-011 **CLOSED** with named residuals; R0.4.2-F APPROVE
- `reviews/REMEDIATION_MILESTONE.md` — R0.4.2-F APPROVE; R0.4.2-G
- `reviews/r0.4-architecture-brief.md` — R0.4.2-G; RF-011 CLOSED
- `reviews/r0.4.2-g-historical-reverse-scenario-report.md`
- `reviews/sdd-briefs/task-20-rf011-historical-reverse-report.md` — this handoff

## Public/interface changes
- `historical_market_scenarios` / `historical_market_scenarios_from_panel`
  return `list[Scenario]` (not `MarketScenario`).
- `iter_shocked_snapshots` applies via `apply_scenario`.
- New helpers: `scenario_from_change`, `scenario_from_panel_observation`,
  `factor_shocks_from_panel_observation`.
- `ReverseStressResult.scenario` is the applied canonical `Scenario`; JSON
  serializes as ScenarioWire. Legacy `required_shock` units unchanged.
- `MarketScenario` / `apply_market_scenario` / `market_scenario_from_*` kept
  as adapters.

## Numerical conventions
- Units: unchanged (bp↔decimal only via `shock_units`)
- Sign convention: unchanged
- Day count/calendar if relevant: n/a
- Tolerances/reference: existing goldens; historical Scenario vs MarketScenario
  adapter `content_hash` / P&L abs `1e-12`; reverse apply vs `achieved_loss_pct`
  abs `1e-4`

## Tests added/updated
- `test_historical_market_scenarios_yield_canonical_scenario_not_market_scenario`
- `test_historical_scenario_apply_matches_market_scenario_adapter_identity`
- `test_panel_historical_scenarios_yield_canonical_scenario`
- `test_reverse_result_carries_canonical_scenario_matching_achieved_loss`
- `test_reverse_zero_and_bound_paths_carry_applied_scenario`
- HTTP reverse body includes `scenario.category == reverse`
- `test_historical_scenarios_count_and_kind` reads category/metadata

## Commands executed
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_scenarios.py tests/test_scenario_model.py \
  tests/test_scenario_engine.py tests/test_reverse_stress.py \
  tests/test_canonical_scenario_store.py
```

Covering (historical VaR / crisis / panel / iterators / HTTP):

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_iter_shocked_snapshots.py tests/test_crisis_library.py \
  tests/test_factor_panel_historical.py tests/test_historical_scenario_kernel.py \
  tests/test_historical_data.py tests/test_contribution_reuse.py \
  tests/test_historical_dataset_projection.py tests/test_omit_market.py \
  tests/test_api_typed_models.py tests/test_var_methodology.py \
  tests/test_var_es_golden.py tests/test_next_phase.py \
  tests/test_demo_snapshot_adapter.py
```

## Results
- Backend brief files (no `tests/test_historical.py` in tree): **70 passed**, 1 warning
  (Starlette TestClient deprecation). No skips.
- Combined core + iterators + crisis + HTTP typed models: **116 passed**, 1 warning.
- Covering historical VaR / reverse / omit-market / demo snapshot: **65 passed**, 1 warning.
- Frontend: n/a
- QuantLib: n/a
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push)

## MET vs PARTIAL vs UNMET (this gate)

| Cell | Score |
|---|---|
| Historical pipeline yields/applies `Scenario` + `FactorShock` | **MET** |
| Aggregate expansion against live snapshot; bp via `shock_units` | **MET** |
| `MarketScenario` is adapter, not pipeline type | **MET** |
| Reverse result carries applied `Scenario`; apply matches `achieved_loss_pct` | **MET** |
| `required_shock` wire units unchanged | **MET** |
| Historical / stress / custom / reverse / persistence / API share typed model | **MET** (named adapter residuals) |
| CLOSE RF-011 | **MET** |

## Why CLOSE (not KEEP OPEN)
Historical no longer stores `MarketScenario` as the pipeline type. Reverse’s
solved answer is a canonical `Scenario`. Stress/custom/persistence/API already
shared that model after R0.4.2-E/F. Named residuals match the brief’s allowed
list.

## Known limitations / risks
- Reverse search is still one-factor-family binary search (in-scope).
- Deprecated StressScenario POST routes remain.
- `ReverseStressResult` JSON serializer uses persistence `scenario_codec`
  (layering smell, same as store codec → HTTP ScenarioWire).
- Flat dict `MarketSnapshot` storage retained (typed views wrap it).
- `ScenarioEngine.apply_scenario` still accepts `MarketScenario` / `StressScenario`
  for low-level adapters.

## Follow-up / next owner
- Owner: independent reviewer (Task 20 review)
- Requested action: APPROVE CLOSE; do not reopen for named residuals
- Blocking?: no
