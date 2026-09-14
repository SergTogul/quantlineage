# Task 26 Report — RF-016 close gate (accepted labeled-runner residual)

## Task
RF-016 close gate with accepted labeled-runner residual (R0.12.7)

## Owner
QA & Quant Validation Engineer (`docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`)

## Status
**CLOSED** pending independent review APPROVE. Disposition: **CLOSE**. No labeled runner; SLA-K1/K2 not CI-enforced; QA-024 demo-artifact range leftover. Those are accepted residuals (not MET). QuantLib cannot be skipped in PR-FULL.

## Summary
Independent re-score of RF-016 against FINDINGS PR-FAST / PR-FULL / NIGHTLY required direction, with file:evidence. R0.12.1–R0.12.6 APPROVE were re-checked on disk and with a focused CI-contract suite, not rubber-stamped. PR-FAST, PR-FULL QuantLib hard-gate, native compile-parity, frontend, semantic API, Playwright, NIGHTLY Postgres two-worker, larger full-reval, and QuantLib E2E are **MET**. Labeled-runner SLA-K1/K2 remains **PARTIAL** and is recorded as an **accepted residual** — not called MET. QA-024 demo-artifact range has no real CI check and is named leftover (not faked). Existing pins kept (`test_ubuntu_latest_jobs_do_not_run_check_m6_sla`). TDD close-gate residual pins failed first, then FINDINGS / milestone text landed. No SLA floors added. No pricing/risk numbers changed.

## Files changed
- `backend/tests/test_rf016_close_gate.py` — FINDINGS CLOSED + R0.12.7 residual pins (TDD: failed first)
- `reviews/FINDINGS.md` — RF-016 **CLOSED**; residuals named not MET
- `reviews/REMEDIATION_MILESTONE.md` — R0.12.7 close-gate record
- `BUILD_NOTES.md` — CLOSE + accepted residual note
- `docs/performance.md` — CLOSE note; PARTIAL marker retained
- `reviews/r0.12.7-rf016-close-gate-report.md` — scoring report
- `reviews/sdd-briefs/task-26-rf016-close-gate-report.md` — this handoff

## Public/interface changes
- None. No workflow job added. No pricing/risk/API change.

## Numerical conventions
- Units: n/a (CI contract close gate). SLA-K1/K2 floors remain those already in `check_m6_sla.py` (serial ≥50× vs python; t4 ≥1.3× vs serial `cpp_ctypes` on `10k_x_1k`). Those floors are reference-host, not `ubuntu-latest` CI gates.
- Sign convention: n/a
- Day count/calendar if relevant: n/a
- Tolerances/reference: n/a

## Tests added/updated
- `test_findings_rf016_closed_with_named_accepted_residuals` — FINDINGS RF-016 is CLOSED; labeled-runner SLA and QA-024 named not MET
- `test_milestone_r0127_records_accepted_labeled_runner_residual` — R0.12.7 records no labeled runner / SLA not CI-enforced / QA-024
- Existing: `test_ubuntu_latest_jobs_do_not_run_check_m6_sla`, `test_labeled_sla_job_is_absent_honest_residual`, PR-FAST / PR-FULL QuantLib hard-gate pins

TDD: residual-marker tests failed first (2 failed, 30 passed). After docs, full required suite GREEN (see Results).

## Commands executed
```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_pr_full_ci.py tests/test_pr_fast_ci.py tests/test_nightly_ci.py \
  tests/test_rf016_close_gate.py
# RED: 2 failed, 30 passed (FINDINGS still IN PROGRESS; no R0.12.7)

PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_pr_full_ci.py tests/test_pr_fast_ci.py tests/test_nightly_ci.py \
  tests/test_rf016_close_gate.py
# GREEN: 32 passed in 3.51s

.venv/bin/ruff check tests/test_rf016_close_gate.py
# All checks passed
```

## Results
- Backend required suite: **32 passed** in 3.51s. Ruff: all checks passed.
- Frontend: n/a
- QuantLib: not exercised numerically. Hard-gate job and `QUANTLINEAGE_REQUIRE_QUANTLIB` left intact.
- C++: n/a this slice (native compile remains inside `backend-pytest`; SLA-K1/K2 not CI-enforced)
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## MET vs PARTIAL vs UNMET (this gate)

| Cell | Score | Evidence |
|---|---|---|
| PR-FAST | **MET** | `pr-fast` goldens + frontend unit/lint; `test_pr_fast_ci.py` |
| PR-FULL QuantLib hard-gate | **MET** | `backend-quantlib` required by `pr-full`; no skip-green |
| PR-FULL native / frontend / semantic API / Playwright | **MET** | `backend`, `frontend`, full pytest API tests, `e2e-playwright` |
| NIGHTLY Postgres two-worker | **MET** | `postgres-two-worker`; fail-closed DSN |
| NIGHTLY larger full-reval | **MET** | sample + N=100 identity |
| NIGHTLY QuantLib E2E | **MET** | `quantlib-e2e` nightly only |
| Labeled-runner SLA-K1/K2 | **PARTIAL** / accepted residual | harness + docs; `total_count=0`; no ubuntu-latest SLA job |
| QA-024 demo-artifact range | **UNMET** leftover | no QL range gate vs `data/demo_risk_artifact.json` |

## Why CLOSE (not KEEP OPEN)
QuantLib cannot be skipped in PR-FULL (`backend-quantlib-hard-gate` is a required need; `QUANTLINEAGE_REQUIRE_QUANTLIB`; no `requirements-no-ql`). KEEP OPEN would be required if that hole remained. Labeled-runner SLA-K1/K2 is still unimplemented in CI; calling it MET would be a rubber-stamp. It is an accepted R0 residual because Milestone R0 is a GitHub-hosted verification matrix, not a self-hosted SLA farm. QA-024 range is named leftover, not MET. Same standard as RF-014 ACLs/TLS.

## Known limitations / risks
- No self-hosted labeled runner; SLA-K1/K2 not a CI gate
- Do not add `check_m6_sla.py` on `ubuntu-latest`
- QA-024 QuantLib demo-artifact range still absent
- `workflow_dispatch` is a trigger, not a runner label
- `backend-pytest` may still omit QuantLib; PR-FULL does not
- GitHub Actions was not executed from this host

## Follow-up / next owner
- Owner: independent reviewer (Task 26 review)
- Requested action: APPROVE CLOSE or KEEP OPEN; do not treat CLOSED as final until that review; do not add Nightly to branch-protection required checks; do not add nightly jobs to PR-FULL `needs:`
- Blocking?: no
