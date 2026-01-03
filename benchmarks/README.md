# Scenario aggregation benchmarks (M6.1 / M6.2 / M6.4)

Reproducible microbenchmarks for the scenario matrix × exposure vector kernel
used by the optional native path (`backend/native`, `app.compute.kernel`).

This harness is **not** an end-to-end risk-run, VaR, or API latency benchmark.
Numbers here are laptop/CI microbenchmarks only — do not treat them as
production SLAs or capacity planning evidence.

**M6.2 baseline table:** [`RESULTS.md`](RESULTS.md) (Python / NumPy / C++
single-thread, identical I/O semantics, NumPy strength-reduction caveat).

**M6.4 parallel C++:** same file, section “M6.4 — Parallel C++ (stdlib thread pool)”.
Strategy is **only** a C++20 stdlib shock-partition pool (`jthread` when available,
else `std::thread`+join) — never OpenMP.

## Identical I/O semantics

All compared implementations implement the same contract:

```text
pnl(exposures: list[Exposure], shocks: list[Shock]) -> list[float]  # len == len(shocks)
```

Per-shock portfolio PnL is the sum over exposures of

`δ·er + ½γ·er² + ν·vol + dv01·rates + fxΔ·fx`.

| Impl | Same I/O? | Same nested `O(E×S)` work? |
|------|-----------|----------------------------|
| python | yes | yes (reference) |
| numpy | yes | **no** — strength reduction `O(E+S)` |
| cpp_ctypes | yes | yes (+ FFI packing) |
| cpp_header | yes | yes (in-process) |
| cpp_*_tN | yes | yes, jthread over shock partitions |

## What is measured

| Metric | Meaning |
|--------|---------|
| `wall_ms` | Timed steady-clock / `perf_counter` duration (warmup excluded) |
| `throughput_ops_per_s` | `(n_exposures × n_shocks × iters) / seconds` — per-exposure scenario PnL evals |
| `scenarios_per_s` | `(n_shocks × iters) / seconds` — full portfolio scenario rows |
| `peak_rss_kib` | Process peak RSS (see caveats) |
| `speedup_vs_python` | `python.wall_ms / impl.wall_ms` for the same workload |
| `speedup_vs_cpp_serial` | serial C++ wall / parallel C++ wall (M6.4 `--parallel-compare`) |

Implementations:

- **python** — `PythonScenarioKernel` (reference)
- **numpy** — vectorized aggregate-then-scale (optional; skipped if NumPy missing)
- **cpp_ctypes** — builds `risk_kernel_capi.cpp`, calls via `NativeScenarioKernel`
- **cpp_header** — builds/runs enhanced `backend/native/src/benchmark.cpp`
- **cpp_*_tN** — same kernels with `RISKFORGE_KERNEL_THREADS=N` / `--threads N`

## Workloads

| Name | Exposures × shocks | Notes |
|------|--------------------|-------|
| `smoke` | 64 × 64 | Harness plumbing / CI smoke |
| `1k_x_1k` | 1 000 × 1 000 | Default practical size (M6.2) |
| `10k_x_1k` | 10 000 × 1 000 | Default practical size (M6.2 / M6.4) |
| `50k_x_1k` | 50 000 × 1 000 | Heavier; matches earlier ad-hoc native bench |

## How to run

From the repo root (requires `g++` with C++20 for native/cpp paths). Prefer the
project venv so NumPy is available:

```bash
# Defaults: 1k×1k and 10k×1k, all impls (single-thread)
RISKFORGE_KERNEL_THREADS=1 backend/.venv/bin/python benchmarks/run_scenario_bench.py

# M6.4: serial + 4-thread stdlib pool on the same run
backend/.venv/bin/python benchmarks/run_scenario_bench.py \
  --workload 10k_x_1k --threads 4 --parallel-compare

# JSON report
backend/.venv/bin/python benchmarks/run_scenario_bench.py \
  --json --workload 10k_x_1k --threads 4 --parallel-compare

# Smoke only (also used by the harness test)
python3 benchmarks/run_scenario_bench.py --workload smoke --iters 1

# Keep build artifacts
python3 benchmarks/run_scenario_bench.py --build-dir benchmarks/build --workload 1k_x_1k

# Standalone C++ binary (same kernel header)
g++ -std=c++20 -O3 -pthread -I backend/native/include \
  backend/native/src/benchmark.cpp -o /tmp/scenario_bench
/tmp/scenario_bench --exposures 1000 --shocks 1000 --threads 4 --json
```

Harness smoke test (separate from backend unit suite):

```bash
python3 -m pytest benchmarks/test_bench_smoke.py -q
```

## Environment caveats

- **Not production claims.** Results vary with CPU, thermal throttling, power
  mode, compiler version (`-O3`), Python build, NumPy BLAS, and OS scheduler.
- **Single-process microbench.** No concurrent tenants, no QuantLib pricing, no
  DB/API, no risk-run worker. M6.3 risk-path wiring uses
  `RISKFORGE_SCENARIO_KERNEL` in product code — this harness does not measure
  Historical VaR end-to-end.
- **Parallel C++ (M6.4).** Stdlib shock-partition thread pool only (`std::jthread`
  when `__cpp_lib_jthread` is available, else `std::thread`+join — Apple clang 14
  libc++ typically lacks jthread). Do **not** set `OMP_NUM_THREADS` expecting
  kernel OpenMP — there is none. Hyperthreading, power limits, and small
  workloads (e.g. `smoke` 64×64) can show little or no speedup; prefer
  `10k_x_1k` / `50k_x_1k` for parallel evidence. ctypes packing can dominate at
  small sizes so `cpp_header` is the fairer parallel kernel view.
- **RSS units differ by OS.** macOS `getrusage.ru_maxrss` is bytes; Linux is
  KiB. The harness normalizes to KiB. Peak RSS includes interpreter/runtime
  overhead for Python/ctypes paths and is not allocatable-heap-only.
- **ctypes marshalling cost.** `cpp_ctypes` includes Python→C array packing;
  `cpp_header` does not. Prefer `cpp_header` for raw kernel throughput and
  `cpp_ctypes` for realistic FFI overhead.
- **NumPy path algebra.** The NumPy impl sums exposures then scales by shocks
  (valid because the kernel is linear in exposures). That is an algebraic
  strength reduction (`O(E+S)` after the sum vs nested `O(E×S)` loops), so
  NumPy speedups are **not** an apples-to-apples comparison against the nested
  Python/C++ loops — they are a useful upper-bound / rewrite signal. Details in
  [`RESULTS.md`](RESULTS.md).
- **Compiler required.** Without `g++`, pass `--skip-native --skip-cpp` to run
  Python/NumPy only. Shared builds need `-I backend/native/include -pthread`.
- **Do not fight M5.4.** This directory must not depend on risk-run HTTP APIs.
- **Do not claim VaR SLAs from this harness.** Risk-path native opt-in is
  `RISKFORGE_SCENARIO_KERNEL` in product code, not the bench tree.

## Ownership

Owned by the C++ Performance Engineer (`docs/agents/06_CPP_PERFORMANCE_ENGINEER.md`).
Benchmark scripts stay separate from product unit tests; equivalence stays in
`backend/tests/test_native_kernel.py` and Historical VaR parity in
`backend/tests/test_historical_scenario_kernel.py`.
