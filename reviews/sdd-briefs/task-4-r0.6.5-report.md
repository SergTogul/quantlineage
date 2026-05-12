# Task 4 Report — R0.6.5 Process-level scenario parallelism

## Task

R0.6.5 — Process-level scenario parallelism (bounded). Option B: document RiskRun / Compose worker as the process partition and add HEAVY proof tests. Do not add unused multiprocessing. Do not close RF-007.

## Owner

Backend / API Engineer.

## Summary

Chose **option B**. HEAVY `FULL_REVALUATION` already runs out of the request thread via RiskRun (`RF-015` CLOSED; `RISKFORGE_EXTERNAL_WORKER` / `run_type` paths). Proof tests pin that summary/var are HEAVY and refuse inline when the gate is on (`details.use=/risk/runs`), that RiskRun stays `QUEUED` in the API process, and that R0.6.1 `pnl_checksum` `6602fa69…` is identity evidence (`wall_ms` recorded, not an SLA). No chunked `ProcessPoolExecutor`. RF-007 remains `IN PROGRESS`.

## Files Changed

- `backend/tests/test_r065_process_partition.py`
- `backend/app/services/risk_run_worker.py`
- `docs/adr/007-quantlib-concurrency.md`
- `docs/adr/README.md`
- `docs/known_limitations.md`
- `reviews/FINDINGS.md`
- `reviews/REMEDIATION_MILESTONE.md`
- `reviews/r0.6.5-process-parallelism-report.md`
- `reviews/sdd-briefs/task-4-r0.6.5-report.md`

## Public / Interface Changes

- None. No new env flag, DTO, or multiprocessing API.
- Existing gate (`RISKFORGE_EXTERNAL_WORKER` / `RISKFORGE_HEAVY_INLINE`) and RiskRun `run_type=summary|var` remain the partition.

## Numerical Conventions

- Units: unchanged.
- Sign convention: unchanged.
- Day count/calendar: n/a.
- Tolerances/reference: R0.6.1 identity checksum `6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f` (`n_obs=120`, builtin); no wall-time SLA.

## Tests Added / Updated

- Added `test_full_revaluation_summary_and_var_are_heavy`.
- Added `test_full_revaluation_summary_and_var_refused_when_external_worker`.
- Added `test_full_revaluation_summary_and_var_refused_when_heavy_inline_disabled`.
- Added `test_full_revaluation_risk_run_stays_queued_when_external_worker`.
- Added `test_full_revaluation_execute_run_type_still_computes`.
- Added `test_r061_checksum_is_identity_scaling_evidence_not_sla`.
- Added `test_full_revaluation_pnl_series_has_no_process_or_thread_pool`.
- Added `test_full_reval_modules_do_not_start_unused_multiprocessing`.
- Added `test_worker_does_not_defer_unused_process_pool_to_r065`.
- Added `test_compose_worker_is_the_full_reval_process_partition`.

## Commands Executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_r065_process_partition.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_full_reval_bench.py \
  tests/test_backpressure.py \
  tests/test_endpoint_execution_class.py \
  tests/test_risk_run_api.py \
  tests/test_r065_process_partition.py \
  tests/test_quantlib_process_parallelism.py
.venv/bin/python -m ruff check tests/test_r065_process_partition.py app/services/risk_run_worker.py
cd /Users/user/src/riskforge-mvp && /usr/bin/git diff --check
```

## Results

- New partition tests before docstring update: 3 failed (`R0.6.5 may add` leftover; checksum assertion too strict vs bench “does not invoke SLA” wording; `ProcessPoolExecutor` mentioned in worker docstring).
- New partition tests after implementation: `17 passed`.
- Brief focused suite plus new partition tests plus R0.3.5 process-parallelism pins: **94 passed**, 1 pre-existing Starlette `TestClient` deprecation warning.
- Ruff on new tests + `risk_run_worker.py`: passed (import order auto-fixed).
- `git diff --check`: passed.
- CI green: not started from this subtask; local focused verification above.

## Known Limitations / Risks

- RF-007 is not closed. Joint N×S full-reval pricing and N=100/1k benches remain.
- Option A (chunked scenario multiprocessing with exact P&L identity) was not implemented; scale-out stays Compose worker replicas.
- Gate-off local uvicorn still schedules RiskRuns on an in-process job `ThreadPoolExecutor`; QuantLib stays lock-serialized.
- No FULL_REVALUATION SLA was invented.

## Follow-Up / Handoff

- Owner: Lead Architect / QA for RF-007 close gate (Task 5).
- Requested action: independent review of R0.6.5; keep RF-007 open.
- Blocking: no for this slice.
