# Scenario aggregation benchmarks + formal SLA

Reproducible microbenchmarks for the scenario matrix × exposure vector kernel
used by the optional native path (`backend/native`, `app.compute.kernel`).

**Formal product SLA ( COMPLETE):** relative floors for the nested-loop native
kernel on workload `10k_x_1k` — see [`RESULTS.md`](RESULTS.md) (SLA-K1 / SLA-K2).
Verify with:

```bash
backend/.venv/bin/python benchmarks/check_m6_sla.py
```

This harness is **not** an HTTP end-to-end risk-run or API latency benchmark.
Absolute milliseconds are host-specific; do not treat table cells as multi-tenant
capacity planning. The published claim is the scoped relative SLA only.

** baseline table:** [`RESULTS.md`](RESULTS.md) (Python / NumPy / C++
single-thread, identical I/O semantics, NumPy strength-reduction caveat).

** parallel C++:** same file, section “ — Parallel C++ (stdlib thread pool)”.
Strategy is **only** a C++20 stdlib shock-partition pool (`jthread` when available,
else `std::thread`+join) — never OpenMP.

## Identical I/O semantics

All compared implementations implement the same contract:

```text
pnl(exposures: list[Exposure], shocks: list[Shock]) -> list[float] # len == len(shocks)
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
| `speedup_vs_cpp_serial` | serial C++ wall / parallel C++ wall ( `--parallel-compare`) |

Implementations:

- **python** — `PythonScenarioKernel` (reference)
- **numpy** — vectorized aggregate-then-scale (optional; skipped if NumPy missing)
- **cpp_ctypes** — builds `risk_kernel_capi.cpp`, calls via `NativeScenarioKernel`
- **cpp_header** — builds/runs enhanced `backend/native/src/benchmark.cpp`
- **cpp_*_tN** — same kernels with `QUANTLINEAGE_KERNEL_THREADS=N` / `--threads N`

## Workloads

| Name | Exposures × shocks | Notes |
|------|--------------------|-------|
| `smoke` | 64 × 64 | Harness plumbing / CI smoke |
| `1k_x_1k` | 1 000 × 1 000 | Default practical size |
| `10k_x_1k` | 10 000 × 1 000 | Default practical size |
| `50k_x_1k` | 50 000 × 1 000 | Heavier; matches earlier ad-hoc native bench |

## How to run

From the repo root (requires `g++` with C++20 for native/cpp paths). Prefer the
project venv so NumPy is available:

```bash
# Defaults: 1k×1k and 10k×1k, all impls (single-thread)
QUANTLINEAGE_KERNEL_THREADS=1 backend/.venv/bin/python benchmarks/run_scenario_bench.py

# serial + 4-thread stdlib pool on the same run
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

- **Host-specific absolute times.** Results vary with CPU, thermal throttling, power
 mode, compiler version (`-O3`), Python build, NumPy BLAS, and OS scheduler.
 Formal claim is **SLA-K1/K2** relative floors in [`RESULTS.md`](RESULTS.md).
- **Single-process microbench.** No concurrent tenants, no QuantLib pricing, no
 DB/API, no risk-run worker. risk-path wiring uses
 `QUANTLINEAGE_SCENARIO_KERNEL` in product code — this harness measures the shared
 kernel ABI, not HTTP Historical VaR end-to-end.
- **Parallel C++ .** Stdlib shock-partition thread pool only (`std::jthread`
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
 `cpp_ctypes` for realistic FFI overhead. Product Historical VaR currently
 aggregates to 1 exposure before the kernel — 1×N timings are FFI-bound; see
 RESULTS.md non-claims.
- **NumPy path algebra.** The NumPy impl sums exposures then scales by shocks
 (valid because the kernel is linear in exposures). That is an algebraic
 strength reduction (`O(E+S)` after the sum vs nested `O(E×S)` loops), so
 NumPy speedups are **not** an apples-to-apples comparison against the nested
 Python/C++ loops — they are a useful upper-bound / rewrite signal. Details in
 [`RESULTS.md`](RESULTS.md).
- **Compiler required.** Without `g++`, pass `--skip-native --skip-cpp` to run
 Python/NumPy only. Shared builds need `-I backend/native/include -pthread`.
- **Do not fight .** This directory must not depend on risk-run HTTP APIs.

Benchmark scripts stay separate from product unit tests. Equivalence stays in
`backend/tests/test_native_kernel.py` and Historical VaR parity in
`backend/tests/test_historical_scenario_kernel.py`.

## FULL_REVALUATION baseline (R0.6.1 / R0.6.7 / R0.6.8)

`run_full_reval_bench.py` records a **checksum/impl identity** on the nightly
120-obs unit-equity sample (shocked PV − base PV). `wall_ms` is printed for
operators and is **not** a host SLA. Do not invoke `check_m6_sla.py`. Do not
treat a positive throughput reading as a floor.

R0.6.7 adds a nested `acceptance` object at PR-safe **N=10 × S=50** (above
1×120): `peak_rss_kib`, `scenarios_per_sec`, `wall_ms_cold` / `wall_ms_warm`,
and builtin vs QuantLib at the same N×S (cash equity). QuantLib is skip-or-run
(fail-closed when `QUANTLINEAGE_REQUIRE_QUANTLIB=1`). Pytest asserts those values
are finite numbers, not floors. Operators may pass `--acceptance-n` /
`--acceptance-s`; do not use N=1000 in PR CI.

R0.6.8 adds a nested `reconstruction` object: European options with live
spot/vol/rate/div, checksums **per engine**, isolated RSS via `--isolated-impl`
subprocess, and a recorded P&L gap at option-match `rel=2e-3`. N=100×50 is
nightly-only (`QUANTLINEAGE_NIGHTLY=1`; job `full-reval-n100`). Not in PR-FULL
`needs:`.

```bash
PYTHONPATH=backend backend/.venv/bin/python benchmarks/run_full_reval_bench.py --json
python3 -m pytest backend/tests/test_full_reval_bench.py -q
QUANTLINEAGE_NIGHTLY=1 python3 -m pytest backend/tests/test_nightly_full_reval_n100.py -q
```

## Stage 10.3 FULL_REVALUATION matrix (not an HTTP / kernel SLA)

`run_full_reval_bench.py --stage103` runs a seeded multi-asset book (cash equities
+ European options so FULL ≠ LINEAR) through the product
`full_revaluation_pnl_from_panel` / `approximate_pnl_from_panel` paths. R0.6
identity benches above are unchanged. Default `--json` without `--stage103` still
emits only the R0.6 payload.

Attempted cells (record honestly if a cell exceeds `--max-cell-wall-s`):

- 100 × 250 FULL_REVALUATION (builtin + QuantLib)
- 100 × 1000 FULL_REVALUATION
- 1000 × 250 FULL_REVALUATION
- 1000 × 1000 FULL_REVALUATION if it finishes in budget
- 10000 × 1000 LINEAR and DELTA_GAMMA

Host observations: [`FULL_REVAL_RESULTS.md`](FULL_REVAL_RESULTS.md) (generated from
`full_reval_stage103.json`). This is **not** an HTTP SLA, **not** multi-tenant
capacity, and **does not** change labeled-runner SLA-K1/K2 (post-R0). Do not
invoke `check_m6_sla.py`.

```bash
# CI-safe 4×8 smoke (JSON + CSV + Markdown)
PYTHONPATH=backend backend/.venv/bin/python benchmarks/run_full_reval_bench.py \
  --stage103 --smoke --json --csv /tmp/stage103.csv --markdown /tmp/stage103.md

# Operator matrix (isolated RSS per cell; abort cells over 240s wall)
PYTHONPATH=backend backend/.venv/bin/python benchmarks/run_full_reval_bench.py \
  --stage103 --json --max-cell-wall-s 240 \
  --csv benchmarks/full_reval_stage103.csv \
  --markdown benchmarks/FULL_REVAL_RESULTS.md

cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_stage103_full_reval_bench.py -q
```

