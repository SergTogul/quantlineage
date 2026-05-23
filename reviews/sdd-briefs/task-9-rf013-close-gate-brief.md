# Task 9 Brief — RF-013 canonical identity close (or remaining HTTP pin)

**Owner:** Backend/API Engineer (`docs/agents/07_BACKEND_API_ENGINEER.md`) with QA close-gate honesty.  
**Finding:** RF-013  
**BASE:** current HEAD after RF-007 CLOSED (`98af558` plus any controller docs commit).

## Why this exists

R0.8.3 already: create fails if id exists; update fails if missing; RiskRun submit create-if-absent / attach stored book (no upsert). Tests in `backend/tests/test_portfolio_identity.py`. Finding still has no Status line. Milestone still lists RF-013 open.

## Required

1. Prove FINDINGS acceptance:
   - a request cannot overwrite `global-macro` merely by supplying that ID (HTTP and/or RiskRun submit against the seeded demo id — pin the stored Cross-Asset book is unchanged);
   - a persisted risk run can be reproduced from IDs (point at existing same-spec tests or add a pin);
   - PostgreSQL path has real pytest/integration coverage (R0.8.5 — cite, do not duplicate unless missing);
   - large derived payloads are not blindly duplicated as unconstrained JSON (R0.8.4 typed requests — cite).
2. If any cell is UNMET, implement the smallest pin (prefer extending `test_portfolio_identity.py` / API tests). Do not invent a new persistence stack.
3. If all cells MET after this slice + independent review, status **CLOSED**. If not, keep IN PROGRESS with an honest residual list.
4. Update FINDINGS + `reviews/REMEDIATION_MILESTONE.md`. Write `reviews/r0.8.6-rf013-close-gate-report.md`.
5. **Commit** (`test(r0.8): ...` and/or `docs(r0.8): ...`). Follow TDD if you add tests.

## Out of scope
- RF-010 domain/API split
- Object ACLs / IAM (RF-014)
- C++ / QuantLib

## Tests
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_portfolio_identity.py tests/test_same_spec_parity.py
```

## Report
`reviews/sdd-briefs/task-9-rf013-close-gate-report.md`
