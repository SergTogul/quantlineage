# Task 10 Report — RF-016 labeled-runner SLA-K1/K2 (honest residual)

## Task
RF-016 labeled-runner SLA-K1/K2 honest close or residual

## Owner
QA & Quant Validation Engineer

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-016)

## Summary
No labeled/self-hosted runner is configured in this repo (`gh api repos/SergTogul/quantlineage/actions/runners` → `total_count=0`). This slice does **not** add `benchmarks/check_m6_sla.py` on `ubuntu-latest` and does **not** invent host SLA floors. SLA-K1/K2 is **PARTIAL**: harness + `docs/performance.md` + `benchmarks/RESULTS.md` exist; CI does not enforce host floors. Pytest pins the residual (TDD: residual markers failed first). PR-FAST, QuantLib hard-gate, and `postgres-persistence-smoke` are unchanged. FINDINGS RF-016 stays **IN PROGRESS**.

## Files changed
- `backend/tests/test_nightly_ci.py`
- `backend/tests/test_pr_full_ci.py`
- `.github/workflows/nightly.yml` (header residual only; no new job)
- `docs/performance.md`
- `BUILD_NOTES.md`
- `reviews/FINDINGS.md`
- `reviews/REMEDIATION_MILESTONE.md`
- `reviews/r0.12.6-rf016-sla-k-report.md`
- `reviews/sdd-briefs/task-10-rf016-sla-report.md`

## Public/interface changes
- None

## Numerical conventions
- Units: unchanged. SLA-K1 ≥50× / SLA-K2 ≥1.3× remain reference-host floors in `check_m6_sla.py`, not CI gates on `ubuntu-latest`.
- Sign convention: n/a
- Day count/calendar if relevant: n/a
- Tolerances/reference: `benchmarks/RESULTS.md`

## Tests added/updated
- `test_ubuntu_latest_jobs_do_not_run_check_m6_sla`
- `test_labeled_sla_job_is_absent_honest_residual`
- `test_sla_k_harness_exists_with_documented_floors`
- `test_sla_k_docs_exist_and_do_not_claim_ubuntu_ci_floors`
- `test_pr_full_needs_does_not_include_sla_k`
- PR-FULL extra pin: no SLA in `needs:`; `ci.yml` does not name `check_m6_sla.py`

## Commands executed
```bash
gh api repos/SergTogul/quantlineage/actions/runners

cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_nightly_ci.py tests/test_pr_full_ci.py tests/test_pr_fast_ci.py

.venv/bin/ruff check tests/test_nightly_ci.py tests/test_pr_full_ci.py
```

## Results
- Backend required suite: **30 passed** in 2.68s
- Ruff: all checks passed
- Frontend: n/a
- QuantLib: n/a (hard-gate not weakened)
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## MET vs PARTIAL vs UNMET (this gate)

Harness + docs **MET**. Labeled-runner CI enforcement **UNMET** (`total_count=0`). Overall leftover **PARTIAL**. PR-FAST / QuantLib hard-gate / postgres-smoke **unchanged**.

Required NIGHTLY “benchmark/SLA on labeled runner” is **PARTIAL**, not MET. QA-024 demo-artifact range is still a leftover (out of this slice).

## Why IN PROGRESS (not CLOSE)
No labeled runner. Did not fake ubuntu-latest floors. Remaining required direction is not honestly MET. Would not defend CLOSE.

## Known limitations / risks
- SLA-K1/K2 is not CI-enforced until a labeled runner exists
- `workflow_dispatch` ≠ runner label
- QA-024 demo range leftover remains

## Follow-up / next owner
- Owner: Lead Architect / DevOps (register labeled runner) then QA (pin the job)
- Requested action: KEEP OPEN; do not CLOSE RF-016
- Blocking?: no
