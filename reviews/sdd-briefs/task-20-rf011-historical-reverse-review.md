# Task 20 Review — RF-011 historical + reverse canonical Scenario

**Base:** `6331115`  
**Head:** `a6a579e`

### Spec Compliance

- ✅ Spec compliant

Historical generation/apply yield and apply canonical `Scenario` + `FactorShock`. Reverse-stress `ReverseStressResult` carries the applied `Scenario`. `MarketScenario` remains an adapter. CLOSE is honest against FINDINGS acceptance.

### Strengths

Pipeline conversion is real: generators return `Scenario`; iterators call `apply_scenario`. Reverse attaches the same `build_reverse_scenario` used during search.

### Issues

#### Critical / Important
None.

#### Minor
1. `ReverseStressResult.scenario` is `Any`; serialize via persistence `scenario_codec`.
2. `POST /risk/stress/reverse/multi` still returns family-scalar solutions (not this brief’s pipeline dual).
3. New identity test compares apply vs adapter that now also goes through `apply_scenario`.
4. TDD red phase claimed in the report only.
5. FINDINGS was stamped CLOSED on the implementing commit; controller owns the stamp after this review.

### Assessment

**Task quality:** Approved

**Lead disposition:** RF-011 **CLOSED**. Named residuals: deprecated StressScenario HTTP POSTs; `MarketScenario` adapter; reverse search remains one-factor-family; flat dict MarketSnapshot storage.
