# Task 19 Report — RF-011 libraries + persistence store canonical Scenario

## Task
RF-011 libraries + persistence store canonical Scenario (R0.4.2-F)

## Owner
Stress & Scenario Engineer (`docs/agents/05_STRESS_SCENARIO_ENGINEER.md`)
with Backend for repository/DI.

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-011)

## Summary
In-code DEFAULT / THREAT libraries are `BroadcastScenarioDefinition`
templates (not `StressScenario`) expanded at apply time against the live
`MarketSnapshot`, following `CrisisDefinition` + `crisis_scenarios(base)`.
`ScenarioDefinitionRepository` save/get/`list_all` persist canonical
`Scenario` as ScenarioWire JSON. HTTP DI returns `Scenario`. Deprecated
StressScenario POST routes still convert once at the route. Shock units
still convert only at the adapter via `shock_units`. Goldens /
`content_hash` / P&L identity unchanged. Demo snapshot ids unchanged.

**Disposition: IN PROGRESS** — historical `MarketScenario` and reverse-stress
factor-family solvers remain a different stored type.

TDD: new store tests failed first (libraries were `StressScenario`; repos
called `model_copy` on `Scenario`; seed returned `StressScenario`; DI
annotations were `list[StressScenario]`). After templates + canonical
repos they passed.

## Files changed
- `backend/app/risk/scenario_model.py` — `BroadcastScenarioDefinition`,
  `expand_broadcast_definition`, template-aware `to_canonical_scenario`
- `backend/app/risk/crisis_library.py` — `crisis_as_broadcast`
- `backend/app/risk/stress.py` — DEFAULT/THREAT templates;
  `default_scenarios` / `threat_scenarios`
- `backend/app/risk/scenario_attribution.py` — `ScenarioLike` includes
  templates
- `backend/app/risk/hierarchy.py` — expand templates before apply
- `backend/app/risk/incremental_var.py` — `ScenarioLike` scenarios arg
- `backend/app/persistence/repositories.py` — repo ABC is `Scenario`
- `backend/app/persistence/memory_repos.py` — store `Scenario`
- `backend/app/persistence/sqlalchemy_repos.py` — ScenarioWire JSON
- `backend/app/persistence/scenario_codec.py` — wire dump/load
- `backend/app/persistence/wiring.py` — seed expanded `Scenario`
- `backend/app/api/deps.py` — DI returns `list[Scenario]`
- `backend/app/api/stress.py` — DI paths pass `Scenario` through
- `backend/app/api/dashboard.py` — DI types
- `backend/tests/test_canonical_scenario_store.py` — new pins
- `backend/tests/test_persistence.py` / `test_stress_scenarios_di.py`
- `reviews/FINDINGS.md` — RF-011 **IN PROGRESS** with R0.4.2-F residual
- `reviews/REMEDIATION_MILESTONE.md` — R0.4.2-F
- `reviews/r0.4-architecture-brief.md` — R0.4.2-F row
- `reviews/r0.4.2-f-canonical-scenario-store-report.md`
- `reviews/sdd-briefs/task-19-rf011-canonical-store-report.md` — this handoff

## Public/interface changes
- `DEFAULT_SCENARIOS` / `THREAT_SCENARIOS` are broadcast templates
  (`BroadcastScenarioDefinition`), not `StressScenario`.
- `ScenarioDefinitionRepository` save/get/`list_all` use `Scenario`.
- HTTP DI returns `list[Scenario]`. Deprecated POST bodies still
  `StressScenario` and convert at the route.
- New helpers: `default_scenarios(base)`, `threat_scenarios(base)`,
  `crisis_as_broadcast`, `expand_broadcast_definition`.
- Routes not deleted.

## Numerical conventions
- Units: unchanged (bp↔decimal only at expand/collapse via `shock_units`)
- Sign convention: unchanged
- Day count/calendar if relevant: n/a
- Tolerances/reference: existing goldens; formal vs legacy P&L abs
  `1e-12`; `content_hash` equality on the same snapshot

## Tests added/updated
- `test_default_library_ids_unchanged`
- `test_default_and_threat_libraries_are_not_stress_scenario`
- `test_eq_down_broadcast_expands_onto_live_snapshot_names`
- `test_default_expansion_matches_legacy_stress_content_hash_and_pnl`
- `test_threat_templates_expand_like_crisis_scenarios`
- `test_memory_repo_round_trips_scenario`
- `test_sqlalchemy_repo_round_trips_scenario_wire_payload`
- `test_default_seed_scenarios_are_canonical_scenario`
- `test_http_di_returns_scenario_not_stress_scenario`
- `test_http_list_and_stress_identity_with_lifespan`
- Persistence / DI tests save `Scenario` instead of `StressScenario`

## Commands executed
TDD red (new file, before production change): 5 failed as expected
(libraries were `StressScenario`; repos lacked `Scenario` save;
seed returned `StressScenario`; DI return type was
`list[StressScenario]`). 5 already-green pins (ids, broadcast via
legacy expand, P&L/`content_hash` identity, HTTP list).

Brief (required):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_stress.py tests/test_stress_scenarios_di.py \
  tests/test_scenario_only_engine.py tests/test_scenario_wire_api.py \
  tests/test_persistence.py
```

Plus new library/repo pins and covering callers:

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_canonical_scenario_store.py tests/test_crisis_library.py \
  tests/test_scenario_model.py tests/test_omit_market.py \
  tests/test_hierarchy_artifacts.py tests/test_persistence_di.py \
  tests/test_scenario_attribution.py tests/test_risk.py \
  tests/test_hedge_comparison.py \
  tests/test_portfolio_hierarchy_artifacts.py \
  tests/test_scenario_engine.py tests/test_demo_portfolios.py \
  tests/test_hierarchy.py
```

## Results
- Backend brief + new store pins: **58 passed**, 1 warning (Starlette TestClient deprecation). No skips.
- Covering crisis/model/omit/hierarchy/persistence-di: **127 passed**, 1 warning. No skips.
- Covering attribution/risk/hedge/hierarchy/engine/demo: **69 passed**, 1 warning. No skips.
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
| DEFAULT/THREAT libraries are not stored `StressScenario` | **MET** (broadcast templates) |
| Templates expand at apply time against live snapshot | **MET** |
| `ScenarioDefinitionRepository` persists `Scenario` | **MET** |
| HTTP DI returns `Scenario` (deprecated POST adapters kept) | **MET** |
| DEFAULT ids unchanged; goldens / P&L / `content_hash` identity | **MET** |
| Historical / stress / custom / reverse / persistence / API all store one typed model | **PARTIAL** (stress/custom/persistence/API store `Scenario`; historical `MarketScenario` and reverse-stress remain dual) |
| CLOSE RF-011 | **UNMET** (required KEEP OPEN) |

## Why IN PROGRESS (not CLOSE)
Would not defend CLOSE. Residual:

1. Historical replay still uses `MarketScenario` (`app.risk.scenarios`), not the stored canonical `Scenario`.
2. Reverse-stress solvers still search factor-family shocks, not a stored `Scenario`.
3. Deprecated StressScenario POST routes remain (adapter, as required this slice).
4. Seeded persistence expands templates against the demo snapshot; in-code libraries still re-expand at apply time for engine callers.

## Known limitations / risks
- Persistence codec serializes via HTTP `ScenarioWire` (`app.persistence.scenario_codec`). JSON shape matches the list wire.
- HTTP DI fallback expands templates against the default market snapshot, not an arbitrary request portfolio's marks. Engine callers that pass templates still expand against the live book snapshot.
- `ScenarioEngine.apply_scenario` still accepts `ScenarioInput` including `StressScenario` for low-level adapters.
- RF-012 / RF-013 / RF-016 untouched.

## Follow-up / next owner
- Owner: independent reviewer (Task 19 review), then later RF-011 close-gate only if historical `MarketScenario` and reverse-stress converge on stored `Scenario`
- Requested action: KEEP OPEN; do not CLOSE RF-011
- Blocking?: no
