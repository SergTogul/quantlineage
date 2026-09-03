# Multi-Agent Development Workflow

## 1. Workstream intake
The Lead Architect converts a workstream into tasks with:
- owner;
- dependencies;
- files/modules likely affected;
- interface changes;
- acceptance criteria;
- required tests.

## 2. Contract first
If multiple agents depend on a new concept, define the contract before parallel implementation.

Examples:
- `RiskFactor` before risk buckets and factor-level scenario shocks;
- `MarketSnapshot` curve/surface representation before key-rate DV01 and vol buckets;
- scenario schema before API and UI scenario builder;
- risk-service DTOs before AI tool schemas.

## 3. Specialist implementation
Each agent changes only its ownership area. Cross-area needs become handoffs.

## 4. Test during development
For every behavior change:
1. add or update a failing test;
2. implement;
3. run focused tests;
4. run affected integration tests;
5. record exact results.

## 5. Handoff gate
The handoff condition is **all tests pass**: a handoff is ready only when all applicable/affected test suites required by the task pass. Record the exact commands and results, and explain any failure or skip; an unexplained failure or skip blocks handoff.

## 6. Push and CI gate
The push condition is **CI is green**. Run all applicable local checks before the initial branch push. That initial push is permitted when needed to trigger CI, but the push/handoff is not complete and integration must not continue until all required CI checks are green. If CI fails, fix the issue, rerun the applicable local checks, push the fix, and verify that required CI is green.

## 7. QA validation
QA reviews the feature independently for:
- numerical correctness;
- signs/units;
- invariants;
- reconciliation;
- edge cases;
- regression risk.

## 8. Integration
Lead Architect resolves interface conflicts and runs cross-module tests.

## 9. Performance pass
Only after reference functionality is correct, C++ Performance may optimize measured bottlenecks.

## 10. UI integration
Frontend consumes stable API contracts and does no duplicate quant computation.

## 11. AI integration
AI orchestration is last: it consumes stable deterministic tools and has its own tool-selection evaluations.

## 12. Workstream close
A workstream is complete only when:
- acceptance criteria pass;
- backend tests pass;
- relevant QuantLib tests pass;
- frontend tests/build pass if affected;
- C++ compile/equivalence tests pass if affected;
- no unexpected skips;
- required CI checks are green;
- docs/ADR updated;
- known limitations explicitly recorded.

