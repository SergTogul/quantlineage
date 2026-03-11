# ADR 007: QuantLib concurrency — RLock, process isolation, native kernels

- Status: Accepted (codifies existing adapter + worker design; closes ROADMAP )
- Date: 2026-09-02
- Owners: Lead Architect; C++ Performance Engineer; Quant Pricing Engineer

## Context

QuantLib keeps process-global settings (notably `Settings.instance.evaluationDate`).
RiskForge prices through `QuantLibPricingEngine` (`backend/app/pricing/quantlib.py`).
Risk-run execution today uses an in-process `ThreadPoolExecutor`
(`backend/app/services/risk_run_worker.py`), so concurrent Python threads may
call into the same adapter.

Separately, Workstream 6 ships an optional C++ scenario aggregation kernel
(`backend/native/`, `NativeScenarioKernel`) for LINEAR / DELTA_GAMMA approximate
P&L. That kernel is pure numerical Δ-Γ math on flat Exposure/Shock buffers; it
does **not** call QuantLib.

Evidence already in code:

- Adapter docstring and `threading.RLock` around `_session` (sets / restores
 evaluation date for each pricing call).
- Worker docstring: thread pool, not a distributed queue; Compose “worker” is a
 separate **process** polling Postgres , not threaded QL reval.
- Native README / FULL_REVALUATION stays on `PricingEngine`; native kernel
 cannot accelerate full revaluation.

## Decision

1. **Serialize QuantLib use inside one process via `_QL_PROCESS_LOCK`.**
 `QuantLibPricingEngine` binds every instance to the module-level
 `_QL_PROCESS_LOCK` and wraps every valuation path that touches QuantLib
 settings (and related construction) in `_session`. Valuation cache keys
 include parseable snapshot as-of so ISO evaluation dates cannot share a
 cached PV. Callers (risk engines, services, workers) must not manipulate
 `ql.Settings` themselves. Parallel full revaluation is process-partitioned
 (R0.3.5): Compose ``worker`` / ``python -m app.worker``, not an in-process
 QuantLib thread pool.

2. **Prefer process isolation for parallel QuantLib revaluation.**
 For high-throughput FULL_REVALUATION / multi-run pricing, scale with
 **multiple processes** (Compose worker replicas, future process pool / job
 queue), each with its own QuantLib globals — not by removing the RLock and
 racing threads against `Settings`. Thread-pool concurrency inside one
 process remains correct but becomes a serial bottleneck under the lock;
 that is acceptable for MVP throughput, not a license to share QL state
 unsafely.

3. **Keep native kernels off QuantLib globals.**
 The C++ scenario kernel (and any future pure numerical kernels) must stay
 free of QuantLib types, settings, and pricing objects. Parallelism inside
 the `.so` (`RISKFORGE_KERNEL_THREADS`) only partitions shock indices for
 Δ-Γ aggregation. Methodology selection and FULL_REVALUATION remain in
 Python on `PricingEngine`.

4. **Do not mix strategies.**
 Do not add OpenMP (or a second pool) to the scenario kernel, and do not
 “speed up” QuantLib by spawning threads that each mutate process-global
 evaluation date without going through the adapter lock.

## R0.3.5 process-partition design (bounded)

R0.3.5 pins the concurrency architecture. It does **not** introduce a
scenario-block `ProcessPoolExecutor` or a job platform (that remains R0.6.5
after profiling).

| Path | What happens | Parallelism |
|---|---|---|
| In-process QuantLib (`QuantLibPricingEngine._session`) | `_QL_PROCESS_LOCK` serializes `Settings` / `IndexManager` | None (correct serial bottleneck) |
| In-process `RiskRunWorker` `ThreadPoolExecutor` | Schedules risk-run **jobs** only; pricing still takes the process lock | Job overlap, not QL overlap |
| Compose `backend` + `RISKFORGE_EXTERNAL_WORKER=1` | HTTP enqueues `QUEUED` rows; does not execute full reval in the API process | API process stays off the QL work |
| Compose `worker` / `python -m app.worker` | Separate OS process claims and executes runs | One QuantLib address space per worker |
| Extra worker replicas | `FOR UPDATE SKIP LOCKED` claim | Process-level scale-out |
| Native scenario kernel | Δ-Γ buffers only; no QuantLib types or settings | Shock-index threads inside the `.so` |

Forbidden:

- `ThreadPoolExecutor` (or any in-process pool) that mutates `ql.Settings` or
  prices QuantLib without `_QL_PROCESS_LOCK` / `_session`.
- Moving QuantLib into `backend/native/`.
- Changing numerical methodology to “get parallelism.”

`full_revaluation_pnl_series` stays a sequential `PricingEngine` loop inside
one process. Parallel full revaluation, when needed, is another worker
process — not more threads in that loop.

## Alternatives considered

| Alternative | Why rejected / deferred |
|-------------|-------------------------|
| Assume QuantLib is thread-safe for evaluation date | Process-global `Settings`; concurrent mutation is undefined / races. |
| Remove RLock and rely on GIL | GIL does not protect C++ QuantLib globals across extension calls. |
| Thread-parallel FULL_REVAL without lock | Unsafe; would change numerical/process behavior under load. |
| Move QuantLib into the native scenario `.so` | Violates “pricing library prices; RiskForge aggregates”; couples ABI to QL. |
| ProcessPoolExecutor for every risk run now | Heavier ops change; still documents single-process poll + future claim/lease. Prefer documenting the target architecture over premature rewrite. |

## Consequences

- Parallel agents must not bypass `_session` / the adapter lock when adding
 QuantLib call sites.
- Product speed claims for FULL_REVALUATION must cite process-level scaling or
 a future native pricing service — not scenario-kernel microbenchmarks.
- Risk-run `ThreadPoolExecutor` remains valid because the RLock serializes QL;
 multi-worker **processes** are the intended horizontal scale-out.
- ADR 001 (QuantLib as pricing backend) stands; this ADR records concurrency
 only. Caching (`pricing/cache.py`) must avoid nesting locks that deadlock
 with the QL RLock (compute outside cache lock when calling into QL).

## Related

- `docs/adr/001-quantlib-for-pricing.md`
- `backend/app/pricing/quantlib.py` (`RLock`, `_session`)
- `backend/app/services/risk_run_worker.py` (job thread pool + external process worker)
- `backend/app/worker.py` (Compose worker process entrypoint)
- `backend/tests/test_quantlib_process_parallelism.py` (R0.3.5 pins)
- `backend/native/README.md` (kernel parallelism; FULL_REVAL out of scope)
- ROADMAP
