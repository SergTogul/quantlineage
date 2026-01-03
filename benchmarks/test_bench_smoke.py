"""Smoke test for the M6.1/M6.2 benchmark harness (not a performance gate)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "benchmarks" / "run_scenario_bench.py"


@pytest.mark.skipif(not shutil.which("g++"), reason="g++ unavailable")
def test_scenario_bench_smoke_json():
    proc = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workload",
            "smoke",
            "--iters",
            "1",
            "--json",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert "environment" in report
    env = report["environment"]
    assert "note" in env
    assert env.get("milestone") in {"M6.2", "M6.4"}
    assert env.get("parallel_strategy") == "std_thread_shock_partition"
    assert "single-thread" in (env.get("threading") or "")
    impls = {row["impl"] for row in report["results"]}
    assert "python" in impls
    assert "cpp_ctypes" in impls
    assert "cpp_header" in impls
    for row in report["results"]:
        assert row["workload"] == "smoke"
        assert row["wall_ms"] >= 0
        assert row["throughput_ops_per_s"] >= 0
        assert row["n_exposures"] == 64
        assert row["n_shocks"] == 64


@pytest.mark.skipif(not shutil.which("g++"), reason="g++ unavailable")
def test_scenario_bench_parallel_compare_smoke():
    """M6.4: serial + stdlib thread pool share checksum; vs_cpp1 reported for parallel."""
    n_cpu = os.cpu_count() or 2
    thr = min(4, max(2, n_cpu))
    proc = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workload",
            "smoke",
            "--iters",
            "1",
            "--threads",
            str(thr),
            "--parallel-compare",
            "--json",
            "--skip-numpy",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["environment"].get("milestone") == "M6.4"
    assert report["environment"].get("parallel_strategy") == "std_thread_shock_partition"
    by_impl = {row["impl"]: row for row in report["results"]}
    assert "cpp_header" in by_impl
    parallel_headers = [r for r in report["results"] if r["impl"].startswith("cpp_header_t")]
    assert parallel_headers, report["results"]
    serial_cs = by_impl["cpp_header"]["checksum"]
    for row in parallel_headers:
        assert abs(row["checksum"] - serial_cs) <= 1e-6 * max(1.0, abs(serial_cs))
        assert row.get("speedup_vs_cpp_serial") is not None


def test_cpp_benchmark_cli_help(tmp_path):
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    native = REPO / "backend" / "native"
    exe = tmp_path / "scenario_bench"
    subprocess.run(
        [
            "g++",
            "-std=c++20",
            "-O2",
            "-pthread",
            "-I",
            str(native / "include"),
            str(native / "src" / "benchmark.cpp"),
            "-o",
            str(exe),
        ],
        check=True,
    )
    help_proc = subprocess.run(
        [str(exe), "--help"], capture_output=True, text=True, check=True
    )
    assert "exposures" in help_proc.stdout + help_proc.stderr
    assert "threads" in help_proc.stdout + help_proc.stderr
