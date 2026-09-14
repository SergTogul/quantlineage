# Task 13 Report — RF-011 engine-facing Scenario-only (dual-model collapse)

## Task
RF-011 engine-facing Scenario-only (R0.4.2-E dual-model collapse)

## Owner
Stress & Scenario Engineer

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-011)

## Summary
Engine-facing stress / attribution / threat now apply canonical typed
`Scenario` (`FactorShock`). Legacy `StressScenario` is adapted once at the
HTTP layer (`stresses_to_scenarios`) and again at the engine public
boundary (`to_canonical_scenario`) so internals never branch on the wire
type. Deprecated StressScenario POST routes are retained. Shock units
still convert only at the adapter via `shock_units`. Goldens /
`content_hash` / P&L identity unchanged. Demo snapshot ids unchanged.

**Disposition: IN PROGRESS** — equity-currency/rate selection is still
implicit USD default; libraries/persistence still store `StressScenario`;
historical `MarketScenario` and reverse-stress factor families are not
the stored canonical type.

TDD: new engine-boundary tests failed first (`apply_scenario` still saw
`StressScenario`; HTTP still passed legacy lists into
`PortfolioService`; `_evaluation_fields` still branched). After
canonicalization they passed.

## Files changed
- `backend/app/risk/scenario_model.py` — `to_canonical_scenario` /
  `to_canonical_scenarios`
- `backend/app/risk/stress.py` — convert once in `run` / `evaluate` /
  `contributions` / compare; `_evaluation_fields` is Scenario-only
- `backend/app/risk/scenario_attribution.py` — `_to_formal` →
  `to_canonical_scenario`; apply path typed `Scenario`
- `backend/app/api/scenario_wire.py` — `stresses_to_scenarios`
- `backend/app/api/stress.py` — deprecated + DI StressScenario routes
  adapt before the service
- `backend/tests/test_scenario_only_engine.py` — engine/HTTP boundary
  proofs
- `reviews/FINDINGS.md` — RF-011 **IN PROGRESS** with R0.4.2-E residual
- `reviews/REMEDIATION_MILESTONE.md` — R0.4.2-E
- `reviews/r0.4-architecture-brief.md` — R0.4.2-E row
- `reviews/r0.4.2-e-scenario-only-engine-report.md`
- `reviews/sdd-briefs/task-13-rf011-scenario-only-report.md` — this handoff

## Public/interface changes
- Engine public methods still *accept* `Scenario | StressScenario` at the
  door; after the first line they only handle `Scenario`.
- Deprecated HTTP POSTs now pass canonical `Scenario` into
  `PortfolioService` (behavior/P&L unchanged).
- New adapter: `to_canonical_scenario`, `stresses_to_scenarios`.
- Routes not deleted.

## Numerical conventions
- Units: unchanged (bp↔decimal only at `scenario_from_stress` /
  `scenario_to_stress` via `shock_units`)
- Sign convention: unchanged
- Day count/calendar if relevant: n/a
- Tolerances/reference: existing goldens; formal vs legacy P&L abs
  `1e-12` / `1e-9`; `content_hash` equality

## Tests added/updated
- `test_to_canonical_scenario_lifts_legacy_and_passes_formal_through`
- `test_stress_engine_run_applies_canonical_scenario_not_legacy`
- `test_stress_engine_evaluate_applies_canonical_scenario_not_legacy`
- `test_attribution_decompose_applies_canonical_scenario_not_legacy`
- `test_evaluation_fields_is_scenario_only`
- `test_legacy_and_canonical_run_share_pnl_and_content_hash`
- `test_deprecated_custom_http_adapts_legacy_before_service`
- `test_deprecated_evaluate_custom_http_adapts_legacy_before_service`

## Commands executed
TDD red (new file, before production change): 6 failed as expected
(missing `to_canonical_scenario`; `apply_scenario` still received
`StressScenario`; HTTP still passed legacy into the service;
`_evaluation_fields` still mentioned `StressScenario`). 2 already-green
pins (attribution already converted; P&L/`content_hash` identity).

Brief (required):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_scenario_engine.py tests/test_stress.py \
  tests/test_scenario_attribution.py tests/test_shock_units.py \
  tests/test_scenario_only_engine.py
```

Covering wire / omit-market / stress callers:

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_scenario_wire_api.py tests/test_omit_market.py \
  tests/test_risk.py tests/test_crisis_library.py \
  tests/test_hedge_comparison.py tests/test_stress_scenarios_di.py \
  tests/test_hierarchy_artifacts.py tests/test_scenario_model.py
```

## Results
- Backend brief + new boundary: **55 passed**, 1 warning (Starlette TestClient deprecation). No skips.
- Covering wire/omit-market/callers: **92 passed**, 1 warning. No skips.
- Frontend: n/a
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push)

## MET vs PARTIAL vs UNMET (this gate)

| Cell | Score |
|---|---|
| Engine-facing stress/attribution/threat take canonical `Scenario` | **MET** |
| Legacy HTTP `StressScenario` is adapter-only (routes kept) | **MET** |
| Shock units only at adapter via `shock_units` | **MET** |
| Goldens / `content_hash` / P&L identity unchanged | **MET** |
| Typed curves/FX from Task 12 | **MET** (prior slice) |
| Invalid FX pairs/market shapes fail validation | **MET** (Task 12) |
| Historical / stress / custom / reverse / persistence / API all store one typed model | **PARTIAL** (engine apply is Scenario; libraries/persistence/historical/reverse still dual) |
| Explicit equity-currency/rate selection | **UNMET** (implicit USD default) |
| CLOSE RF-011 | **UNMET** (required KEEP OPEN) |

## Why IN PROGRESS (not CLOSE)
Would not defend CLOSE. Residual:

1. `MarketSnapshot.rates` default remains `{"USD": 0.04}` — equity-currency/rate selection is implicit USD.
2. `DEFAULT_SCENARIOS` / `THREAT_SCENARIOS` / persistence scenario definitions still *are* `StressScenario` (adapted at the boundary).
3. Historical replay still uses `MarketScenario`; reverse stress still solves by factor family, not a stored `Scenario`.
4. Deprecated StressScenario POST routes remain (adapter, as required this slice).

## Known limitations / risks
- Conversion needs a `MarketSnapshot` (scalar StressScenario expansion is snapshot-relative). HTTP snapshots then the service snapshots again; both are deterministic per book.
- `ScenarioEngine.apply_scenario` still accepts `ScenarioInput` including `StressScenario` for `shock_snapshot` / historical helpers — that is the remaining low-level adapter, not the stress engine loop.
- RF-010 / RF-012 / RF-013 / RF-014 / RF-016 untouched.

## Follow-up / next owner
- Owner: independent reviewer (Task 13 review), then later RF-011 close-gate only if USD default and stored dual types are retired
- Requested action: KEEP OPEN; do not CLOSE RF-011
- Blocking?: no
