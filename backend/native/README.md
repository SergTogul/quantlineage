# Native scenario kernel

Build the optional shared library (C++20; `-pthread` for the stdlib thread
pool; **`-I include` is required** — the header lives under `native/include/`):

```bash
g++ -std=c++20 -O3 -shared -fPIC -pthread -I include \
 src/risk_kernel_capi.cpp -o libriskkernel.so
# macOS: prefer -o libriskkernel.dylib
```

`app.compute.kernel.NativeScenarioKernel` loads it with Python `ctypes`; no pybind11 dependency is required.

## Parallel strategy — one approach only

**Choice: C++20 standard-library thread pool over contiguous shock partitions.**

Prefer `std::jthread` when `__cpp_lib_jthread` is available; otherwise
`std::thread` + join-on-scope-exit (same strategy — Apple Clang libc++ often
lacks `std::jthread`). **Never OpenMP.**

| Why not OpenMP | Why std thread pool |
|---|---|
| Apple Clang often lacks bundled OpenMP (`libomp` / `-fopenmp` extra dep) | Ships with the toolchain; no third-party runtime |
| Schedule/reduction quirks can obscure parity | Each `out[j]` written by exactly one thread |
| Mixing OpenMP + other pools is forbidden here | Single coherent strategy in `risk_kernel.hpp` |

Thread count:

| Env / API | Effect |
|---|---|
| `RISKFORGE_KERNEL_THREADS=1` | Serial nested loops (parity / baseline) |
| `RISKFORGE_KERNEL_THREADS=N` (`N>1`) | Up to `N` workers (capped by `n_shocks`) |
| unset | `std::thread::hardware_concurrency` (min 1) |
| C++ CLI `--threads T` | Same resolution (`0` = auto via env/hw) |

Inner exposure reduction order for each shock matches the serial loop → numerical
parity with single-thread (see `tests/kernel_test.cpp`,
`backend/tests/test_native_kernel.py`).

**Do not add OpenMP or a second pool.** Product risk path still selects Python vs
native via `RISKFORGE_SCENARIO_KERNEL` only; parallelism is internal to the .so.

## Risk-path wiring Historical VaR / scenario P&L for **LINEAR** and **DELTA_GAMMA** may evaluate the
linear Δ-Γ kernel via:

| Env | Effect |
|---|---|
| `RISKFORGE_SCENARIO_KERNEL=python` (default) | NumPy vectorized formula in `approximate_pnl_series` |
| `RISKFORGE_SCENARIO_KERNEL=native` | ctypes `NativeScenarioKernel` |
| `RISKFORGE_SCENARIO_KERNEL_LIB` | Optional absolute path to the shared library |

Methodology selection, vol-point scaling (`vol_move × 100`), and LINEAR γ=0 remain
in Python (`app.risk.historical`). Business logic is not moved into C++.

### FULL_REVALUATION cannot use this kernel

`VaRMethodology.FULL_REVALUATION` reprices each shocked `MarketSnapshot` through
`PricingEngine`. That path is outside the Exposure/Shock ABI (no Greeks-only
approximation). Setting `RISKFORGE_SCENARIO_KERNEL=native` does **not** accelerate
or alter full revaluation.

## Parity & tolerances | Layer | Tests | Abs / rel |
|---|---|---|
| ABI: Python ↔ native ↔ C++ serial/parallel | `tests/test_native_kernel.py`, `native/tests/kernel_test.cpp` | `KERNEL_ABI_*` = **1e-12** (`app.compute.kernel`) |
| Risk path: NumPy ↔ native on LINEAR/Δ-Γ P&L and VaR/ES | `tests/test_historical_scenario_kernel.py` | `KERNEL_PNL_ABS_TOL` = **1e-9**, `KERNEL_PNL_REL_TOL` = **1e-12** |

Units: currency P&L. Sign: positive = gain. NaN/Inf are **not** sanitized —
callers must pass finite shocks/exposures; both backends must propagate equally.

FULL_REVALUATION never uses this kernel (PricingEngine only). QuantLib
concurrency is orthogonal — see `docs/adr/007-quantlib-concurrency.md`.

## Microbenchmark

`src/benchmark.cpp` is a standalone CLI (sizes, iterations, threads, JSON metrics).
Prefer the repo-root harness for Python / NumPy / ctypes / C++ comparison:

```bash
# from repo root — serial baseline
RISKFORGE_KERNEL_THREADS=1 python3 benchmarks/run_scenario_bench.py --workload 1k_x_1k

# parallel vs serial (same host)
python3 benchmarks/run_scenario_bench.py --workload 10k_x_1k \
 --threads 4 --parallel-compare
```

See `benchmarks/README.md` and `benchmarks/RESULTS.md` for workloads, identical I/O
semantics, metrics, and environment caveats. These timings are not production SLAs.
