from __future__ import annotations

import numpy as np

from app.compute.kernel import (
    KERNEL_ERR_LENGTH,
    KERNEL_EXPOSURE_STRIDE,
    KERNEL_SHOCK_STRIDE,
    Exposure,
    NativeKernelError,
    ScenarioKernel,
    Shock,
    get_scenario_kernel,
)
from app.domain.models import (
    BondPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    Portfolio,
    Position,
    SwapPosition,
    Valuation,
    VaRMethodology,
)
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.risk.factor_panel import HistoricalFactorPanel, panel_factor_identity
from app.risk.factor_types import (
    EquitySpot,
    EquityVol,
    FXSpot,
    FXVol,
    RateZero,
    RiskFactor,
)
from app.risk.historical_data import HistoricalMarketDataset, SyntheticHistoricalDataset
from app.risk.scenarios import iter_historical_shocked_snapshots, iter_panel_shocked_snapshots
from app.risk.shock_units import relative_vol_move_to_vol_points


def require_explicit_market(market: MarketSnapshot | None) -> MarketSnapshot:
    """Fail closed: production risk methods must receive a snapshot."""
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


def _require_aligned_1d_factors(
    equity_ret: np.ndarray,
    vol_points: np.ndarray,
    rates_bps: np.ndarray,
    fx_ret: np.ndarray,
) -> int:
    """Fail closed unless all four factor arrays are 1-D with the same length."""
    named = (
        ("equity_ret", equity_ret),
        ("vol_points", vol_points),
        ("rates_bps", rates_bps),
        ("fx_ret", fx_ret),
    )
    n: int | None = None
    for name, raw in named:
        arr = np.asarray(raw)
        if arr.ndim != 1:
            raise ValueError(f"{name} must be 1-D, got shape {arr.shape}")
        length = int(arr.shape[0])
        if n is None:
            n = length
        elif length != n:
            raise ValueError(
                f"factor arrays must have the same length; {name} has {length}, expected {n}"
            )
    return int(n or 0)


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
    """Map aggregated Greeks + factor arrays onto the Exposure/Shock kernel ABI.

    Native kernels (``pnl_from_arrays``) receive C-contiguous float64 buffers:
    exposures ``(1, 5)`` and shocks ``(n, 4)``. Object ``pnl()`` packing is
    reserved for the Python reference kernel.
    """
    n = _require_aligned_1d_factors(equity_ret, vol_points, rates_bps, fx_ret)
    if n == 0:
        return np.zeros(0, dtype=float)

    pnl_from_arrays = getattr(kernel, "pnl_from_arrays", None)
    if callable(pnl_from_arrays):
        exposures = np.empty((1, KERNEL_EXPOSURE_STRIDE), dtype=np.float64)
        exposures[0, 0] = float(delta)
        exposures[0, 1] = float(gamma)
        exposures[0, 2] = float(vega)
        exposures[0, 3] = float(dv01)
        exposures[0, 4] = float(fx_delta)
        shocks = np.empty((n, KERNEL_SHOCK_STRIDE), dtype=np.float64)
        shocks[:, 0] = np.asarray(equity_ret, dtype=np.float64)
        shocks[:, 1] = np.asarray(vol_points, dtype=np.float64)
        shocks[:, 2] = np.asarray(rates_bps, dtype=np.float64)
        shocks[:, 3] = np.asarray(fx_ret, dtype=np.float64)
        if not exposures.flags.c_contiguous:
            exposures = np.ascontiguousarray(exposures)
        if not shocks.flags.c_contiguous:
            shocks = np.ascontiguousarray(shocks)
        if exposures.shape != (1, KERNEL_EXPOSURE_STRIDE) or shocks.shape != (
            n,
            KERNEL_SHOCK_STRIDE,
        ):
            raise NativeKernelError(
                KERNEL_ERR_LENGTH,
                f"packed buffers have wrong shape: exposures {exposures.shape}, "
                f"shocks {shocks.shape}, expected (1, {KERNEL_EXPOSURE_STRIDE}) and "
                f"({n}, {KERNEL_SHOCK_STRIDE})",
            )
        return np.asarray(pnl_from_arrays(exposures, shocks), dtype=float)

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
    evaluated via the linear Δ-Γ scenario kernel. Native kernels receive
    C-contiguous float64 exposure/shock arrays (``pnl_from_arrays``); the
    Python reference kernel still uses object ``pnl()``. Methodology / unit
    conversion remain in Python.

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
    vol_points = relative_vol_move_to_vol_points(np.asarray(vol_pct, dtype=float))
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


def historical_pnl_for_valuation(
    risk: RiskEngine,
    valuation: Valuation,
) -> tuple[float, ...] | None:
    """One historical P&L series from already-valued Greeks (no reprice).

    Shared by ``PortfolioService`` and ``HierarchyEngine`` default artifact
    production. Uses the engine dataset + methodology and
    ``approximate_pnl_series`` (LINEAR / DELTA_GAMMA). One series per trade,
    shared factor observations so lengths match.

    FULL_REVALUATION and an opt-in ``factor_panel`` are omitted (``None``):
    those paths would call ``value`` again. Non-``HistoricalRiskEngine``
    risk engines also return ``None``.
    """
    if not isinstance(risk, HistoricalRiskEngine):
        return None
    if risk.methodology is VaRMethodology.FULL_REVALUATION:
        return None
    if risk.factor_panel is not None:
        return None
    observations = risk.dataset.factor_observations()
    series = approximate_pnl_series(
        delta=valuation.delta,
        gamma=valuation.gamma,
        vega=valuation.vega,
        dv01=valuation.dv01,
        fx_delta=valuation.fx_delta,
        equity_ret=observations.equity_returns,
        vol_pct=observations.vol_moves,
        rates_bps=observations.rate_moves_bps,
        fx_ret=observations.fx_returns,
        methodology=risk.methodology,
        scenario_kernel=risk.scenario_kernel,
        scenario_backend=risk.scenario_backend,
    )
    if series.size == 0:
        return None
    return tuple(float(point) for point in series)


def _rate_tenor(maturity_years: float) -> str:
    return f"{round(float(maturity_years))}Y"


def required_factors_for_position(position: Position) -> tuple[RiskFactor, ...]:
    """Typed factors a panel must contain for one position (fail-closed).

    Identity matches ``RiskFactorEngine.calculate_typed``: per-name equity/FX
    and per-tenor rates via ``round(maturity_years)Y``. Options also require
    their vol factor. Cap/floor and swaption are not mapped here.
    """
    if isinstance(position, (EquityPosition, EquityFuturePosition, EuropeanOptionPosition)):
        factors: list[RiskFactor] = [EquitySpot(position.symbol)]
        if isinstance(position, EuropeanOptionPosition):
            factors.append(EquityVol(underlying=position.symbol))
        return tuple(factors)
    if isinstance(position, (BondPosition, SwapPosition, InterestRateFuturePosition)):
        return (RateZero(currency=position.currency, tenor=_rate_tenor(position.maturity_years)),)
    if isinstance(position, (FXForwardPosition, FXOptionPosition)):
        factors = [FXSpot(position.pair)]
        if isinstance(position, FXOptionPosition):
            factors.append(FXVol(pair=position.pair))
        return tuple(factors)
    raise TypeError(f"unsupported position type for panel path: {type(position)!r}")


def required_panel_factors(portfolio: Portfolio) -> tuple[RiskFactor, ...]:
    """Union of ``required_factors_for_position`` across the book."""
    factors: list[RiskFactor] = []
    seen: set[tuple[str, str, str]] = set()
    for position in portfolio.positions:
        for factor in required_factors_for_position(position):
            identity = panel_factor_identity(factor)
            if identity not in seen:
                seen.add(identity)
                factors.append(factor)
    return tuple(factors)


def require_panel_covers_portfolio(portfolio: Portfolio, panel: HistoricalFactorPanel) -> None:
    """Fail closed if any required position factor is absent from ``panel``.

    Missing is not treated as a zero move.
    """
    column_ids = {panel_factor_identity(factor) for factor in panel.factors}
    missing = [
        factor
        for factor in required_panel_factors(portfolio)
        if panel_factor_identity(factor) not in column_ids
    ]
    if missing:
        identities = ", ".join(str(panel_factor_identity(f)) for f in missing)
        raise ValueError(f"panel missing required factor(s): {identities}")


def _panel_linear_contribution(factor: RiskFactor, valuation: Valuation, move: float) -> float:
    if isinstance(factor, EquitySpot):
        return float(valuation.delta) * move
    if isinstance(factor, FXSpot):
        return float(valuation.fx_delta) * move
    if isinstance(factor, (EquityVol, FXVol)):
        return float(valuation.vega) * relative_vol_move_to_vol_points(move)
    if isinstance(factor, RateZero):
        return float(valuation.dv01) * move
    raise TypeError(f"unsupported risk factor type: {type(factor)!r}")


def approximate_position_pnls_from_panel(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    base_market: MarketSnapshot,
    panel: HistoricalFactorPanel,
    *,
    methodology: VaRMethodology = VaRMethodology.LINEAR,
) -> dict[str, np.ndarray]:
    """Per-position LINEAR / DELTA_GAMMA P&L series from a ``HistoricalFactorPanel``.

    Each position is shocked by its own typed column — two equities or two
    rate tenors in one observation are not broadcast. Missing required factors
    fail closed. Units match ``approximate_pnl_series``.
    """
    if methodology is VaRMethodology.FULL_REVALUATION:
        raise ValueError(
            "FULL_REVALUATION cannot use approximate_position_pnls_from_panel; "
            "use full_revaluation_pnl_from_panel instead"
        )
    if methodology not in (VaRMethodology.LINEAR, VaRMethodology.DELTA_GAMMA):
        raise ValueError(f"approximate_position_pnls_from_panel does not support {methodology!r}")
    require_panel_covers_portfolio(portfolio, panel)
    vals = pricing_engine.value_portfolio(portfolio, base_market)
    if len(vals) != len(portfolio.positions):
        raise ValueError("valuation count does not match portfolio positions")

    position_factors = [required_factors_for_position(p) for p in portfolio.positions]
    out: dict[str, np.ndarray] = {
        p.id: np.zeros(panel.n_observations, dtype=float) for p in portfolio.positions
    }
    use_gamma = methodology is VaRMethodology.DELTA_GAMMA
    for i, observation in enumerate(panel.observations):
        for position, factors, valuation in zip(
            portfolio.positions, position_factors, vals, strict=True
        ):
            total = 0.0
            for factor in factors:
                move = observation.change(factor)
                total += _panel_linear_contribution(factor, valuation, move)
                if use_gamma and isinstance(factor, EquitySpot):
                    total += 0.5 * float(valuation.gamma) * move * move
            out[position.id][i] = total
    return out


def approximate_pnl_from_panel(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    base_market: MarketSnapshot,
    panel: HistoricalFactorPanel,
    *,
    methodology: VaRMethodology = VaRMethodology.LINEAR,
) -> np.ndarray:
    """Per-factor LINEAR / DELTA_GAMMA P&L from a ``HistoricalFactorPanel``.

    Each position is shocked by its own typed column — two equities or two
    rate tenors in one observation are not broadcast. Units match
    ``approximate_pnl_series`` / ``FactorObservationSeries``.
    """
    by_position = approximate_position_pnls_from_panel(
        portfolio,
        pricing_engine,
        base_market,
        panel,
        methodology=methodology,
    )
    if not by_position:
        return np.zeros(panel.n_observations, dtype=float)
    return sum(by_position.values(), start=np.zeros(panel.n_observations, dtype=float))


def full_revaluation_pnl_from_panel(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    base_market: MarketSnapshot,
    panel: HistoricalFactorPanel,
) -> np.ndarray:
    """P&L under each panel-shocked snapshot (independent, not cumulative).

    ``pnl[i] = PV(shocked_i) - PV(base)``. Required position factors must
    exist on the panel; missing is not treated as a zero move.
    """
    require_panel_covers_portfolio(portfolio, panel)
    base_mv = sum(v.market_value for v in pricing_engine.value_portfolio(portfolio, base_market))
    pnls: list[float] = []
    for snap in iter_panel_shocked_snapshots(base_market, panel):
        shocked_mv = sum(v.market_value for v in pricing_engine.value_portfolio(portfolio, snap))
        pnls.append(shocked_mv - base_mv)
    return np.asarray(pnls, dtype=float)


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
    pnls: list[float] = []
    for snap in iter_historical_shocked_snapshots(base_market, dataset):
        shocked_mv = sum(v.market_value for v in pricing_engine.value_portfolio(portfolio, snap))
        pnls.append(shocked_mv - base_mv)
    return np.asarray(pnls, dtype=float)


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

    ``factor_panel`` (R0.5.3): when supplied, LINEAR / DELTA_GAMMA /
    FULL_REVALUATION consume per-name and per-tenor panel columns instead of
    ``dataset.factor_observations()``. Production
    :func:`app.services.risk_factories.build_historical_risk_engine` wires a
    seeded synthetic panel. Bare ``HistoricalRiskEngine()`` /
    ``factor_panel=None`` keeps the labeled ``four_macro_demo`` dataset path.
    """

    def __init__(
        self,
        seed: int = 7,
        observations: int = 750,
        dataset: HistoricalMarketDataset | None = None,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
        scenario_kernel: ScenarioKernel | None = None,
        scenario_backend: str | None = None,
        factor_panel: HistoricalFactorPanel | None = None,
    ):
        self.seed = seed
        self.observations = observations
        self.dataset: HistoricalMarketDataset = dataset or SyntheticHistoricalDataset(
            seed=seed, observations=observations
        )
        self.methodology = methodology
        self.scenario_kernel = scenario_kernel
        self.scenario_backend = scenario_backend
        self.factor_panel = factor_panel

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

        if self.factor_panel is not None:
            if meth is VaRMethodology.FULL_REVALUATION:
                pnl = full_revaluation_pnl_from_panel(
                    portfolio, pricing_engine, base_market, self.factor_panel
                )
            else:
                pnl = approximate_pnl_from_panel(
                    portfolio,
                    pricing_engine,
                    base_market,
                    self.factor_panel,
                    methodology=meth,
                )
        elif meth is VaRMethodology.FULL_REVALUATION:
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
