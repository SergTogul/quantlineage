# Task 19 Review — RF-011 canonical Scenario store

**Base:** `b2cd138`  
**Head:** `6331115`

### Spec Compliance

- ✅ Spec compliant

DEFAULT/THREAT are apply-time `BroadcastScenarioDefinition` templates, not `StressScenario`. Repos persist canonical `Scenario` as ScenarioWire JSON. HTTP DI returns `Scenario`. FINDINGS keep RF-011 **IN PROGRESS**.

- ⚠️ TDD red phase is claimed in the report only; not visible in this commit.
- ⚠️ HTTP `POST /risk/stress` consumes already-expanded named shocks (seed/default snapshot), not re-expand against the request book. Engine callers that pass templates still expand at apply.
- ⚠️ Historical `MarketScenario` (`backend/app/risk/scenarios.py`) and `ReverseStressEngine` (`backend/app/risk/reverse_stress.py`) remain dual — KEEP OPEN.

### Strengths

Template vs stored `Scenario` split matches `CrisisDefinition` + `crisis_scenarios(base)`. Expand path is one helper; identity pin compares `content_hash` and P&L. Residual honesty is correct.

### Issues

#### Critical / Important
None.

#### Minor
1. Leftover SQLAlchemy `definition` blobs in StressScenario shape fail closed; seed uses `get()` as existence (`scenario_codec.py`, `sqlalchemy_repos.py`, `wiring.py`).
2. Persistence codec imports HTTP `ScenarioWire` — layering smell, no cycle.
3. `test_http_di_returns_scenario_not_stress_scenario` only asserts annotations (runtime covered elsewhere).
4. Pre-existing Starlette TestClient deprecation warning.

### Assessment

**Task quality:** Approved

**Lead disposition:** RF-011 **KEEP OPEN**. CLOSE would be dishonest: historical replay still uses `MarketScenario`; reverse-stress still searches factor-family shocks; deprecated StressScenario POST routes remain (intentional this slice).
