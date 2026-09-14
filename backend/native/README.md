# Native scenario kernel

Build the optional shared library (C++20; `-pthread` for the stdlib thread
pool; **`-I include` is required** — the header lives under `native/include/`):

```bash
g++ -std=c++20 -O3 -shared -fPIC -pthread -I include \
 src/risk_kernel_capi.cpp -o libriskkernel.so
# macOS: prefer -o libriskkernel.dylib
```

`app.compute.kernel.NativeScenarioKernel` loads it with Python `ctypes`; no pybind11 dependency is required.

## C ABI (R0.12.5)

Header: `include/risk_kernel_capi.h`. Python constants live in `app.compute.kernel`
(`KERNEL_ABI_VERSION`, `KERNEL_OK`, `KERNEL_ERR_*`).

| Symbol | Role |
|---|---|
| `QUANTLINEAGE_KERNEL_ABI` / `quantlineage_kernel_abi_version()` | Version **1**. Python refuses to load a mismatch. |
| `quantlineage_portfolio_scenarios` | Returns `int` (`OK=0`, `ERR_ABI=1`, `ERR_NULL=2`, `ERR_LENGTH=3`). |
| Exposure stride | 5 doubles (`delta, gamma, vega, dv01, fx_delta`) |
| Shock stride | 4 doubles (`equity, vol_points, rates_bps, fx`) |

Length contract (mismatch → `ERR_LENGTH`, **no writes / no overrun**):

- `n_exposure_doubles == n_exposures * 5`
- `n_shock_doubles == n_shocks * 4`
- `n_out == n_shocks`

Null / empty policy:

- Count `== 0`: pointer may be `NULL`; it is not dereferenced.
- `n_shocks == 0`: success, no writes (`out` may be `NULL`).
- `n_exposures == 0` and `n_shocks > 0`: write `0.0` per shock (empty book).
- Count `> 0` and pointer is `NULL`: `ERR_NULL` (out buffer unchanged).

P&L math and (absent) SIMD are unchanged. Tiny E×S stays serial (R0.17).
`kernel_test` must compile
`src/risk_kernel_capi.cpp` with the same flags as the baseline:

```bash
g++ -std=c++20 -O2 -pthread -I include \
  tests/kernel_test.cpp src/risk_kernel_capi.cpp -o /tmp/kernel_test
```

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
| `QUANTLINEAGE_KERNEL_THREADS=1` | Serial nested loops (parity / baseline) |
| `QUANTLINEAGE_KERNEL_THREADS=N` (`N>1`) | Up to `N` workers (capped by `n_shocks`) |
| unset | `std::thread::hardware_concurrency` (min 1) |
| C++ CLI `--threads T` | Same resolution (`0` = auto via env/hw) |
| `n_exposures * n_shocks < 4096` | Always serial (R0.17; no per-call spawn) |

`NativeScenarioKernel.pnl_from_arrays` passes C-contiguous `float64` NumPy
buffers to the C ABI without an extra pack copy. `pnl()` still packs
`Exposure`/`Shock` lists for the object API.

Inner exposure reduction order for each shock matches the serial loop → numerical
parity with single-thread (see `tests/kernel_test.cpp`,
`backend/tests/test_native_kernel.py`).

**Do not add OpenMP or a second pool.** Product risk path still selects Python vs
native via `QUANTLINEAGE_SCENARIO_KERNEL` only; parallelism is internal to the .so.

## Risk-path wiring Historical VaR / scenario P&L for **LINEAR** and **DELTA_GAMMA** may evaluate the
linear Δ-Γ kernel via:

| Env | Effect |
|---|---|
| `QUANTLINEAGE_SCENARIO_KERNEL=python` (default) | NumPy vectorized formula in `approximate_pnl_series` |
| `QUANTLINEAGE_SCENARIO_KERNEL=native` | ctypes `NativeScenarioKernel` |
| `QUANTLINEAGE_SCENARIO_KERNEL_LIB` | Optional absolute path to the shared library |

Methodology selection, vol-point scaling (`vol_move × 100`), and LINEAR γ=0 remain
in Python (`app.risk.historical`). Business logic is not moved into C++.

### FULL_REVALUATION cannot use this kernel

`VaRMethodology.FULL_REVALUATION` reprices each shocked `MarketSnapshot` through
`PricingEngine`. That path is outside the Exposure/Shock ABI (no Greeks-only
approximation). Setting `QUANTLINEAGE_SCENARIO_KERNEL=native` does **not** accelerate
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
QUANTLINEAGE_KERNEL_THREADS=1 python3 benchmarks/run_scenario_bench.py --workload 1k_x_1k

# parallel vs serial (same host)
python3 benchmarks/run_scenario_bench.py --workload 10k_x_1k \
 --threads 4 --parallel-compare
```

See `benchmarks/README.md` and `benchmarks/RESULTS.md` for workloads, identical I/O
semantics, metrics, and environment caveats. These timings are not production SLAs.
