# scenario-kernel benchmarks + formal product SLA

Measured under the formal scenario-kernel SLA below — not an HTTP end-to-end VaR latency claim.

 wires this kernel into LINEAR/DELTA_GAMMA approximate P&L behind
`QUANTLINEAGE_SCENARIO_KERNEL`. parallel results follow the serial baseline.

Do **not** cite these numbers as multi-tenant capacity planning or HTTP risk-run
guarantees. Absolute milliseconds move with CPU/thermal; the published SLA uses
**relative floors** with host/workload caveats.

---

## Formal product SLA ( COMPLETE gate)

**Claim (Lead Architect + C++ Performance, 2026-09-02):** On the documented
reference host class, the **native nested-loop scenario kernel** (same ctypes
ABI Historical VaR uses when `QUANTLINEAGE_SCENARIO_KERNEL=native`) meets:

| ID | Requirement | Floor | Measurement |
|----|-------------|------:|-------------|
| **SLA-K1** | Workload `10k_x_1k` (10 000 exposures × 1 000 shocks): serial `cpp_ctypes` wall-time speedup vs pure-Python nested-loop `python` | **≥ 50×** | `benchmarks/run_scenario_bench.py --workload 10k_x_1k --iters 1 --json` (or `check_m6_sla.py`) |
| **SLA-K2** | Same workload: `cpp_ctypes_t4` (`--threads 4 --parallel-compare`) vs serial `cpp_ctypes` on the same run | **≥ 1.3×** | same harness / `check_m6_sla.py` |

Checksums must match Python within the harness guard (`1e-6` relative).

### Pass / fail command

```bash
backend/.venv/bin/python benchmarks/check_m6_sla.py
```

### Evidence (this reference host, 2026-09-02 refresh)

| Capture | SLA-K1 (`cpp_ctypes` vs `python`) | SLA-K2 (`t4` vs serial) | Verdict |
|---------|----------------------------------:|------------------------:|---------|
| Serial JSON refresh | **133×** (42.3 ms vs 5643 ms) | — | above 50× |
| Parallel compare refresh | **139×** (41.0 ms vs 5695 ms) | **1.83×** (22.4 ms) | above floors |
| `check_m6_sla.py` verify runs | **106–145×** | **1.45–1.95×** | PASS (K2 floor 1.3×) |
| Prior RESULTS.md tables | 88–125× | ~2.0–2.1× | above floors |

### Reference host class

| Field | Value |
|-------|--------|
| CPU | Intel(R) Core(TM) i7-7700HQ @ 2.80GHz (4C/8T) |
| OS / platform | macOS 13.7.8 (`macOS-13.7.8-x86_64-i386-64bit`) |
| Python | 3.12.14 (`backend/.venv`) |
| Compiler | Apple clang 14.0.3 (`g++ -std=c++20 -O3 -pthread`) |
| Power / thermal | Uncontrolled laptop — floors leave margin (SLA-K1 vs ~88–145× measured; SLA-K2 floor 1.3× vs ~1.45–2.1× observed) |

### Explicit non-claims

- **Not** HTTP/API end-to-end Historical VaR wall time.
- **Not** FULL_REVALUATION (never uses the kernel).
- **Not** a CI hard gate on arbitrary runners (host class differs).
- **Not** “1×N aggregated-Greek Historical VaR is 50× faster than NumPy.” Current
 product path aggregates Greeks to **one** exposure before the kernel; ad-hoc
 `1×750` / `1×10k` timings on this host show ctypes ≈ Python (FFI packing
 dominates). Multi-exposure `E×S` is the measurable nested-loop claim for the
 wired native ABI.

---

## — Baseline Python / NumPy / C++ single-thread comparison

**Status:** captured microbenchmark snapshot (supports SLA-K1 evidence).

---

## Identical I/O semantics

Every implementation under comparison accepts and returns the same contract as
`ScenarioKernel.pnl` in `backend/app/compute/kernel.py`:

| | Contract |
|---|---|
| **Input** | `exposures: list[Exposure]` — each `(delta, gamma, vega, dv01, fx_delta)` |
| **Input** | `shocks: list[Shock]` — each `(equity_return, vol_points, rates_bps, fx_return)` |
| **Output** | `list[float]` of length `len(shocks)` — portfolio PnL per shock |
| **Kernel** | Per exposure×shock: `δ·er + ½γ·er² + ν·vol + dv01·rates + fxΔ·fx` summed over exposures |

| Impl | Entry point | Loop shape | Notes |
|------|-------------|------------|--------|
| `python` | `PythonScenarioKernel.pnl` | Nested `O(E×S)` | Reference |
| `numpy` | `benchmarks/run_scenario_bench.py::numpy_pnl` | Strength-reduced `O(E+S)` after packing | Same I/O + numerical result; **not** same asymptotic work |
| `cpp_ctypes` | `NativeScenarioKernel.pnl` → `quantlineage_portfolio_scenarios` | Nested `O(E×S)` + Python packing/FFI | Realistic ctypes overhead |
| `cpp_header` | `backend/native/src/benchmark.cpp` → `portfolio_scenarios` | Nested `O(E×S)` in-process | Raw kernel; no Python marshalling |

Harness inputs are deterministic constants matching the C++ CLI defaults
(every exposure `{1000, 200, 30, -10, 500}`, every shock `{-0.01, 2, 5, -0.002}`).
Warmup is excluded from `wall_ms`. Checksums must match Python within relative
`1e-6` (ctypes/NumPy guard in the harness).

### NumPy strength-reduction caveat

Because portfolio PnL is **linear in exposures** for a fixed shock, summing the
exposure vector once and applying each shock is algebraically identical to the
nested loops:

```text
Σ_e pnl(e, s) ≡ pnl(Σ_e e, s) (for this kernel)
```

The harness NumPy path uses that rewrite. Wall-time speedups for `numpy` are
therefore a **rewrite / upper-bound signal**, not an apples-to-apples comparison
of nested-loop Python vs nested-loop C++. For loop-vs-loop evidence use
`python` vs `cpp_ctypes` vs `cpp_header` only.

---

## Environment (this capture)

| Field | Value |
|-------|--------|
| Date (local) | 2026-09-02 |
| Host CPU | Intel(R) Core(TM) i7-7700HQ CPU @ 2.80GHz (4C/8T) |
| OS / platform | macOS 13.7.8 (`macOS-13.7.8-x86_64-i386-64bit`) |
| Python | 3.12.14 (`backend/.venv`) |
| NumPy | 2.5.2 |
| Compiler | Apple clang 14.0.3 (`g++ -std=c++20 -O3`) |
| Threading | Single-thread; `OMP_NUM_THREADS=1` (kernel has no OpenMP) |
| Power / thermal | Uncontrolled laptop session — expect run-to-run variance |

Regenerate:

```bash
OMP_NUM_THREADS=1 backend/.venv/bin/python benchmarks/run_scenario_bench.py \
 --workload 1k_x_1k --workload 10k_x_1k --iters 1 --json
```

---

## Results table (iters=1)

Wall times are for the timed region only (warmup excluded). Throughput
`ops/s` = `(n_exposures × n_shocks × iters) / seconds`. Speedup is
`python.wall_ms / impl.wall_ms`.

### Workload `1k_x_1k` (1 000 × 1 000)

| impl | wall_ms | ops/s | scen/s | peak_rss_KiB | speedup vs python | checksum |
|------|--------:|------:|-------:|-------------:|------------------:|---------:|
| python | 626.4 | 1.60e6 | 1.60e3 | 16380 | 1.00× | −990 |
| numpy† | 3.63 | 2.76e8 | 2.76e5 | 26024 | 173× | −990 |
| cpp_ctypes | 5.99 | 1.67e8 | 1.67e5 | 26280 | 105× | −990 |
| cpp_header | 5.52 | 1.81e8 | 1.81e5 | 612 | 113× | −990 |

### Workload `10k_x_1k` (10 000 × 1 000)

| impl | wall_ms | ops/s | scen/s | peak_rss_KiB | speedup vs python | checksum |
|------|--------:|------:|-------:|-------------:|------------------:|---------:|
| python | 6832 | 1.46e6 | 146 | 27104 | 1.00× | −9900 |
| numpy† | 15.9 | 6.27e8 | 6.27e4 | 29012 | 429× | −9900 |
| cpp_ctypes | 54.5 | 1.84e8 | 1.84e4 | 29816 | 125× | −9900 |
| cpp_header | 39.5 | 2.53e8 | 2.53e4 | 912 | 173× | −9900 |

† NumPy strength reduction — not nested-loop comparable (see caveat above).

### Readout (single-thread, this host only)

- Nested-loop C++ via ctypes is ~**100–125×** the pure-Python reference at these
 sizes, including marshalling.
- In-process `cpp_header` is slightly faster than ctypes at 10k×1k (~**173×**)
 and avoids interpreter RSS; small sizes are noisy (FFI vs cache effects).
- NumPy’s headline speedups are dominated by the **algebraic rewrite**, not by
 beating an `O(E×S)` C++ loop — treat as methodology signal for optional
 aggregate-then-scale paths, not as “NumPy beats C++” marketing.

---

## Environment caveats

- Results vary with CPU generation, thermal throttling, power mode, compiler
 (`-O3`), Python build, NumPy BLAS, and OS scheduler.
- Single-process microbench: no concurrent tenants, no QuantLib pricing, no
 DB/API, no risk-run worker.
- Peak RSS mixes interpreter + buffers + library mappings; macOS `ru_maxrss`
 is normalized to KiB by the harness.
- `cpp_ctypes` includes Python→C packing; `cpp_header` does not.
- wires LINEAR/DELTA_GAMMA approximate P&L optionally via native kernel;
 FULL_REVALUATION never uses it. Formal product claim is the **SLA-K1/K2**
 section above only (parity gate: `tests/test_historical_scenario_kernel.py`).

---

## — Parallel C++ (`std::thread` / `std::jthread` shock partitions)

**Status:** captured microbenchmark snapshot (supports SLA-K2 evidence).
**Strategy (one only):** standard-library thread pool over contiguous shock
ranges. Prefer `std::jthread` when `__cpp_lib_jthread` is defined; otherwise
`std::thread` + join-on-scope-exit. **Not OpenMP** (Apple Clang often lacks
bundled `libomp`; mixing runtimes is forbidden).
**Env:** `QUANTLINEAGE_KERNEL_THREADS` / harness `--threads N --parallel-compare`.

### Why this strategy

| Option | Decision |
|--------|----------|
| OpenMP | Rejected — extra `-fopenmp`/libomp dependency; weak Apple Clang story |
| stdlib thread pool | Chosen — C++20 toolchain only; deterministic disjoint `out[j]` writes |
| Mix both | Forbidden |

### Environment (this capture)

| Field | Value |
|-------|--------|
| Date (local) | 2026-09-02 |
| Host CPU | Intel(R) Core(TM) i7-7700HQ CPU @ 2.80GHz (4C/8T, `logical_cpus=8`) |
| OS / platform | macOS 13.7.8 (`macOS-13.7.8-x86_64-i386-64bit`) |
| Python | 3.12.14 (`backend/.venv`) |
| NumPy | 2.5.2 |
| Compiler | Apple clang 14.0.3 (`g++ -std=c++20 -O3 -pthread`) |
| Parallel | `--threads 4 --parallel-compare` (`std_thread_shock_partition`; no jthread on this libc++) |
| Power / thermal | Uncontrolled laptop session — expect run-to-run variance |

Regenerate:

```bash
backend/.venv/bin/python benchmarks/run_scenario_bench.py \
 --workload 1k_x_1k --workload 10k_x_1k --threads 4 --parallel-compare --iters 1
```

### Results table (iters=1, threads=4 vs serial)

`vs_cpp1` = serial C++ wall / parallel C++ wall for the same impl family.

#### Workload `1k_x_1k` (1 000 × 1 000)

| impl | thr | wall_ms | ops/s | speedup vs python | vs_cpp1 | checksum |
|------|----:|--------:|------:|------------------:|--------:|---------:|
| python | 1 | 624.2 | 1.60e6 | 1.00× | — | −990 |
| numpy† | 1 | 2.12 | 4.72e8 | 295× | — | −990 |
| cpp_ctypes | 1 | 10.8 | 9.26e7 | 58× | — | −990 |
| cpp_ctypes_t4 | 4 | 3.90 | 2.56e8 | 160× | **2.77×** | −990 |
| cpp_header | 1 | 2.83 | 3.53e8 | 221× | — | −990 |
| cpp_header_t4 | 4 | 1.31 | 7.62e8 | 475× | **2.16×** | −990 |

#### Workload `10k_x_1k` (10 000 × 1 000)

| impl | thr | wall_ms | ops/s | speedup vs python | vs_cpp1 | checksum |
|------|----:|--------:|------:|------------------:|--------:|---------:|
| python | 1 | 5728 | 1.75e6 | 1.00× | — | −9900 |
| numpy† | 1 | 14.4 | 6.96e8 | 399× | — | −9900 |
| cpp_ctypes | 1 | 65.2 | 1.53e8 | 88× | — | −9900 |
| cpp_ctypes_t4 | 4 | 31.1 | 3.21e8 | 184× | **2.09×** | −9900 |
| cpp_header | 1 | 40.0 | 2.50e8 | 143× | — | −9900 |
| cpp_header_t4 | 4 | 20.0 | 4.99e8 | 286× | **2.00×** | −9900 |

† NumPy strength reduction — not nested-loop comparable.

### Readout (this host only)

- With 4 workers on a 4C/8T laptop, nested-loop C++ sees ~**2.0–2.2×** wall
 speedup for in-process `cpp_header` and ~**2.1–2.8×** for ctypes (FFI packing
 still present; parallel helps the native loop portion).
- Perfect linear scaling is not expected (memory bandwidth, HT, thermal).
- Small workloads (`smoke` 64×64) may show little/no gain — thread spawn cost.
- Checksums match serial at the harness guard (`1e-6` rel) and unit tests at
 `1e-12`.

### Environment caveats (parallel)

- Do **not** set `OMP_NUM_THREADS` expecting kernel OpenMP — there is none.
- Hyperthreading / power limits / antivirus can flatten speedups.
- HTTP / 1×N Historical VaR wall time is **not** claimed from this table;
 SLA-K2 is the parallel ctypes floor only.
- macOS Apple Clang 14 used `std::thread` fallback (`QUANTLINEAGE_HAS_JTHREAD=0`);
 Linux libstdc++ typically uses `std::jthread` — same partition math either way.

---

## Related

- Formal SLA check: `benchmarks/check_m6_sla.py`
- Harness: `benchmarks/run_scenario_bench.py`
- Smoke (not a perf gate): `python3 -m pytest benchmarks/test_bench_smoke.py -q`
- Equivalence unit tests: `backend/tests/test_native_kernel.py`
- Operator notes: `benchmarks/README.md`
- Native parallel notes: `backend/native/README.md`
