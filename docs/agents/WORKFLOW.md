# Multi-Agent Development Workflow

## 1. Milestone intake
The Lead Architect converts a milestone into tasks with:
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

## 5. QA validation
QA reviews the feature independently for:
- numerical correctness;
- signs/units;
- invariants;
- reconciliation;
- edge cases;
- regression risk.

## 6. Integration
Lead Architect resolves interface conflicts and runs cross-module tests.

## 7. Performance pass
Only after reference functionality is correct, C++ Performance may optimize measured bottlenecks.

## 8. UI integration
Frontend consumes stable API contracts and does no duplicate quant computation.

## 9. AI integration
AI orchestration is last: it consumes stable deterministic tools and has its own tool-selection evaluations.

## 10. Milestone close
A milestone is complete only when:
- acceptance criteria pass;
- backend tests pass;
- relevant QuantLib tests pass;
- frontend tests/build pass if affected;
- C++ compile/equivalence tests pass if affected;
- no unexpected skips;
- docs/ADR updated;
- known limitations explicitly recorded.

