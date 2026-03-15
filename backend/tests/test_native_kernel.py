"""Equivalence tests for the optional C++ scenario kernel (M6.4/M6.5 / R0.12.5).

Coverage
- Pure-Python ABI math sanity
- C++ compile smoke (``kernel_test``)
- Native ctypes ↔ PythonScenarioKernel (serial)
- Parallel ↔ serial (stdlib thread pool)
- Edge cases: empty exposures/shocks, single shock, zeros, NaN propagation
- R0.12.5 ABI version, error codes, length mismatch, wrap/tight-buffer, null/empty policy
- R0.17 contiguous NumPy buffer path (no pack copy) and tiny-work serial policy

Tolerances (M6.5)
- ABI (this module): ``KERNEL_ABI_ABS_TOL`` / ``KERNEL_ABI_REL_TOL`` = 1e-12
  (matches ``native/tests/kernel_test.cpp``)
- Risk-path NumPy ↔ native: ``KERNEL_PNL_*`` in ``app.compute.kernel`` /
  ``test_historical_scenario_kernel.py`` (M6.7 gate)

NaN / Inf policy
- Kernel does not sanitize; IEEE float ops propagate. Callers must supply
  finite exposures/shocks. Parity requires both backends to propagate equally.

Null / empty policy (C ABI)
- Count == 0: pointer may be NULL; no dereference.
- ``n_shocks == 0``: success, no writes (``out`` may be NULL).
- ``n_exposures == 0`` and ``n_shocks > 0``: write 0.0 per shock.
- Count > 0 and pointer is NULL: ``KERNEL_ERR_NULL`` (out buffer unchanged).
- Length mismatch vs stride / ``n_out``: ``KERNEL_ERR_LENGTH`` (no overrun).
- Wrap-sized ``n_exposures`` / ``n_shocks`` (``SIZE_MAX/stride+1``): ``KERNEL_ERR_LENGTH``.
- Tight-buffer mismatch: skipped length predicate is an overrun under ASan.
"""

from __future__ import annotations

import ctypes
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import numpy as np

from app.compute.kernel import (
    KERNEL_ABI_ABS_TOL,
    KERNEL_ABI_REL_TOL,
    KERNEL_ABI_VERSION,
    KERNEL_ERR_ABI,
    KERNEL_ERR_LENGTH,
    KERNEL_ERR_NULL,
    KERNEL_OK,
    KERNEL_PARALLEL_MIN_WORK,
    Exposure,
    NativeKernelError,
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
            str(root / "src/risk_kernel_capi.cpp"),
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
        for k in range(2048)
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


def test_native_abi_version_readable(tmp_path):
    """R0.12.5: Python bridge can read the exported ABI version."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    lib = _build_native_lib(tmp_path)
    native = NativeScenarioKernel(lib)
    assert KERNEL_ABI_VERSION == 1
    assert native.abi_version == KERNEL_ABI_VERSION
    raw = ctypes.CDLL(str(lib))
    raw.riskforge_kernel_abi_version.argtypes = []
    raw.riskforge_kernel_abi_version.restype = ctypes.c_int
    assert raw.riskforge_kernel_abi_version() == KERNEL_ABI_VERSION


def test_native_constructor_rejects_abi_mismatch(tmp_path, monkeypatch):
    """R0.12.5: a stale Python ABI expectation must fail closed at load."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    lib = _build_native_lib(tmp_path)
    monkeypatch.setattr("app.compute.kernel.KERNEL_ABI_VERSION", 99)
    with pytest.raises(NativeKernelError) as exc:
        NativeScenarioKernel(lib)
    assert exc.value.code == KERNEL_ERR_ABI


def test_native_wrong_abi_arg_fails_closed(tmp_path, monkeypatch):
    """R0.12.5: compute entry rejects a mismatched ABI argument and does not write."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    e = (ctypes.c_double * 5)(1000.0, 200.0, 30.0, -10.0, 500.0)
    s = (ctypes.c_double * 4)(-0.1, 5.0, 20.0, -0.02)
    out = (ctypes.c_double * 1)(99.0)
    rc = native.fn(0, e, 1, 5, s, 1, 4, out, 1)
    assert rc == KERNEL_ERR_ABI
    assert out[0] == 99.0


def test_native_length_mismatch_fails_closed(tmp_path, monkeypatch):
    """R0.12.5: mismatched exposure/shock/out lengths return an error, no overrun."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    e = (ctypes.c_double * 5)(1000.0, 200.0, 30.0, -10.0, 500.0)
    s = (ctypes.c_double * 4)(-0.1, 5.0, 20.0, -0.02)
    out = (ctypes.c_double * 1)(99.0)

    rc = native.fn(KERNEL_ABI_VERSION, e, 1, 4, s, 1, 4, out, 1)
    assert rc == KERNEL_ERR_LENGTH
    assert out[0] == 99.0

    rc = native.fn(KERNEL_ABI_VERSION, e, 1, 5, s, 1, 3, out, 1)
    assert rc == KERNEL_ERR_LENGTH
    assert out[0] == 99.0

    rc = native.fn(KERNEL_ABI_VERSION, e, 1, 5, s, 1, 4, out, 0)
    assert rc == KERNEL_ERR_LENGTH
    assert out[0] == 99.0


def _size_max() -> int:
    return (1 << (ctypes.sizeof(ctypes.c_size_t) * 8)) - 1


def test_native_wrap_sized_counts_fail_closed(tmp_path, monkeypatch):
    """R0.12.5: wrap-sized n_exposures/n_shocks must ERR_LENGTH without a huge alloc.

    SIZE_MAX/5+1 makes *5 wrap to 4; SIZE_MAX/4+1 makes *4 wrap to 0. Passing
    those wrapped products as n_*_doubles (and n_out == wrap n_shocks) means a
    deleted overflow guard would treat lengths as matching and walk huge n_*.
    """
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    e = (ctypes.c_double * 5)(1000.0, 200.0, 30.0, -10.0, 500.0)
    s = (ctypes.c_double * 4)(-0.1, 5.0, 20.0, -0.02)
    out = (ctypes.c_double * 1)(99.0)
    size_max = _size_max()
    wrap_exposures = size_max // 5 + 1
    wrap_shocks = size_max // 4 + 1

    rc = native.fn(KERNEL_ABI_VERSION, e, wrap_exposures, 4, s, 1, 4, out, 1)
    assert rc == KERNEL_ERR_LENGTH
    assert out[0] == 99.0

    rc = native.fn(KERNEL_ABI_VERSION, e, 1, 5, s, wrap_shocks, 0, out, wrap_shocks)
    assert rc == KERNEL_ERR_LENGTH
    assert out[0] == 99.0


def test_native_tight_buffer_mismatch_fails_closed(tmp_path, monkeypatch):
    """R0.12.5: tight out/exposure buffers so a skipped predicate is an ASan overrun."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    e = (ctypes.c_double * 5)(1000.0, 200.0, 30.0, -10.0, 500.0)
    two_s = (ctypes.c_double * 8)(-0.1, 5.0, 20.0, -0.02, 0.03, -2.0, -10.0, 0.01)
    out = (ctypes.c_double * 1)(99.0)

    rc = native.fn(KERNEL_ABI_VERSION, e, 1, 5, two_s, 2, 8, out, 1)
    assert rc == KERNEL_ERR_LENGTH
    assert out[0] == 99.0

    rc = native.fn(KERNEL_ABI_VERSION, e, 2, 5, two_s, 1, 4, out, 1)
    assert rc == KERNEL_ERR_LENGTH
    assert out[0] == 99.0


def test_native_null_pointer_nonzero_count_fails_closed(tmp_path, monkeypatch):
    """R0.12.5: NULL + count > 0 is an error; out is not written."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    s = (ctypes.c_double * 4)(-0.1, 5.0, 20.0, -0.02)
    out = (ctypes.c_double * 1)(99.0)
    rc = native.fn(KERNEL_ABI_VERSION, None, 1, 5, s, 1, 4, out, 1)
    assert rc == KERNEL_ERR_NULL
    assert out[0] == 99.0

    e = (ctypes.c_double * 5)(1.0, 0.0, 0.0, 0.0, 0.0)
    rc = native.fn(KERNEL_ABI_VERSION, e, 1, 5, None, 1, 4, out, 1)
    assert rc == KERNEL_ERR_NULL
    assert out[0] == 99.0

    rc = native.fn(KERNEL_ABI_VERSION, e, 1, 5, s, 1, 4, None, 1)
    assert rc == KERNEL_ERR_NULL


def test_native_empty_null_pointers_ok(tmp_path, monkeypatch):
    """R0.12.5: count == 0 may pass NULL; empty book writes zeros per shock."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    rc = native.fn(KERNEL_ABI_VERSION, None, 0, 0, None, 0, 0, None, 0)
    assert rc == KERNEL_OK

    s = (ctypes.c_double * 4)(0.01, 1.0, 2.0, -0.01)
    out = (ctypes.c_double * 1)(99.0)
    rc = native.fn(KERNEL_ABI_VERSION, None, 0, 0, s, 1, 4, out, 1)
    assert rc == KERNEL_OK
    assert out[0] == 0.0


def _ptr_addr(p) -> int | None:
    if not p:
        return None
    return ctypes.cast(p, ctypes.c_void_p).value


def _spy_native_fn(native: NativeScenarioKernel) -> list[dict]:
    """Capture buffer addresses passed into the C ABI (proves no extra copy)."""
    captured: list[dict] = []
    orig = native.fn

    def spy(abi, exposures, n_e, n_ed, shocks, n_s, n_sd, out, n_out):
        captured.append(
            {
                "e": _ptr_addr(exposures),
                "s": _ptr_addr(shocks),
                "o": _ptr_addr(out),
            }
        )
        return orig(abi, exposures, n_e, n_ed, shocks, n_s, n_sd, out, n_out)

    native.fn = spy
    return captured


def test_native_contiguous_numpy_no_copy_matches_python(tmp_path, monkeypatch):
    """R0.17: C-contiguous float64 buffers go to the kernel without a pack copy."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    exposures = [
        Exposure(1000, 200, 30, -10, 500),
        Exposure(-300, 80, 10, 5, -200),
    ]
    shocks = [Shock(-0.1, 5, 20, -0.02), Shock(0.03, -2, -10, 0.01)]
    e = np.array(
        [[1000.0, 200.0, 30.0, -10.0, 500.0], [-300.0, 80.0, 10.0, 5.0, -200.0]],
        dtype=np.float64,
    )
    s = np.array(
        [[-0.1, 5.0, 20.0, -0.02], [0.03, -2.0, -10.0, 0.01]],
        dtype=np.float64,
    )
    assert e.flags.c_contiguous and s.flags.c_contiguous
    captured = _spy_native_fn(native)
    actual = native.pnl_from_arrays(e, s)
    assert captured, "native ABI must be invoked"
    assert captured[0]["e"] == e.ctypes.data
    assert captured[0]["s"] == s.ctypes.data
    expected = PythonScenarioKernel().pnl(exposures, shocks)
    assert _approx(actual.tolist(), expected)
    assert _approx(actual.tolist(), native.pnl(exposures, shocks))


def test_native_flat_1d_contiguous_numpy_no_copy(tmp_path, monkeypatch):
    """R0.17: packed 1-D C-contiguous float64 is the same ABI layout, no copy."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    e = np.array([1000.0, 200.0, 30.0, -10.0, 500.0], dtype=np.float64)
    s = np.array([-0.1, 5.0, 20.0, -0.02], dtype=np.float64)
    captured = _spy_native_fn(native)
    actual = native.pnl_from_arrays(e, s)
    assert captured[0]["e"] == e.ctypes.data
    assert captured[0]["s"] == s.ctypes.data
    expected = PythonScenarioKernel().pnl(
        [Exposure(1000, 200, 30, -10, 500)], [Shock(-0.1, 5, 20, -0.02)]
    )
    assert _approx(actual.tolist(), expected)


def test_native_numpy_out_buffer_no_copy(tmp_path, monkeypatch):
    """R0.17: caller-supplied C-contiguous float64 out is written in place."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    e = np.array([[1000.0, 200.0, 30.0, -10.0, 500.0]], dtype=np.float64)
    s = np.array([[-0.1, 5.0, 20.0, -0.02]], dtype=np.float64)
    out = np.full(1, 99.0, dtype=np.float64)
    captured = _spy_native_fn(native)
    result = native.pnl_from_arrays(e, s, out=out)
    assert result is out
    assert captured[0]["o"] == out.ctypes.data
    expected = PythonScenarioKernel().pnl(
        [Exposure(1000, 200, 30, -10, 500)], [Shock(-0.1, 5, 20, -0.02)]
    )
    assert _approx(out.tolist(), expected)


def test_native_noncontiguous_numpy_matches_python(tmp_path, monkeypatch):
    """R0.17: Fortran / strided arrays still match; they may copy."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    e_c = np.array(
        [[1000.0, 200.0, 30.0, -10.0, 500.0], [-300.0, 80.0, 10.0, 5.0, -200.0]],
        dtype=np.float64,
    )
    s_c = np.array(
        [[-0.1, 5.0, 20.0, -0.02], [0.03, -2.0, -10.0, 0.01]],
        dtype=np.float64,
    )
    e_f = np.asfortranarray(e_c)
    s_f = np.asfortranarray(s_c)
    assert not e_f.flags.c_contiguous
    assert not s_f.flags.c_contiguous
    captured = _spy_native_fn(native)
    actual = native.pnl_from_arrays(e_f, s_f)
    assert captured[0]["e"] != e_f.ctypes.data
    assert captured[0]["s"] != s_f.ctypes.data
    expected = PythonScenarioKernel().pnl(
        [Exposure(1000, 200, 30, -10, 500), Exposure(-300, 80, 10, 5, -200)],
        [Shock(-0.1, 5, 20, -0.02), Shock(0.03, -2, -10, 0.01)],
    )
    assert _approx(actual.tolist(), expected)


def test_native_numpy_empty_and_shape_mismatch(tmp_path, monkeypatch):
    """R0.17: empty arrays follow the ABI; wrong stride is KERNEL_ERR_LENGTH."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "1")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    e = np.zeros((0, 5), dtype=np.float64)
    s = np.array([[0.01, 1.0, 2.0, -0.01]], dtype=np.float64)
    assert _approx(native.pnl_from_arrays(e, s).tolist(), [0.0])
    assert native.pnl_from_arrays(e, np.zeros((0, 4), dtype=np.float64)).tolist() == []

    bad = np.zeros((2, 3), dtype=np.float64)
    with pytest.raises(NativeKernelError) as exc:
        native.pnl_from_arrays(bad, s)
    assert exc.value.code == KERNEL_ERR_LENGTH


def test_native_tiny_workload_matches_python_with_many_threads(tmp_path, monkeypatch):
    """R0.17: 1×S Historical-VaR shape stays correct when THREADS>1 (serial path)."""
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    assert KERNEL_PARALLEL_MIN_WORK == 4096
    monkeypatch.setenv("RISKFORGE_KERNEL_THREADS", "8")
    native = NativeScenarioKernel(_build_native_lib(tmp_path))
    exposures = [Exposure(1000, 200, 30, -10, 500)]
    shocks = [Shock(-0.01 + 0.0001 * k, 2.0, 5.0, -0.002) for k in range(64)]
    assert 1 * 64 < KERNEL_PARALLEL_MIN_WORK
    expected = PythonScenarioKernel().pnl(exposures, shocks)
    assert _approx(native.pnl(exposures, shocks), expected)
    e = np.array([[1000.0, 200.0, 30.0, -10.0, 500.0]], dtype=np.float64)
    s = np.array(
        [[-0.01 + 0.0001 * k, 2.0, 5.0, -0.002] for k in range(64)],
        dtype=np.float64,
    )
    assert _approx(native.pnl_from_arrays(e, s).tolist(), expected)

