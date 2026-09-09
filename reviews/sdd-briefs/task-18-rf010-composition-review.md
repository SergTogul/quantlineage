# Task 18 Review — RF-010 composition (after fail-closed + TestClient lifespan)

**Base:** `a6821eb`  
**Head:** `fa75ca8`

### Spec Compliance

- ✅ Spec compliant after honesty fix + TestClient lifespan callers

HTTP `get_portfolio_service` 503s when `app.state` is missing. Leftover `TestClient(app)` callers use lifespan. Four acceptance cells MET.

### Issues

#### Critical / Important
None after the TestClient follow-up.

### Assessment

**Task quality:** Approved

**Lead disposition:** RF-010 **CLOSED**. Dual-use `AttributionRequest` / `WhatIfRequest` / `RiskChangeAttributionRequest` are a named residual, not KEEP OPEN.
