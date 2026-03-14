from __future__ import annotations

import numpy as np

from app.compute.kernel import (
    Exposure,
    ScenarioKernel,
    Shock,
    get_scenario_kernel,
)
from app.domain.models import MarketSnapshot, Portfolio, Valuation, VaRMethodology
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.risk.historical_data import HistoricalMarketDataset, SyntheticHistoricalDataset
from app.risk.scenarios import historical_shocked_snapshots


def require_explicit_market(market: MarketSnapshot | None) -> MarketSnapshot:
    """Fail closed: production VaR / ES / full-reval must receive a snapshot."""
    if market is None:
        raise ValueError("production risk calculation requires an explicit MarketSnapshot")
    return market


def _aggregate_greeks(vals: list[Valuation]) -> tuple[float, float, float, float, float, float]:
    mv = sum(v.market_value for v in vals)
    delta = sum(v.delta for v in vals)
    gamma = sum(v.gamma for v in vals)
    vega = sum(v.vega for v in vals)
    dv01 = sum(v.dv01 for v in vals)
    fx_delta = sum(v.fx_delta for v in vals)
    return mv, delta, gamma, vega, dv01, fx_delta


def _pnl_via_scenario_kernel(
    kernel: ScenarioKernel,
    *,
    delta: float,
    gamma: float,
    vega: float,
    dv01: float,
    fx_delta: float,
    equity_ret: np.ndarray,
    vol_points: np.ndarray,
    rates_bps: np.ndarray,
    fx_ret: np.ndarray,
) -> np.ndarray:
    """Map aggregated Greeks + factor arrays onto the Exposure/Shock kernel ABI."""
    n = int(equity_ret.shape[0])
    if n == 0:
        return np.zeros(0, dtype=float)
    exposures = [
        Exposure(
            delta=float(delta),
            gamma=float(gamma),
            vega=float(vega),
            dv01=float(dv01),
            fx_delta=float(fx_delta),
        )
    ]
    shocks = [
        Shock(
            equity_return=float(equity_ret[i]),
            vol_points=float(vol_points[i]),
            rates_bps=float(rates_bps[i]),
            fx_return=float(fx_ret[i]),
        )
        for i in range(n)
    ]
    return np.asarray(kernel.pnl(exposures, shocks), dtype=float)


def approximate_pnl_series(
    *,
    delta: float,
    gamma: float,
    vega: float,
    dv01: float,
    fx_delta: float,
    equity_ret: np.ndarray,
    vol_pct: np.ndarray,
    rates_bps: np.ndarray,
    fx_ret: np.ndarray,
    methodology: VaRMethodology,
    scenario_kernel: ScenarioKernel | None = None,
    scenario_backend: str | None = None,
) -> np.ndarray:
    """First-order (LINEAR) or delta-gamma (DELTA_GAMMA) P&L path.

    Units match ``FactorObservationSeries`` / legacy Δ-Γ VaR:
    - equity / FX: relative returns × cash delta / fx_delta
    - vol: relative vol move × vega, with vega quoted per 1 vol point (×100)
    - rates: parallel bp moves × DV01

    Kernel backend (M6.3): default NumPy (``RISKFORGE_SCENARIO_KERNEL=python``).
    When ``native`` is selected (or ``scenario_kernel`` is injected), P&L is
    evaluated via the linear Δ-Γ scenario kernel. Methodology / unit conversion
    remain in Python.

    ``FULL_REVALUATION`` cannot use this function or the scenario kernel — it
    requires ``PricingEngine`` revaluation on shocked snapshots
    (``full_revaluation_pnl_series``).
    """
    if methodology is VaRMethodology.FULL_REVALUATION:
        raise ValueError(
            "FULL_REVALUATION cannot use the linear Δ-Γ scenario kernel; "
            "use full_revaluation_pnl_series / PricingEngine revaluation instead"
        )
    if methodology not in (VaRMethodology.LINEAR, VaRMethodology.DELTA_GAMMA):
        raise ValueError(f"approximate_pnl_series does not support {methodology!r}")

    # LINEAR zeros γ so the same kernel ABI serves both approximate modes.
    gamma_eff = 0.0 if methodology is VaRMethodology.LINEAR else float(gamma)
    vol_points = np.asarray(vol_pct, dtype=float) * 100.0
    equity_ret = np.asarray(equity_ret, dtype=float)
    rates_bps = np.asarray(rates_bps, dtype=float)
    fx_ret = np.asarray(fx_ret, dtype=float)

    kernel = scenario_kernel
    if kernel is None:
        kernel = get_scenario_kernel(scenario_backend)

    if kernel is not None:
        return _pnl_via_scenario_kernel(
            kernel,
            delta=float(delta),
            gamma=gamma_eff,
            vega=float(vega),
            dv01=float(dv01),
            fx_delta=float(fx_delta),
            equity_ret=equity_ret,
            vol_points=vol_points,
            rates_bps=rates_bps,
            fx_ret=fx_ret,
        )

    linear = (
        delta * equity_ret
        + vega * vol_points
        + dv01 * rates_bps
        + fx_delta * fx_ret
    )
    if methodology is VaRMethodology.LINEAR:
        return linear
    return linear + 0.5 * gamma * equity_ret * equity_ret


def full_revaluation_pnl_series(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    base_market: MarketSnapshot,
    dataset: HistoricalMarketDataset,
) -> np.ndarray:
    """P&L under each historical shocked snapshot (independent, not cumulative).

    ``pnl[i] = PV(shocked_i) - PV(base)``. Zero shocks → ~0 (pricing-determinism
    and empty ``MarketScenario`` preserving marks).

    Does **not** use the linear Δ-Γ scenario kernel (Python or native): full
    revaluation is pricing-driven and outside the Exposure/Shock ABI.
    """
    base_mv = sum(v.market_value for v in pricing_engine.value_portfolio(portfolio, base_market))
    shocked = historical_shocked_snapshots(base_market, dataset)
    pnls = np.empty(len(shocked), dtype=float)
    for i, snap in enumerate(shocked):
        shocked_mv = sum(v.market_value for v in pricing_engine.value_portfolio(portfolio, snap))
        pnls[i] = shocked_mv - base_mv
    return pnls


class HistoricalRiskEngine(RiskEngine):
    """Historical-style risk using a :class:`HistoricalMarketDataset`.

    Methodologies (M2.3):
    - ``LINEAR`` — first-order Greek approximation
    - ``DELTA_GAMMA`` — legacy delta-gamma + vega/DV01/FX (default)
    - ``FULL_REVALUATION`` — reprice via ``PricingEngine`` on M2.2 shocked snapshots

    Approximate modes (LINEAR / DELTA_GAMMA) may evaluate scenario P&L via the
    optional native kernel when ``RISKFORGE_SCENARIO_KERNEL=native`` (or an
    injected ``scenario_kernel``). FULL_REVALUATION never uses that kernel.

    Default dataset is :class:`SyntheticHistoricalDataset` (deterministic RNG)
    so MVP results stay reproducible without an external market-data feed.
    """

    def __init__(
        self,
        seed: int = 7,
        observations: int = 750,
        dataset: HistoricalMarketDataset | None = None,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
        scenario_kernel: ScenarioKernel | None = None,
        scenario_backend: str | None = None,
    ):
        self.seed = seed
        self.observations = observations
        self.dataset: HistoricalMarketDataset = dataset or SyntheticHistoricalDataset(
            seed=seed, observations=observations
        )
        self.methodology = methodology
        self.scenario_kernel = scenario_kernel
        self.scenario_backend = scenario_backend

    def calculate(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        methodology: VaRMethodology | None = None,
        market: MarketSnapshot | None = None,
    ) -> dict:
        meth = methodology if methodology is not None else self.methodology
        # Production path: caller must supply the snapshot. Demo inference is
        # reserved for named demo helpers / tests, not this engine.
        base_market = require_explicit_market(market)
        vals = pricing_engine.value_portfolio(portfolio, base_market)
        mv, delta, gamma, vega, dv01, fx_delta = _aggregate_greeks(vals)

        if meth is VaRMethodology.FULL_REVALUATION:
            pnl = full_revaluation_pnl_series(portfolio, pricing_engine, base_market, self.dataset)
        else:
            obs = self.dataset.factor_observations()
            pnl = approximate_pnl_series(
                delta=delta,
                gamma=gamma,
                vega=vega,
                dv01=dv01,
                fx_delta=fx_delta,
                equity_ret=obs.equity_returns,
                vol_pct=obs.vol_moves,
                rates_bps=obs.rate_moves_bps,
                fx_ret=obs.fx_returns,
                methodology=meth,
                scenario_kernel=self.scenario_kernel,
                scenario_backend=self.scenario_backend,
            )

        losses = -pnl
        var95 = float(max(0.0, np.quantile(losses, 0.95)))
        var99 = float(max(0.0, np.quantile(losses, 0.99)))
        tail = losses[losses >= var99]
        es99 = float(max(0.0, tail.mean() if len(tail) else var99))
        return {
            "market_value": float(mv),
            "delta": float(delta),
            "gamma": float(gamma),
            "vega": float(vega),
            "dv01": float(dv01),
            "fx_delta": float(fx_delta),
            "var_95": var95,
            "var_99": var99,
            "expected_shortfall_99": es99,
            "methodology": meth.value if isinstance(meth, VaRMethodology) else str(meth),
        }
