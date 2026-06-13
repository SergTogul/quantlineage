# Task 23 Review — RF-013 portfolio_version

**Base:** `ff4eadc`  
**Head:** `de6c1cd`

### Spec Compliance

- ✅ Spec compliant

Server-owned `Portfolio.version` (create=1). `update` compare-and-swap. `RiskRun.portfolio_version` stamped from the stored book at submit. Alembic `004_portfolio_version`. CLOSE is honest against the brief’s named residuals.

### Strengths

Version is stored, returned, checked on `update`, and copied onto the run header with SQL pins. Not Task 9’s rubber-stamp.

### Issues

#### Critical / Important
None.

#### Minor
1. Optimistic lock is check-then-write, not `UPDATE … WHERE version = :expected`.
2. FINDINGS index still described an open finding (controller stamp should fix).
3. OpenAPI queued-run example omits `portfolio_version`.
4. Postgres lifecycle pin is the view, not SQL.

### Assessment

**Task quality:** Approved

**Lead disposition:** RF-013 **CLOSED**. Named residuals: leftover seed `save`; live debug calculate POST; RF-014 ACLs; client id on first create. Not a revision archive.
