# RiskForge Definition of Done

A task is not done because code was written. It is done when behavior, correctness, integration and reproducibility are demonstrated.

## All tasks
- [ ] Scope matches assigned agent ownership.
- [ ] Existing public contracts preserved or approved change documented.
- [ ] Tests added/updated for every behavior change.
- [ ] Focused tests pass.
- [ ] Affected integration tests pass.
- [ ] No unexpected skips or warnings are ignored.
- [ ] Documentation updated where behavior/architecture changed.
- [ ] Handoff report contains exact commands/results.

## Quant/pricing/risk tasks
- [ ] Units and sign conventions explicit.
- [ ] Numerical tolerance justified.
- [ ] Reference implementation, golden value, invariant or independent calculation exists.
- [ ] Edge cases tested.
- [ ] Reconciliation tested where applicable.

## Backend/API tasks
- [ ] Validation and errors tested.
- [ ] OpenAPI model/examples updated where applicable.
- [ ] No quant formula duplicated in transport layer.

## Frontend tasks
- [ ] No risk calculation duplicated client-side.
- [ ] Loading/error/empty states handled.
- [ ] Unit tests pass.
- [ ] Production build passes.
- [ ] Critical E2E path updated when relevant.

## C++ tasks
- [ ] Reference implementation retained.
- [ ] Numerical equivalence proven.
- [ ] Native compile test passes.
- [ ] Benchmark is reproducible.
- [ ] Speed claim includes workload/environment context.

## AI tasks
- [ ] All numerical values originate from deterministic tools.
- [ ] Tool-selection evaluations pass.
- [ ] Missing/ambiguous inputs handled explicitly.
- [ ] No hallucinated risk values.

