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

1. **Serialize QuantLib use inside one process via `RLock`.**
 `QuantLibPricingEngine` owns an instance `RLock` and wraps every valuation
 path that touches QuantLib settings (and related construction) in `_session`.
 Callers (risk engines, services, workers) must not manipulate
 `ql.Settings` themselves.

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
- `backend/app/services/risk_run_worker.py` (thread pool + external process worker)
- `backend/native/README.md` (kernel parallelism; FULL_REVAL out of scope)
- ROADMAP
