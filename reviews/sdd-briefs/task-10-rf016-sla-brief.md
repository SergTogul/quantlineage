# Task 10 Brief — RF-016 labeled-runner SLA-K1/K2 (honest close or residual)

**Owner:** QA & Quant Validation (`docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`) + DevOps as needed.  
**Finding:** RF-016  
**BASE:** `9ddb8df`

## Why this exists

RF-016 remaining line: labeled-runner SLA-K1/K2. Nightly already exists (`nightly.yml`) and **must not** run `benchmarks/check_m6_sla.py` on `ubuntu-latest` (host-specific floors flake — already documented in that workflow). PR-FAST/FULL/QuantLib hard-gate/E2E/hierarchy identity already APPROVE in R0.12.x.

## Required

1. Make the SLA-K1/K2 path real **or** score it honestly:
   - If a labeled/self-hosted runner path can run `benchmarks/check_m6_sla.py` without inventing a fake floor on GitHub `ubuntu-latest`, add it (workflow_dispatch / runner label). Pin the contract in `backend/tests/test_nightly_ci.py` the same way other nightly jobs are pinned: job exists, not in PR-FULL `needs:`, no `continue-on-error`.
   - If no labeled runner exists in this repo, **do not** add a flake-prone ubuntu SLA job. Document the leftover as **PARTIAL** (harness + `docs/performance.md` + `benchmarks/RESULTS.md` exist; CI does not enforce host floors) and **do not CLOSE** unless remaining FINDINGS required direction is otherwise MET and Lead later accepts the SLA leftover in writing.
2. Update FINDINGS RF-016 residual honestly. Do not rubber-stamp CLOSED if SLA-K1/K2 is still UNMET and you did not add a non-flaky labeled job.
3. Do not weaken PR-FAST, QuantLib hard-gate, or postgres-persistence-smoke.
4. Write `reviews/r0.12.6-rf016-sla-k-report.md`.
5. **Commit**. TDD for any new pytest contract pins.

## Out of scope
- Expanding C++ kernels
- Inventing wall-time floors on ubuntu-latest
- Closing RF-013 / RF-010 / RF-011 / RF-012 / RF-014

## Tests
```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_nightly_ci.py tests/test_pr_full_ci.py tests/test_pr_fast_ci.py
```

## Report
`reviews/sdd-briefs/task-10-rf016-sla-report.md`
