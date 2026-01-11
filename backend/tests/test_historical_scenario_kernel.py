"""M6.7 gate: Python/NumPy vs native linear Δ-Γ kernel parity on Historical VaR path.

Conventions
- Units: currency P&L (same as ``approximate_pnl_series`` / HistoricalRiskEngine)
- Sign: positive P&L = gain; VaR uses loss = -P&L
- Kernel ABI: equity/FX relative returns; vol in *points* (relative × 100);
  rates in bp × DV01
- Tolerances: ``KERNEL_PNL_ABS_TOL`` / ``KERNEL_PNL_REL_TOL`` (``app.compute.kernel``)
- FULL_REVALUATION must not use the scenario kernel (pricing revaluation only)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.compute.kernel import (
    KERNEL_PNL_ABS_TOL,
    KERNEL_PNL_REL_TOL,
    Exposure,
    NativeScenarioKernel,
    PythonScenarioKernel,
    Shock,
    get_scenario_kernel,
    scenario_kernel_backend,
)
from app.domain.models import VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import (
    HistoricalRiskEngine,
    approximate_pnl_series,
    full_revaluation_pnl_series,
)
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.sample import SAMPLE_PORTFOLIO


def _build_native_lib(tmp_path: Path) -> Path:
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    root = Path(__file__).parents[1] / "native"
    # Darwin: emit .dylib (matches test_native_kernel / ctypes loaders).
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
            str(root / "src" / "risk_kernel_capi.cpp"),
            "-o",
            str(lib),
        ],
        check=True,
    )
    return lib


def _factor_series() -> FactorObservationSeries:
    eq = np.array([-0.12, -0.04, 0.0, 0.03, 0.08, -0.15, 0.02, 0.05], dtype=float)
    vol = np.array([0.25, 0.10, 0.0, -0.05, 0.15, 0.40, -0.02, 0.08], dtype=float)
    rates = np.array([12.0, -5.0, 0.0, 8.0, -15.0, 20.0, 3.0, -7.0], dtype=float)
    fx = np.array([-0.02, 0.01, 0.0, -0.005, 0.015, -0.03, 0.004, 0.008], dtype=float)
    return FactorObservationSeries(
        equity_returns=eq,
        vol_moves=vol,
        rate_moves_bps=rates,
        fx_returns=fx,
    )


def _assert_pnl_close(actual: np.ndarray, expected: np.ndarray) -> None:
    assert actual.shape == expected.shape
    np.testing.assert_allclose(
        actual,
        expected,
        rtol=KERNEL_PNL_REL_TOL,
        atol=KERNEL_PNL_ABS_TOL,
    )


def test_scenario_kernel_backend_default_python(monkeypatch):
    monkeypatch.delenv("RISKFORGE_SCENARIO_KERNEL", raising=False)
    assert scenario_kernel_backend() == "python"
    assert get_scenario_kernel() is None


def test_scenario_kernel_backend_native_alias(monkeypatch):
    monkeypatch.setenv("RISKFORGE_SCENARIO_KERNEL", "ctypes")
    assert scenario_kernel_backend() == "native"


def test_scenario_kernel_backend_rejects_unknown(monkeypatch):
    monkeypatch.setenv("RISKFORGE_SCENARIO_KERNEL", "gpu")
    with pytest.raises(ValueError, match="python|native"):
        scenario_kernel_backend()


def test_full_revaluation_rejected_by_approximate_pnl():
    z = np.zeros(4)
    with pytest.raises(ValueError, match="FULL_REVALUATION cannot use"):
        approximate_pnl_series(
            delta=1.0,
            gamma=2.0,
            vega=0.0,
            dv01=0.0,
            fx_delta=0.0,
            equity_ret=z,
            vol_pct=z,
            rates_bps=z,
            fx_ret=z,
            methodology=VaRMethodology.FULL_REVALUATION,
        )


def test_numpy_matches_python_scenario_kernel_reference():
    """NumPy risk path vs pure-Python kernel ABI (same Δ-Γ math)."""
    series = _factor_series()
    kwargs = dict(
        delta=1200.0,
        gamma=180.0,
        vega=40.0,
        dv01=-8.5,
        fx_delta=250.0,
        equity_ret=series.equity_returns,
        vol_pct=series.vol_moves,
        rates_bps=series.rate_moves_bps,
        fx_ret=series.fx_returns,
    )
    for meth in (VaRMethodology.LINEAR, VaRMethodology.DELTA_GAMMA):
        numpy_pnl = approximate_pnl_series(methodology=meth, scenario_backend="python", **kwargs)
        gamma_eff = 0.0 if meth is VaRMethodology.LINEAR else kwargs["gamma"]
        ref = PythonScenarioKernel().pnl(
            [
                Exposure(
                    delta=kwargs["delta"],
                    gamma=gamma_eff,
                    vega=kwargs["vega"],
                    dv01=kwargs["dv01"],
                    fx_delta=kwargs["fx_delta"],
                )
            ],
            [
                Shock(
                    equity_return=float(series.equity_returns[i]),
                    vol_points=float(series.vol_moves[i] * 100.0),
                    rates_bps=float(series.rate_moves_bps[i]),
                    fx_return=float(series.fx_returns[i]),
                )
                for i in range(series.n_observations)
            ],
        )
        _assert_pnl_close(numpy_pnl, np.asarray(ref, dtype=float))


def test_native_approximate_pnl_matches_numpy(tmp_path):
    lib = _build_native_lib(tmp_path)
    native = NativeScenarioKernel(lib)
    series = _factor_series()
    kwargs = dict(
        delta=-400.0,
        gamma=90.0,
        vega=12.0,
        dv01=3.25,
        fx_delta=-75.0,
        equity_ret=series.equity_returns,
        vol_pct=series.vol_moves,
        rates_bps=series.rate_moves_bps,
        fx_ret=series.fx_returns,
    )
    for meth in (VaRMethodology.LINEAR, VaRMethodology.DELTA_GAMMA):
        ref = approximate_pnl_series(methodology=meth, scenario_backend="python", **kwargs)
        actual = approximate_pnl_series(
            methodology=meth, scenario_kernel=native, **kwargs
        )
        _assert_pnl_close(actual, ref)


def test_historical_engine_native_var_matches_python(tmp_path, monkeypatch):
    """M6.7: HistoricalRiskEngine LINEAR/DELTA_GAMMA VaR parity under native kernel."""
    lib = _build_native_lib(tmp_path)
    monkeypatch.setenv("RISKFORGE_SCENARIO_KERNEL_LIB", str(lib))
    dataset = ArrayHistoricalDataset(_factor_series())
    pricing = BuiltinPricingEngine()
    py_engine = HistoricalRiskEngine(dataset=dataset, scenario_backend="python")
    native_engine = HistoricalRiskEngine(
        dataset=dataset,
        scenario_kernel=NativeScenarioKernel(lib),
    )
    for meth in (VaRMethodology.LINEAR, VaRMethodology.DELTA_GAMMA):
        py = py_engine.calculate(SAMPLE_PORTFOLIO, pricing, methodology=meth)
        nat = native_engine.calculate(SAMPLE_PORTFOLIO, pricing, methodology=meth)
        for key in ("var_95", "var_99", "expected_shortfall_99", "market_value", "delta", "gamma"):
            assert nat[key] == pytest.approx(
                py[key], rel=KERNEL_PNL_REL_TOL, abs=KERNEL_PNL_ABS_TOL
            ), key


def test_env_native_backend_loads_lib(tmp_path, monkeypatch):
    lib = _build_native_lib(tmp_path)
    monkeypatch.setenv("RISKFORGE_SCENARIO_KERNEL", "native")
    monkeypatch.setenv("RISKFORGE_SCENARIO_KERNEL_LIB", str(lib))
    kernel = get_scenario_kernel()
    assert isinstance(kernel, NativeScenarioKernel)
    series = _factor_series()
    ref = approximate_pnl_series(
        delta=100.0,
        gamma=10.0,
        vega=1.0,
        dv01=0.0,
        fx_delta=0.0,
        equity_ret=series.equity_returns,
        vol_pct=series.vol_moves,
        rates_bps=series.rate_moves_bps,
        fx_ret=series.fx_returns,
        methodology=VaRMethodology.DELTA_GAMMA,
        scenario_backend="python",
    )
    via_env = approximate_pnl_series(
        delta=100.0,
        gamma=10.0,
        vega=1.0,
        dv01=0.0,
        fx_delta=0.0,
        equity_ret=series.equity_returns,
        vol_pct=series.vol_moves,
        rates_bps=series.rate_moves_bps,
        fx_ret=series.fx_returns,
        methodology=VaRMethodology.DELTA_GAMMA,
    )
    _assert_pnl_close(via_env, ref)


def test_full_revaluation_path_unaffected_by_native_flag(tmp_path, monkeypatch):
    """FULL_REVALUATION must ignore RISKFORGE_SCENARIO_KERNEL (no kernel P&L)."""
    lib = _build_native_lib(tmp_path)
    monkeypatch.setenv("RISKFORGE_SCENARIO_KERNEL", "native")
    monkeypatch.setenv("RISKFORGE_SCENARIO_KERNEL_LIB", str(lib))
    dataset = ArrayHistoricalDataset(_factor_series())
    pricing = BuiltinPricingEngine()
    engine = HistoricalRiskEngine(dataset=dataset)
    # Must complete without routing through approximate_pnl_series / kernel.
    out = engine.calculate(
        SAMPLE_PORTFOLIO, pricing, methodology=VaRMethodology.FULL_REVALUATION
    )
    assert out["methodology"] == "FULL_REVALUATION"
    assert out["var_95"] >= 0.0
    # Smoke: full_revaluation helper still documents/runs independently of kernel.
    from app.market.snapshot import PositionMarketDataProvider

    base = PositionMarketDataProvider().snapshot(SAMPLE_PORTFOLIO)
    pnl = full_revaluation_pnl_series(SAMPLE_PORTFOLIO, pricing, base, dataset)
    assert pnl.shape == (dataset.factor_observations().n_observations,)


def test_empty_observations_native(tmp_path):
    lib = _build_native_lib(tmp_path)
    z = np.zeros(0)
    out = approximate_pnl_series(
        delta=1.0,
        gamma=2.0,
        vega=3.0,
        dv01=4.0,
        fx_delta=5.0,
        equity_ret=z,
        vol_pct=z,
        rates_bps=z,
        fx_ret=z,
        methodology=VaRMethodology.DELTA_GAMMA,
        scenario_kernel=NativeScenarioKernel(lib),
    )
    assert out.shape == (0,)
