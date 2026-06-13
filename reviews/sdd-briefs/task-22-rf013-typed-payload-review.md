# Task 22 Review — RF-013 typed risk_results.payload

**Base:** `9615d57`  
**Head:** `ff4eadc`

### Spec Compliance

- ✅ Spec compliant

Per-`result_type` schema gate with `extra='forbid'`. Unknown type and extra keys fail closed at `add_result` / `complete`. Physical JSON column remains. Cell 4 **MET**. RF-013 stays **IN PROGRESS**.

### Strengths

Reuses existing result models. Write gate is on the persistence path. Honest KEEP OPEN.

### Issues

#### Critical / Important
None.

#### Minor
1. Nested extra-key reject untested (top-level extras only).
2. `test_execute_run_type_payload_validates` covers 5 of 18 run types.
3. `_reject_unknown_keys` silent path when dumped is not a mapping.
4. `DashboardResultPayload` duplicates `DashboardBatchResponse`.
5. `RiskQueryResponse.data` remains an untyped dict (existing envelope).

### Assessment

**Task quality:** Approved

**Lead disposition:** RF-013 **KEEP OPEN**. Cell 4 **MET**. Residuals: `portfolio_version` / server-issued ids; live calculate still POSTs a full book; leftover `save` upsert; object ACLs = RF-014.
