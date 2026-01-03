"""Optional linear Δ-Γ scenario aggregation kernels (Python reference + C++ ctypes).

Business / methodology selection stays in ``app.risk.historical`` (and callers).
This module only evaluates the per-scenario P&L:

    Δ·eq + ½γ·eq² + vega·vol_points + DV01·rates_bps + fx_delta·fx

``FULL_REVALUATION`` Historical VaR **cannot** use these kernels: that path
reprices via ``PricingEngine`` on shocked market snapshots. Only ``LINEAR`` and
``DELTA_GAMMA`` approximate P&L may select a kernel. Native threads never touch
QuantLib globals (ADR 007).

Backend selection (M6.3):

- ``RISKFORGE_SCENARIO_KERNEL=python`` (default) — risk path keeps the NumPy
  vectorized formula in ``approximate_pnl_series``
- ``RISKFORGE_SCENARIO_KERNEL=native`` — load ``NativeScenarioKernel`` via ctypes
- ``RISKFORGE_SCENARIO_KERNEL_LIB`` — optional explicit shared-library path

Tolerances (M6.5): ``KERNEL_ABI_*`` for direct ABI compares; ``KERNEL_PNL_*`` for
NumPy risk-path vs kernel (also re-exported from ``app.risk.historical``).
"""

from __future__ import annotations

import ctypes
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

SCENARIO_KERNEL_ENV = "RISKFORGE_SCENARIO_KERNEL"
SCENARIO_KERNEL_LIB_ENV = "RISKFORGE_SCENARIO_KERNEL_LIB"

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


class NativeScenarioKernel(ScenarioKernel):
    """Dependency-free ctypes adapter for the optional C++20 scenario kernel."""

    def __init__(self, library_path: str | Path):
        self.library_path = Path(library_path)
        self.lib = ctypes.CDLL(str(self.library_path))
        self.fn = self.lib.riskforge_portfolio_scenarios
        self.fn.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
        ]
        self.fn.restype = None

    def pnl(self, exposures, shocks):
        eflat = [x for e in exposures for x in (e.delta, e.gamma, e.vega, e.dv01, e.fx_delta)]
        sflat = [
            x for s in shocks for x in (s.equity_return, s.vol_points, s.rates_bps, s.fx_return)
        ]
        E = (ctypes.c_double * len(eflat))(*eflat)
        S = (ctypes.c_double * len(sflat))(*sflat)
        O = (ctypes.c_double * len(shocks))()
        self.fn(E, len(exposures), S, len(shocks), O)
        return list(O)


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
