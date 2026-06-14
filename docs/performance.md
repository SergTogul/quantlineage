# Performance Report

RiskForge has one formal performance claim today: a scoped native scenario-kernel SLA for the C++20 `ctypes` path used by LINEAR and DELTA_GAMMA approximate Historical VaR aggregation.

It does not claim HTTP latency, full-revaluation throughput, multi-tenant capacity, or QuantLib pricing speedups.

## What Is Benchmarked

The benchmarked kernel contract is:

```text
pnl(exposures, shocks) -> per-scenario portfolio P&L
```

Each exposure has delta, gamma, vega, DV01, and FX delta terms. Each shock has equity return, volatility points, rate basis points, and FX return. The kernel sums deterministic approximate P&L over exposure x shock rows.

Benchmarked implementations:

- `python`: pure-Python nested-loop reference.
- `numpy`: vectorized/strength-reduced comparison path, useful as an upper-bound signal but not same-loop evidence.
- `cpp_ctypes`: C++20 shared library called through `NativeScenarioKernel`, including Python-to-C marshalling.
- `cpp_header`: standalone C++ benchmark binary for raw in-process kernel throughput.
- `cpp_*_tN`: standard-library shock-partition parallel variants.

## Formal SLA

The accepted Workstream 6 SLA is recorded in [`benchmarks/RESULTS.md`](../benchmarks/RESULTS.md):

| ID | Requirement | Floor |
|---|---|---:|
| SLA-K1 | On workload `10k_x_1k`, serial `cpp_ctypes` wall-time speedup versus pure-Python nested-loop `python`. | >= 50x |
| SLA-K2 | On the same workload, `cpp_ctypes_t4` speedup versus serial `cpp_ctypes` in a parallel-compare run. | >= 1.3x |

Reference-host evidence from `benchmarks/RESULTS.md` shows SLA-K1 and SLA-K2 above those floors, with checksums guarded by the benchmark harness. Absolute times are host-specific.

Verification command:

```bash
backend/.venv/bin/python benchmarks/check_m6_sla.py
```

## What The Claim Proves

- The native nested-loop scenario kernel is substantially faster than the pure-Python nested-loop reference on the named workload and reference host class.
- The four-thread stdlib shock-partition variant improves over serial `cpp_ctypes` above the accepted floor on the named workload.
- The kernel ABI and Historical VaR approximate-path wiring are covered by parity tests.

## What It Does Not Prove

- It does not prove FastAPI endpoint latency or queued risk-run latency.
- It does not accelerate `FULL_REVALUATION`; that mode reprices through `PricingEngine`.
- It does not prove QuantLib is thread-parallel inside one process. ADR 007 requires serialized in-process QuantLib access and prefers process isolation for parallel full revaluation.
- It does not prove multi-tenant capacity planning or production SLOs.
- It does not prove `1 x N` aggregated-Greek Historical VaR is 50x faster than NumPy. The current product path can be FFI-bound at small exposure counts.
- It is not a CI hard gate on arbitrary runner hardware.
- RF-016 residual: labeled-runner SLA-K1/K2 is PARTIAL. This repository has no labeled self-hosted Actions runner (`actions/runners total_count=0` as of 2026-09-09). Nightly GitHub-hosted `ubuntu-latest` jobs must not run `benchmarks/check_m6_sla.py`. R0.12.7 accepted this as a named residual when RF-016 CLOSED; SLA-K1/K2 is not CI-enforced.

## Operational Notes

- Native kernel usage is opt-in with `RISKFORGE_SCENARIO_KERNEL=native`.
- `RISKFORGE_KERNEL_THREADS` controls the C++ stdlib partition count; there is no OpenMP path.
- C++ builds require a C++20-capable `g++` and include paths documented in [`backend/native/README.md`](../backend/native/README.md).
- Benchmark scripts live under [`benchmarks/`](../benchmarks/), separate from product unit tests.

## Related Evidence

- Benchmark operator guide: [`benchmarks/README.md`](../benchmarks/README.md)
- Captured benchmark evidence and SLA: [`benchmarks/RESULTS.md`](../benchmarks/RESULTS.md)
- Native kernel notes: [`backend/native/README.md`](../backend/native/README.md)
- Concurrency decision: [`docs/adr/007-quantlib-concurrency.md`](adr/007-quantlib-concurrency.md)
