"""Optional linear Δ-Γ scenario aggregation kernels (Python reference + C++ ctypes).

Business / methodology selection stays in ``app.risk.historical`` (and callers).
This module only evaluates the per-scenario P&L:

    Δ·eq + ½γ·eq² + vega·vol_points + DV01·rates_bps + fx_delta·fx

``FULL_REVALUATION`` Historical VaR **cannot** use these kernels: that path
reprices via ``PricingEngine`` on shocked market snapshots. Only ``LINEAR`` and
``DELTA_GAMMA`` approximate P&L may select a kernel. Native threads never touch
QuantLib globals (ADR 007).

Backend selection (M6.3):

- ``QUANTLINEAGE_SCENARIO_KERNEL=python`` (default) — risk path keeps the NumPy
  vectorized formula in ``approximate_pnl_series``
- ``QUANTLINEAGE_SCENARIO_KERNEL=native`` — load ``NativeScenarioKernel`` via ctypes
- ``QUANTLINEAGE_SCENARIO_KERNEL_LIB`` — optional explicit shared-library path

Tolerances (M6.5): ``KERNEL_ABI_*`` for direct ABI compares; ``KERNEL_PNL_*`` for
NumPy risk-path vs kernel (also re-exported from ``app.risk.historical``).

C ABI (R0.12.5)
- ``quantlineage_kernel_abi_version()`` must equal ``KERNEL_ABI_VERSION`` (1).
- ``quantlineage_portfolio_scenarios`` returns ``KERNEL_OK`` / ``KERNEL_ERR_*``.
- Lengths: ``n_exposure_doubles == n_exposures * 5``,
  ``n_shock_doubles == n_shocks * 4``, ``n_out == n_shocks``.
- Null/empty: count 0 may pass NULL; count > 0 and NULL is ``KERNEL_ERR_NULL``.
  Empty book (0 exposures, N shocks) writes 0.0 per shock. Mismatch fails
  closed (error, no buffer walk).

R0.17 buffer / threads
- ``NativeScenarioKernel.pnl_from_arrays`` passes C-contiguous float64 buffers
  straight to the C ABI (no pack copy). Non-contiguous / non-float64 arrays
  are made contiguous float64 first.
- C++ stays serial when ``n_exposures * n_shocks < KERNEL_PARALLEL_MIN_WORK``
  (4096) so tiny workloads do not spawn threads per call.
"""

from __future__ import annotations

import ctypes
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

SCENARIO_KERNEL_ENV = "QUANTLINEAGE_SCENARIO_KERNEL"
SCENARIO_KERNEL_LIB_ENV = "QUANTLINEAGE_SCENARIO_KERNEL_LIB"

# M6.5 / M6.7 numerical tolerances (currency P&L units on the Exposure/Shock ABI).
#
# ABI layer (PythonScenarioKernel ↔ NativeScenarioKernel ↔ C++ serial/parallel):
# float64 nested loops with identical reduction order stay within a few ULPs;
# 1e-12 abs/rel is the gate used by native/tests/kernel_test.cpp.
KERNEL_ABI_ABS_TOL = 1e-12
KERNEL_ABI_REL_TOL = 1e-12
#
# Risk-path layer (NumPy ``approximate_pnl_series`` ↔ kernel via Historical VaR):
# slightly looser abs for near-zero paths after vol-point scaling / methodology
# gating in Python; see also re-exports in ``app.risk.historical``.
KERNEL_PNL_ABS_TOL = 1e-9
KERNEL_PNL_REL_TOL = 1e-12

# R0.12.5 C ABI contract (must match native/include/risk_kernel_capi.h).
KERNEL_ABI_VERSION = 1
KERNEL_EXPOSURE_STRIDE = 5
KERNEL_SHOCK_STRIDE = 4
KERNEL_OK = 0
KERNEL_ERR_ABI = 1
KERNEL_ERR_NULL = 2
KERNEL_ERR_LENGTH = 3

# R0.17: must match native/include/risk_kernel.hpp KERNEL_PARALLEL_MIN_WORK.
# Work items are n_exposures * n_shocks; below this the C++ kernel stays serial
# even when QUANTLINEAGE_KERNEL_THREADS > 1 (avoids per-call thread spawn).
KERNEL_PARALLEL_MIN_WORK = 4096

_KERNEL_ERR_NAMES = {
    KERNEL_ERR_ABI: "ABI mismatch",
    KERNEL_ERR_NULL: "null pointer",
    KERNEL_ERR_LENGTH: "length mismatch",
}


@dataclass(frozen=True)
class Exposure:
    delta: float = 0
    gamma: float = 0
    vega: float = 0
    dv01: float = 0
    fx_delta: float = 0


@dataclass(frozen=True)
class Shock:
    equity_return: float = 0
    vol_points: float = 0
    rates_bps: float = 0
    fx_return: float = 0


class ScenarioKernel(ABC):
    @abstractmethod
    def pnl(self, exposures: list[Exposure], shocks: list[Shock]) -> list[float]:
        raise NotImplementedError


class PythonScenarioKernel(ScenarioKernel):
    """Pure-Python reference for the linear Δ-Γ scenario kernel (M6 equivalence)."""

    def pnl(self, exposures, shocks):
        return [
            sum(
                e.delta * s.equity_return
                + 0.5 * e.gamma * s.equity_return**2
                + e.vega * s.vol_points
                + e.dv01 * s.rates_bps
                + e.fx_delta * s.fx_return
                for e in exposures
            )
            for s in shocks
        ]


class NativeKernelError(Exception):
    """Native C ABI rejected the call (version, null pointer, or length)."""

    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)


def _native_f64_c_buffer(arr: object, stride: int, *, name: str) -> tuple[np.ndarray, int, int]:
    """Return ``(c_contiguous float64 view, n_rows, n_doubles)``.

    A C-contiguous ``float64`` array is returned as-is (no copy). Other layouts
    or dtypes go through ``np.ascontiguousarray``. Shape must be ``(n, stride)``
    or packed ``(n * stride,)``.
    """
    a = np.asarray(arr)
    if a.ndim == 2:
        if a.shape[1] != stride:
            raise NativeKernelError(
                KERNEL_ERR_LENGTH,
                f"{name} second dimension must be {stride}, got {a.shape[1]}",
            )
        n_rows = int(a.shape[0])
    elif a.ndim == 1:
        if a.size % stride != 0:
            raise NativeKernelError(
                KERNEL_ERR_LENGTH,
                f"{name} length {a.size} is not a multiple of stride {stride}",
            )
        n_rows = int(a.size // stride)
    else:
        raise NativeKernelError(KERNEL_ERR_LENGTH, f"{name} must be 1-D or 2-D, got ndim={a.ndim}")
    n_doubles = n_rows * stride
    if a.dtype == np.float64 and a.flags.c_contiguous:
        return a, n_rows, n_doubles
    return np.ascontiguousarray(a, dtype=np.float64), n_rows, n_doubles


def _c_double_ptr(arr: np.ndarray):
    if arr.size == 0:
        return None
    return arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))


class NativeScenarioKernel(ScenarioKernel):
    """ctypes adapter for the optional C++20 scenario kernel."""

    def __init__(self, library_path: str | Path):
        self.library_path = Path(library_path)
        self.lib = ctypes.CDLL(str(self.library_path))
        if not hasattr(self.lib, "quantlineage_kernel_abi_version"):
            raise NativeKernelError(
                KERNEL_ERR_ABI,
                "native library missing quantlineage_kernel_abi_version",
            )
        ver_fn = self.lib.quantlineage_kernel_abi_version
        ver_fn.argtypes = []
        ver_fn.restype = ctypes.c_int
        self.abi_version = int(ver_fn())
        if self.abi_version != KERNEL_ABI_VERSION:
            raise NativeKernelError(
                KERNEL_ERR_ABI,
                f"native ABI {self.abi_version} != Python KERNEL_ABI_VERSION {KERNEL_ABI_VERSION}",
            )
        self.fn = self.lib.quantlineage_portfolio_scenarios
        self.fn.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
        ]
        self.fn.restype = ctypes.c_int

    def _invoke(
        self,
        exposures,
        n_exposures: int,
        n_exposure_doubles: int,
        shocks,
        n_shocks: int,
        n_shock_doubles: int,
        out,
        n_out: int,
    ) -> None:
        rc = self.fn(
            KERNEL_ABI_VERSION,
            exposures,
            n_exposures,
            n_exposure_doubles,
            shocks,
            n_shocks,
            n_shock_doubles,
            out,
            n_out,
        )
        if rc != KERNEL_OK:
            name = _KERNEL_ERR_NAMES.get(rc, "unknown")
            raise NativeKernelError(rc, f"quantlineage_portfolio_scenarios failed: {name} ({rc})")

    def pnl(self, exposures, shocks):
        n_e = len(exposures)
        n_s = len(shocks)
        eflat = [x for e in exposures for x in (e.delta, e.gamma, e.vega, e.dv01, e.fx_delta)]
        sflat = [
            x for s in shocks for x in (s.equity_return, s.vol_points, s.rates_bps, s.fx_return)
        ]
        n_ed = len(eflat)
        n_sd = len(sflat)
        if n_ed != n_e * KERNEL_EXPOSURE_STRIDE or n_sd != n_s * KERNEL_SHOCK_STRIDE:
            raise NativeKernelError(KERNEL_ERR_LENGTH, "packed buffer length does not match strides")
        E = (ctypes.c_double * n_ed)(*eflat)
        S = (ctypes.c_double * n_sd)(*sflat)
        O = (ctypes.c_double * n_s)()
        self._invoke(
            E if n_e else None,
            n_e,
            n_ed,
            S if n_s else None,
            n_s,
            n_sd,
            O if n_s else None,
            n_s,
        )
        return list(O)

    def pnl_from_arrays(
        self,
        exposures: object,
        shocks: object,
        out: NDArray[np.float64] | None = None,
    ) -> NDArray[np.float64]:
        """Evaluate the kernel from packed NumPy buffers.

        C-contiguous ``float64`` exposures/shocks/out are passed to the C ABI
        without an extra pack copy. Shape is ``(n, stride)`` or packed 1-D.
        ``out`` if given must be writable C-contiguous ``float64`` of length
        ``n_shocks`` and is updated in place.
        """
        e_buf, n_e, n_ed = _native_f64_c_buffer(
            exposures, KERNEL_EXPOSURE_STRIDE, name="exposures"
        )
        s_buf, n_s, n_sd = _native_f64_c_buffer(shocks, KERNEL_SHOCK_STRIDE, name="shocks")
        if out is None:
            out_buf = np.empty(n_s, dtype=np.float64)
        else:
            out_buf = np.asarray(out)
            if (
                out_buf.dtype != np.float64
                or not out_buf.flags.c_contiguous
                or out_buf.ndim != 1
                or int(out_buf.size) != n_s
            ):
                raise NativeKernelError(
                    KERNEL_ERR_LENGTH,
                    "out must be C-contiguous float64 with shape (n_shocks,)",
                )
        self._invoke(
            _c_double_ptr(e_buf),
            n_e,
            n_ed,
            _c_double_ptr(s_buf),
            n_s,
            n_sd,
            _c_double_ptr(out_buf) if n_s else None,
            n_s,
        )
        return out_buf


def scenario_kernel_backend(explicit: str | None = None) -> str:
    """Return ``python`` or ``native`` from env / override (default ``python``)."""
    raw = (explicit if explicit is not None else os.getenv(SCENARIO_KERNEL_ENV, "python") or "python")
    name = raw.strip().lower()
    if name in {"", "python", "numpy", "ref", "reference"}:
        return "python"
    if name in {"native", "cpp", "c++", "ctypes"}:
        return "native"
    raise ValueError(
        f"Unknown {SCENARIO_KERNEL_ENV}={raw!r}; expected 'python' or 'native'"
    )


def native_library_candidates() -> list[Path]:
    """Search paths for the optional shared library (explicit env first)."""
    out: list[Path] = []
    env = os.getenv(SCENARIO_KERNEL_LIB_ENV)
    if env and env.strip():
        out.append(Path(env.strip()).expanduser())
    native_root = Path(__file__).resolve().parents[2] / "native"
    names = (
        ("libriskkernel.dylib", "libriskkernel.so")
        if sys.platform == "darwin"
        else ("libriskkernel.so",)
    )
    for name in names:
        out.append(native_root / name)
    return out


def find_native_library() -> Path:
    """Resolve the native scenario shared library or raise ``FileNotFoundError``."""
    tried: list[str] = []
    for cand in native_library_candidates():
        tried.append(str(cand))
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        f"{SCENARIO_KERNEL_ENV}=native but no shared library found. "
        f"Build backend/native (see native/README.md) or set {SCENARIO_KERNEL_LIB_ENV}. "
        f"Tried: {tried}"
    )


def load_native_scenario_kernel(library_path: str | Path | None = None) -> NativeScenarioKernel:
    path = Path(library_path) if library_path is not None else find_native_library()
    if not path.is_file():
        raise FileNotFoundError(f"Native scenario kernel library not found: {path}")
    return NativeScenarioKernel(path)


def get_scenario_kernel(
    backend: str | None = None,
    *,
    library_path: str | Path | None = None,
) -> ScenarioKernel | None:
    """Return a kernel instance for the selected backend.

    ``python`` returns ``None`` so the Historical VaR path keeps its NumPy
    vectorized reference (faster than the pure-Python nested loops, same math).
    ``native`` returns a loaded :class:`NativeScenarioKernel`.
    """
    mode = scenario_kernel_backend(backend)
    if mode == "python":
        return None
    return load_native_scenario_kernel(library_path)
