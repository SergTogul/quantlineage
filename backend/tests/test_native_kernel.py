"""Equivalence tests for the optional C++ scenario kernel (M6.4/M6.5).

Coverage
- Pure-Python ABI math sanity
- C++ compile smoke (``kernel_test``)
- Native ctypes ↔ PythonScenarioKernel (serial)
- Parallel ↔ serial (stdlib thread pool)
- Edge cases: empty exposures/shocks, single shock, zeros, NaN propagation

Tolerances (M6.5)
- ABI (this module): ``KERNEL_ABI_ABS_TOL`` / ``KERNEL_ABI_REL_TOL`` = 1e-12
  (matches ``native/tests/kernel_test.cpp``)
- Risk-path NumPy ↔ native: ``KERNEL_PNL_*`` in ``app.compute.kernel`` /
  ``test_historical_scenario_kernel.py`` (M6.7 gate)

NaN / Inf policy
- Kernel does not sanitize; IEEE float ops propagate. Callers must supply
  finite exposures/shocks. Parity requires both backends to propagate equally.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.compute.kernel import (
    KERNEL_ABI_ABS_TOL,
    KERNEL_ABI_REL_TOL,
    Exposure,
    NativeScenarioKernel,
    PythonScenarioKernel,
    Shock,
)


def _approx(actual, expected):
    return actual == pytest.approx(
        expected, abs=KERNEL_ABI_ABS_TOL, rel=KERNEL_ABI_REL_TOL
    )


def test_python_kernel_math():
    e = Exposure(delta=1000, gamma=200, vega=30, dv01=-10, fx_delta=500)
    s = Shock(-0.1, 5, 20, -0.02)
    expected = 1000 * (-0.1) + 0.5 * 200 * 0.01 + 30 * 5 - 10 * 20 + 500 * (-0.02)
    assert PythonScenarioKernel().pnl([e], [s]) == pytest.approx([expected])


def test_cpp_kernel_compiles_and_executes(tmp_path):
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    root = Path(__file__).parents[1] / "native"
    exe = tmp_path / "kernel_test"
    subprocess.run(
        [
            "g++",
            "-std=c++20",
            "-O2",
            "-pthread",
            "-I",
            str(root / "include"),
            str(root / "tests/kernel_test.cpp"),
            "-o",
            str(exe),
        ],
        check=True,
    )
    result = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
    assert "risk_kernel_ok" in result.stdout


def _build_native_lib(tmp_path: Path) -> Path:
    root = Path(__file__).parents[1] / "native"
    lib = tmp_path / ("libriskkernel.dylib" if os.uname().sysname == "Darwin" else "libriskkernel.so")
    subprocess.run(
        [
            "g++",
            "-std=c++20",
            "-O3",
            "-shared",
            "-fPIC",
            "-pthread",
            "-I",
            str(root / "include"),
            str(root / "src/risk_kernel_capi.cpp"),
            "-o",
            str(lib),
        ],
        check=True,
    )
    return lib


def test_native_ctypes_kernel_matches_python(tmp_path, monkeypatch):
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    # Force serial path for a clean single-thread baseline compare.
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    lib = _build_native_lib(tmp_path)
    exposures = [Exposure(1000, 200, 30, -10, 500), Exposure(-300, 80, 10, 5, -200)]
    shocks = [Shock(-0.1, 5, 20, -0.02), Shock(0.03, -2, -10, 0.01)]
    expected = PythonScenarioKernel().pnl(exposures, shocks)
    actual = NativeScenarioKernel(lib).pnl(exposures, shocks)
    assert _approx(actual, expected)


def test_native_ctypes_parallel_matches_serial(tmp_path, monkeypatch):
    """M6.4: stdlib thread pool must match serial nested-loop results (bit-level approx)."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    lib = _build_native_lib(tmp_path)
    exposures = [
        Exposure(1000, 200, 30, -10, 500),
        Exposure(-300, 80, 10, 5, -200),
        Exposure(50, -10, 2, 1, 25),
        Exposure(10, 0, 0, -2, 3),
    ]
    shocks = [
        Shock(-0.01 + 0.0001 * k, 2.0 - 0.01 * k, 5.0 + 0.1 * k, -0.002 + 0.00005 * k)
        for k in range(256)
    ]
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    serial = NativeScenarioKernel(lib).pnl(exposures, shocks)
    for thr in ("2", "3", "4", "8"):
        monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", thr)
        # Reloading CDLL reuses the process image; env is read per call in C++.
        parallel = NativeScenarioKernel(lib).pnl(exposures, shocks)
        assert _approx(parallel, serial)


def test_native_empty_shocks_and_exposures(tmp_path, monkeypatch):
    """M6.5: empty inputs — length-0 out; zero exposures → zeros per shock."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    lib = _build_native_lib(tmp_path)
    native = NativeScenarioKernel(lib)
    py = PythonScenarioKernel()
    e = [Exposure(1.0, 2.0, 3.0, 4.0, 5.0)]
    s = [Shock(0.01, 1.0, 2.0, -0.01)]

    assert native.pnl(e, []) == []
    assert py.pnl(e, []) == []
    assert _approx(native.pnl([], s), py.pnl([], s))
    assert _approx(native.pnl([], s), [0.0])
    assert native.pnl([], []) == []
    assert py.pnl([], []) == []


def test_native_single_shock_and_zero_greeks(tmp_path, monkeypatch):
    """M6.5: one-element path (forces serial even if threads>1) and all-zero Greeks."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "4")
    lib = _build_native_lib(tmp_path)
    native = NativeScenarioKernel(lib)
    py = PythonScenarioKernel()
    exposures = [Exposure(100.0, -20.0, 5.0, -1.5, 10.0), Exposure(0.0, 0.0, 0.0, 0.0, 0.0)]
    shocks = [Shock(-0.05, 3.0, -10.0, 0.02)]
    assert _approx(native.pnl(exposures, shocks), py.pnl(exposures, shocks))
    assert _approx(native.pnl([Exposure()], [Shock(0.1, 1.0, 1.0, 0.1)]), [0.0])


def test_native_nan_propagates_like_python(tmp_path, monkeypatch):
    """M6.5: NaN is not sanitized; both backends must propagate."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    lib = _build_native_lib(tmp_path)
    exposures = [Exposure(1.0, 0.0, 0.0, 0.0, 0.0)]
    shocks = [Shock(float("nan"), 0.0, 0.0, 0.0)]
    py_out = PythonScenarioKernel().pnl(exposures, shocks)
    nat_out = NativeScenarioKernel(lib).pnl(exposures, shocks)
    assert len(py_out) == 1 and len(nat_out) == 1
    assert math.isnan(py_out[0]) and math.isnan(nat_out[0])


def test_native_multi_exposure_matrix_matches_python(tmp_path, monkeypatch):
    """M6.5: denser book × shock matrix beyond the two-row smoke case."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    lib = _build_native_lib(tmp_path)
    exposures = [
        Exposure(
            delta=10.0 * (i + 1),
            gamma=-0.5 * i,
            vega=0.1 * i,
            dv01=-0.01 * (i + 1),
            fx_delta=0.25 * i,
        )
        for i in range(32)
    ]
    shocks = [
        Shock(
            equity_return=0.001 * (j - 20),
            vol_points=0.5 * j,
            rates_bps=float(j - 10),
            fx_return=-0.0001 * j,
        )
        for j in range(64)
    ]
    expected = PythonScenarioKernel().pnl(exposures, shocks)
    actual = NativeScenarioKernel(lib).pnl(exposures, shocks)
    assert _approx(actual, expected)
