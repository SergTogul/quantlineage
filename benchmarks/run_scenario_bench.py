#!/usr/bin/env python3
"""Reproducible scenario-aggregation benchmark harness (M6.1 / M6.2 / M6.4).

Compares Python reference, optional NumPy, ctypes native C ABI, and the
standalone C++ header binary under ``backend/native/src/benchmark.cpp``.

All implementations share identical I/O semantics (see
``benchmarks/RESULTS.md``): ``list[Exposure]`` × ``list[Shock]`` →
``list[float]`` portfolio scenario PnL of length ``len(shocks)``.

M6.2 baseline: single-thread (``--threads 1`` / ``RISKFORGE_KERNEL_THREADS=1``).
M6.4: C++ ``std::jthread`` shock-partition pool — compare serial vs parallel
with ``--threads N`` (no OpenMP; do not mix strategies).

Not an HTTP/API latency claim. Product LINEAR/DELTA_GAMMA may opt into the same
ctypes kernel via RISKFORGE_SCENARIO_KERNEL (M6.3). Formal relative floors are
documented in ``benchmarks/RESULTS.md`` (SLA-K1/K2) and checked by
``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NATIVE_ROOT = REPO_ROOT / "backend" / "native"
BACKEND_ROOT = REPO_ROOT / "backend"

# Ensure ``app.compute.kernel`` is importable without installing a package.
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.compute.kernel import (  # noqa: E402
    Exposure,
    NativeScenarioKernel,
    PythonScenarioKernel,
    Shock,
)

WORKLOADS = {
    "smoke": {"n_exposures": 64, "n_shocks": 64},
    "1k_x_1k": {"n_exposures": 1_000, "n_shocks": 1_000},
    "10k_x_1k": {"n_exposures": 10_000, "n_shocks": 1_000},
    "50k_x_1k": {"n_exposures": 50_000, "n_shocks": 1_000},
}


@dataclass
class BenchResult:
    workload: str
    impl: str
    n_exposures: int
    n_shocks: int
    iters: int
    wall_ms: float
    throughput_ops_per_s: float
    scenarios_per_s: float
    peak_rss_kib: float | None
    checksum: float
    threads: int | None = None
    speedup_vs_python: float | None = None
    speedup_vs_cpp_serial: float | None = None


def _peak_rss_kib() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss = float(usage.ru_maxrss)
    if sys.platform == "darwin":
        return rss / 1024.0  # bytes → KiB
    return rss  # Linux: already KiB


def _make_inputs(n_exposures: int, n_shocks: int) -> tuple[list[Exposure], list[Shock]]:
    # Deterministic constants matching the C++ microbenchmark defaults.
    exposures = [
        Exposure(delta=1000.0, gamma=200.0, vega=30.0, dv01=-10.0, fx_delta=500.0)
        for _ in range(n_exposures)
    ]
    shocks = [
        Shock(equity_return=-0.01, vol_points=2.0, rates_bps=5.0, fx_return=-0.002)
        for _ in range(n_shocks)
    ]
    return exposures, shocks


def numpy_pnl(exposures: list[Exposure], shocks: list[Shock]) -> list[float]:
    """NumPy path with identical I/O to ``PythonScenarioKernel.pnl``.

    Same contract: exposures × shocks → list[float] of length ``len(shocks)``.
    Numerically equivalent under the linear-in-exposures kernel, but uses an
    algebraic **strength reduction** (sum exposures once, then scale by each
    shock) so asymptotic work is ``O(E + S)`` after packing, not nested
    ``O(E × S)``. Do not treat NumPy speedups as fair loop-vs-loop evidence
    against Python/C++; see ``benchmarks/RESULTS.md``.
    """
    import numpy as np

    e = np.asarray(
        [[x.delta, x.gamma, x.vega, x.dv01, x.fx_delta] for x in exposures],
        dtype=np.float64,
    )
    s = np.asarray(
        [[x.equity_return, x.vol_points, x.rates_bps, x.fx_return] for x in shocks],
        dtype=np.float64,
    )
    d_sum, g_sum, v_sum, r_sum, fx_sum = e.sum(axis=0)
    er = s[:, 0]
    return (
        d_sum * er
        + 0.5 * g_sum * er * er
        + v_sum * s[:, 1]
        + r_sum * s[:, 2]
        + fx_sum * s[:, 3]
    ).tolist()


def _time_kernel(fn, exposures, shocks, iters: int) -> tuple[list[float], float, float]:
    # Warmup
    out = fn(exposures, shocks)
    rss_before = _peak_rss_kib()
    t0 = time.perf_counter()
    for _ in range(iters):
        out = fn(exposures, shocks)
    t1 = time.perf_counter()
    rss_after = _peak_rss_kib()
    wall_ms = (t1 - t0) * 1000.0
    return out, wall_ms, max(rss_before, rss_after)


def _metrics(
    workload: str,
    impl: str,
    n_exposures: int,
    n_shocks: int,
    iters: int,
    wall_ms: float,
    peak_rss_kib: float | None,
    checksum: float,
    threads: int | None = None,
) -> BenchResult:
    elapsed_s = wall_ms / 1000.0
    ops = float(n_exposures) * float(n_shocks) * float(iters)
    return BenchResult(
        workload=workload,
        impl=impl,
        n_exposures=n_exposures,
        n_shocks=n_shocks,
        iters=iters,
        wall_ms=wall_ms,
        throughput_ops_per_s=(ops / elapsed_s) if elapsed_s > 0 else 0.0,
        scenarios_per_s=((n_shocks * iters) / elapsed_s) if elapsed_s > 0 else 0.0,
        peak_rss_kib=peak_rss_kib,
        checksum=checksum,
        threads=threads,
    )


def _cxx_common_flags() -> list[str]:
    return ["g++", "-std=c++20", "-O3", "-pthread", "-I", str(NATIVE_ROOT / "include")]


def build_native_library(build_dir: Path) -> Path:
    lib = build_dir / ("libriskkernel.dylib" if sys.platform == "darwin" else "libriskkernel.so")
    src = NATIVE_ROOT / "src" / "risk_kernel_capi.cpp"
    cmd = [*_cxx_common_flags(), "-shared", "-fPIC", str(src), "-o", str(lib)]
    subprocess.run(cmd, check=True)
    return lib


def build_cpp_bench(build_dir: Path) -> Path:
    exe = build_dir / "scenario_bench"
    src = NATIVE_ROOT / "src" / "benchmark.cpp"
    cmd = [*_cxx_common_flags(), str(src), "-o", str(exe)]
    subprocess.run(cmd, check=True)
    return exe


def run_cpp_binary(
    exe: Path, n_exposures: int, n_shocks: int, iters: int, threads: int
) -> BenchResult:
    proc = subprocess.run(
        [
            str(exe),
            "--exposures",
            str(n_exposures),
            "--shocks",
            str(n_shocks),
            "--iters",
            str(iters),
            "--threads",
            str(threads),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    resolved = int(payload.get("threads_resolved", threads))
    return _metrics(
        workload="",  # filled by caller
        impl="cpp_header" if threads <= 1 else f"cpp_header_t{resolved}",
        n_exposures=int(payload["n_exposures"]),
        n_shocks=int(payload["n_shocks"]),
        iters=int(payload["iters"]),
        wall_ms=float(payload["wall_ms"]),
        peak_rss_kib=float(payload["peak_rss_kib"]),
        checksum=float(payload["checksum"]),
        threads=resolved,
    )


def environment_block(threads: int) -> dict:
    numpy_version: str | None
    try:
        import numpy as np

        numpy_version = np.__version__
    except ImportError:
        numpy_version = None
    milestone = "M6.4" if threads != 1 else "M6.2"
    threading = (
        "single-thread (RISKFORGE_KERNEL_THREADS=1; stdlib thread pool idle)"
        if threads == 1
        else (
            f"std::thread shock-partition pool "
            f"(requested={threads}; jthread if libc++ supports it; no OpenMP)"
        )
    )
    return {
        "milestone": milestone,
        "threading": threading,
        "parallel_strategy": "std_thread_shock_partition",
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "numpy": numpy_version,
        "gxx": _gxx_version(),
        "riskforge_kernel_threads": os.environ.get("RISKFORGE_KERNEL_THREADS"),
        "bench_threads": threads,
        "logical_cpus": os.cpu_count(),
        "note": (
            "Wall times and speedups are environment-specific microbenchmarks. "
            "They are not production SLAs, not multi-tenant load tests, and not "
            "claims about end-to-end risk-run latency. NumPy uses strength "
            "reduction (see RESULTS.md); apples-to-apples loop comparison is "
            "python vs cpp_ctypes vs cpp_header. Parallel C++ uses only a "
            "std::thread/std::jthread shock-partition pool (never OpenMP)."
        ),
    }


def _gxx_version() -> str | None:
    gxx = shutil.which("g++")
    if not gxx:
        return None
    try:
        out = subprocess.run([gxx, "--version"], capture_output=True, text=True, check=True)
        return out.stdout.splitlines()[0]
    except (OSError, subprocess.CalledProcessError):
        return gxx


def run_workload(
    name: str,
    n_exposures: int,
    n_shocks: int,
    iters: int,
    *,
    build_dir: Path,
    include_numpy: bool,
    include_native: bool,
    include_cpp: bool,
    threads: int,
    parallel_compare: bool,
) -> list[BenchResult]:
    exposures, shocks = _make_inputs(n_exposures, n_shocks)
    results: list[BenchResult] = []

    # Python / NumPy stay single-threaded reference math (not the C++ pool).
    py_out, py_ms, py_rss = _time_kernel(
        PythonScenarioKernel().pnl, exposures, shocks, iters
    )
    py = _metrics(name, "python", n_exposures, n_shocks, iters, py_ms, py_rss, py_out[0], 1)
    results.append(py)

    if include_numpy:
        try:
            np_out, np_ms, np_rss = _time_kernel(numpy_pnl, exposures, shocks, iters)
            # Equivalence guard (same numerical contract as unit tests).
            if abs(np_out[0] - py_out[0]) > 1e-6 * max(1.0, abs(py_out[0])):
                raise RuntimeError(
                    f"NumPy checksum mismatch: {np_out[0]} vs python {py_out[0]}"
                )
            r = _metrics(
                name, "numpy", n_exposures, n_shocks, iters, np_ms, np_rss, np_out[0], 1
            )
            r.speedup_vs_python = py.wall_ms / r.wall_ms if r.wall_ms > 0 else None
            results.append(r)
        except ImportError:
            print("warning: numpy unavailable; skipping numpy impl", file=sys.stderr)

    cpp_serial_wall: float | None = None

    if include_native:
        lib = build_native_library(build_dir)
        thread_sets = [1]
        if parallel_compare and threads > 1:
            thread_sets.append(threads)
        elif threads > 1:
            thread_sets = [threads]

        for thr in thread_sets:
            os.environ["RISKFORGE_KERNEL_THREADS"] = str(thr)
            native = NativeScenarioKernel(lib)
            n_out, n_ms, n_rss = _time_kernel(native.pnl, exposures, shocks, iters)
            if abs(n_out[0] - py_out[0]) > 1e-6 * max(1.0, abs(py_out[0])):
                raise RuntimeError(
                    f"Native checksum mismatch: {n_out[0]} vs python {py_out[0]}"
                )
            impl = "cpp_ctypes" if thr <= 1 else f"cpp_ctypes_t{thr}"
            r = _metrics(
                name, impl, n_exposures, n_shocks, iters, n_ms, n_rss, n_out[0], thr
            )
            r.speedup_vs_python = py.wall_ms / r.wall_ms if r.wall_ms > 0 else None
            if thr <= 1:
                cpp_serial_wall = r.wall_ms
            elif cpp_serial_wall and r.wall_ms > 0:
                r.speedup_vs_cpp_serial = cpp_serial_wall / r.wall_ms
            results.append(r)

    if include_cpp:
        exe = build_cpp_bench(build_dir)
        thread_sets = [1]
        if parallel_compare and threads > 1:
            thread_sets.append(threads)
        elif threads > 1:
            thread_sets = [threads]

        header_serial_wall: float | None = None
        for thr in thread_sets:
            r = run_cpp_binary(exe, n_exposures, n_shocks, iters, thr)
            r.workload = name
            if thr <= 1:
                r.impl = "cpp_header"
                header_serial_wall = r.wall_ms
            r.speedup_vs_python = py.wall_ms / r.wall_ms if r.wall_ms > 0 else None
            if thr > 1 and header_serial_wall and r.wall_ms > 0:
                r.speedup_vs_cpp_serial = header_serial_wall / r.wall_ms
            results.append(r)

    return results


def _print_table(results: list[BenchResult]) -> None:
    headers = (
        "workload",
        "impl",
        "thr",
        "wall_ms",
        "ops/s",
        "scen/s",
        "rss_kib",
        "vs_py",
        "vs_cpp1",
        "checksum",
    )
    rows = [headers]
    for r in results:
        rows.append(
            (
                r.workload,
                r.impl,
                str(r.threads) if r.threads is not None else "-",
                f"{r.wall_ms:.3f}",
                f"{r.throughput_ops_per_s:.3e}",
                f"{r.scenarios_per_s:.3e}",
                f"{r.peak_rss_kib:.0f}" if r.peak_rss_kib is not None else "-",
                f"{r.speedup_vs_python:.2f}x" if r.speedup_vs_python else "1.00x",
                (
                    f"{r.speedup_vs_cpp_serial:.2f}x"
                    if r.speedup_vs_cpp_serial
                    else "-"
                ),
                f"{r.checksum:.6g}",
            )
        )
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(headers))]
    for row in rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workload",
        action="append",
        choices=sorted(WORKLOADS.keys()),
        help="Workload name (repeatable). Default: 1k_x_1k and 10k_x_1k.",
    )
    parser.add_argument("--iters", type=int, default=1, help="Timed iterations per impl")
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    parser.add_argument("--skip-numpy", action="store_true")
    parser.add_argument("--skip-native", action="store_true")
    parser.add_argument("--skip-cpp", action="store_true")
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help=(
            "C++ worker threads (1=serial M6.2 baseline; >1 enables stdlib thread pool). "
            "Default 1."
        ),
    )
    parser.add_argument(
        "--parallel-compare",
        action="store_true",
        help="When --threads>1, also time serial (threads=1) and report vs_cpp1 speedup.",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="Directory for compiled artifacts (default: temp dir)",
    )
    args = parser.parse_args(argv)

    if args.threads < 1:
        print("error: --threads must be >= 1", file=sys.stderr)
        return 2

    if not args.skip_native or not args.skip_cpp:
        if not shutil.which("g++"):
            print(
                "error: g++ required for native/cpp impls (or pass --skip-native --skip-cpp)",
                file=sys.stderr,
            )
            return 2

    names = args.workload or ["1k_x_1k", "10k_x_1k"]
    build_dir = args.build_dir
    tmp: tempfile.TemporaryDirectory[str] | None = None
    if build_dir is None:
        tmp = tempfile.TemporaryDirectory(prefix="riskforge-bench-")
        build_dir = Path(tmp.name)
    else:
        build_dir.mkdir(parents=True, exist_ok=True)

    # Align env with requested serial baseline when not comparing.
    if args.threads == 1 and not args.parallel_compare:
        os.environ["RISKFORGE_KERNEL_THREADS"] = "1"

    all_results: list[BenchResult] = []
    try:
        for name in names:
            sizes = WORKLOADS[name]
            all_results.extend(
                run_workload(
                    name,
                    sizes["n_exposures"],
                    sizes["n_shocks"],
                    args.iters,
                    build_dir=build_dir,
                    include_numpy=not args.skip_numpy,
                    include_native=not args.skip_native,
                    include_cpp=not args.skip_cpp,
                    threads=args.threads,
                    parallel_compare=args.parallel_compare,
                )
            )
    finally:
        if tmp is not None:
            tmp.cleanup()

    report = {
        "environment": environment_block(args.threads),
        "results": [asdict(r) for r in all_results],
    }

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        title = (
            "RiskForge scenario-aggregation microbenchmark (M6.4 parallel C++)"
            if args.threads > 1 or args.parallel_compare
            else "RiskForge scenario-aggregation microbenchmark (M6.2 single-thread)"
        )
        print(title)
        print("I/O + caveats: benchmarks/RESULTS.md — not a production claim.")
        for k, v in report["environment"].items():
            print(f"  {k}: {v}")
        print()
        _print_table(all_results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
