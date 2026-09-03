#!/usr/bin/env python3
"""Verify Milestone 6 formal scenario-kernel SLA floors (product-path ABI).

Runs ``run_scenario_bench.py`` on workload ``10k_x_1k`` and checks:

* SLA-K1: serial ``cpp_ctypes`` ≥ ``MIN_SERIAL_SPEEDUP_VS_PYTHON``× vs ``python``
* SLA-K2: ``cpp_ctypes_t4`` ≥ ``MIN_PARALLEL_VS_SERIAL``× vs serial ``cpp_ctypes``

Host/workload caveats and scope: ``benchmarks/RESULTS.md`` (Formal product SLA).
Exit 0 on pass, 1 on fail, 2 on harness/environment error.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "benchmarks" / "run_scenario_bench.py"
VENV_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"

# Conservative floors below documented laptop captures (see RESULTS.md).
MIN_SERIAL_SPEEDUP_VS_PYTHON = 50.0
MIN_PARALLEL_VS_SERIAL = 1.3
WORKLOAD = "10k_x_1k"
THREADS = 4


def _python() -> str:
    if VENV_PYTHON.is_file():
        return str(VENV_PYTHON)
    return sys.executable


def main() -> int:
    cmd = [
        _python(),
        str(HARNESS),
        "--workload",
        WORKLOAD,
        "--threads",
        str(THREADS),
        "--parallel-compare",
        "--iters",
        "1",
        "--json",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(f"error: failed to launch harness: {exc}", file=sys.stderr)
        return 2

    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        print(f"error: harness exited {proc.returncode}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f"error: harness JSON parse failed: {exc}", file=sys.stderr)
        print(proc.stdout[:2000], file=sys.stderr)
        return 2

    by_impl = {
        r["impl"]: r
        for r in payload.get("results", [])
        if r.get("workload") == WORKLOAD
    }
    serial = by_impl.get("cpp_ctypes")
    parallel = by_impl.get(f"cpp_ctypes_t{THREADS}")
    python = by_impl.get("python")

    if not serial or not python:
        print(
            f"error: missing python/cpp_ctypes rows for {WORKLOAD}; got {sorted(by_impl)}",
            file=sys.stderr,
        )
        return 2

    serial_speedup = serial.get("speedup_vs_python")
    if serial_speedup is None:
        py_ms = float(python["wall_ms"])
        serial_speedup = py_ms / float(serial["wall_ms"]) if serial["wall_ms"] else 0.0

    print("M6 formal scenario-kernel SLA check")
    print(f"  workload: {WORKLOAD}")
    env = payload.get("environment", {})
    print(f"  platform: {env.get('platform')}")
    print(f"  gxx: {env.get('gxx')}")
    print(
        f"  SLA-K1: cpp_ctypes vs python = {serial_speedup:.2f}× "
        f"(floor ≥ {MIN_SERIAL_SPEEDUP_VS_PYTHON:.0f}×); "
        f"wall_ms={serial['wall_ms']:.1f}"
    )

    ok = True
    if float(serial_speedup) < MIN_SERIAL_SPEEDUP_VS_PYTHON:
        print("  FAIL SLA-K1", file=sys.stderr)
        ok = False
    else:
        print("  PASS SLA-K1")

    if not parallel:
        print(
            f"  error: missing cpp_ctypes_t{THREADS} row for SLA-K2",
            file=sys.stderr,
        )
        return 2

    vs_serial = parallel.get("speedup_vs_cpp_serial")
    if vs_serial is None:
        vs_serial = (
            float(serial["wall_ms"]) / float(parallel["wall_ms"])
            if parallel["wall_ms"]
            else 0.0
        )
    print(
        f"  SLA-K2: cpp_ctypes_t{THREADS} vs serial = {float(vs_serial):.2f}× "
        f"(floor ≥ {MIN_PARALLEL_VS_SERIAL:.1f}×); "
        f"wall_ms={parallel['wall_ms']:.1f}"
    )
    if float(vs_serial) < MIN_PARALLEL_VS_SERIAL:
        print("  FAIL SLA-K2", file=sys.stderr)
        ok = False
    else:
        print("  PASS SLA-K2")

    if ok:
        print("RESULT: PASS")
        return 0
    print("RESULT: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
