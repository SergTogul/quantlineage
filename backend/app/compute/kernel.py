from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import ctypes
from pathlib import Path

@dataclass(frozen=True)
class Exposure:
    delta: float=0; gamma: float=0; vega: float=0; dv01: float=0; fx_delta: float=0
@dataclass(frozen=True)
class Shock:
    equity_return: float=0; vol_points: float=0; rates_bps: float=0; fx_return: float=0

class ScenarioKernel(ABC):
    @abstractmethod
    def pnl(self, exposures: list[Exposure], shocks: list[Shock]) -> list[float]: raise NotImplementedError

class PythonScenarioKernel(ScenarioKernel):
    def pnl(self, exposures, shocks):
        return [sum(e.delta*s.equity_return + .5*e.gamma*s.equity_return**2 + e.vega*s.vol_points + e.dv01*s.rates_bps + e.fx_delta*s.fx_return for e in exposures) for s in shocks]

class NativeScenarioKernel(ScenarioKernel):
    """Dependency-free ctypes adapter for the optional C++20 scenario kernel."""
    def __init__(self, library_path: str | Path):
        self.lib=ctypes.CDLL(str(library_path)); self.fn=self.lib.riskforge_portfolio_scenarios
        self.fn.argtypes=[ctypes.POINTER(ctypes.c_double),ctypes.c_size_t,ctypes.POINTER(ctypes.c_double),ctypes.c_size_t,ctypes.POINTER(ctypes.c_double)]
        self.fn.restype=None
    def pnl(self, exposures, shocks):
        eflat=[x for e in exposures for x in (e.delta,e.gamma,e.vega,e.dv01,e.fx_delta)]
        sflat=[x for s in shocks for x in (s.equity_return,s.vol_points,s.rates_bps,s.fx_return)]
        E=(ctypes.c_double*len(eflat))(*eflat); S=(ctypes.c_double*len(sflat))(*sflat); O=(ctypes.c_double*len(shocks))()
        self.fn(E,len(exposures),S,len(shocks),O)
        return list(O)
