"""Single-factor reverse stress (M3.5).

Answers: how far must one factor family move for portfolio loss to exceed a
target fraction of |NAV|?

Pipeline: build a formal ``Scenario`` with typed ``FactorShock`` / ``RiskFactor``
entries → ``apply_scenario`` on an immutable ``MarketSnapshot`` → revalue via
the pricing engine. Numerical search is binary search on adverse magnitude
(monotonic loss vs magnitude assumed for single-factor families).

Wire units for ``required_shock`` stay API-compatible with
``POST /risk/stress/reverse``:
- equity / vol / fx: relative move (0.10 = 10%)
- rates: parallel shift in **basis points** (100 = +100bp)
"""

from __future__ import annotations

from typing import Literal

from app.domain.models import (
    Portfolio,
    ReverseStressConvergence,
    ReverseStressResult,
)
from app.interfaces.pricing import PricingEngine
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero, RiskFactor
from app.risk.scenario_engine import apply_scenario
from app.risk.scenario_model import FactorShock, Scenario, ScenarioCategory
from app.sample import DemoAggregateMarketDataProvider

FactorFamily = Literal["equity", "rates", "vol", "fx"]

DEFAULT_MAX_ITERATIONS = 40
# Absolute tolerance on loss fraction of |NAV| used to declare "close enough".
DEFAULT_LOSS_TOLERANCE = 1e-6
# Search variable for rates: magnitude * RATES_BP_SCALE == returned bp shock.
# Matches legacy ReverseStressEngine (max_shock=0.80 → 800bp search bound).
RATES_BP_SCALE = 1000.0


def shock_unit_for(factor: FactorFamily) -> Literal["relative", "bp"]:
    return "bp" if factor == "rates" else "relative"


def to_wire_shock(factor: FactorFamily, magnitude: float) -> float:
    """Map internal search magnitude onto the public ``required_shock`` unit."""
    if factor == "rates":
        return magnitude * RATES_BP_SCALE
    return magnitude


def from_wire_bound(factor: FactorFamily, max_shock: float) -> float:
    """Interpret request ``max_shock`` as internal search magnitude.

    For equity/vol/fx, ``max_shock`` is already relative. For rates the API
    historically passed the same relative-style bound (e.g. 0.80) which this
    engine maps to ``0.80 * 1000 = 800`` bp — callers that pass an explicit
    bp bound (> 1) are also accepted.
    """
    if factor != "rates":
        return float(max_shock)
    # Heuristic: values > 1 are treated as bp (e.g. max_shock=500 → 500bp).
    if max_shock > 1.0:
        return float(max_shock) / RATES_BP_SCALE
    return float(max_shock)


def build_single_factor_shocks(
    factor: FactorFamily,
    magnitude: float,
    base,
) -> tuple[FactorShock, ...]:
    """Typed shocks for one adverse move of ``magnitude`` (search units).

    Direction (loss-seeking for a typical long book):
    - equity / fx: negative relative return
    - vol: positive relative vol level
    - rates: positive parallel zero shift (decimal = magnitude * 0.1)
    """
    if magnitude == 0.0:
        return ()
    shocks: list[FactorShock] = []
    if factor == "equity":
        for sym in base.equity_spots:
            shocks.append(FactorShock(EquitySpot(sym), -float(magnitude)))
    elif factor == "vol":
        for sym in base.equity_vols:
            shocks.append(FactorShock(EquityVol(underlying=sym), float(magnitude)))
        for pair in base.fx_vols:
            shocks.append(FactorShock(FXVol(pair=pair), float(magnitude)))
    elif factor == "fx":
        for pair in base.fx_spots:
            shocks.append(FactorShock(FXSpot(pair), -float(magnitude)))
    elif factor == "rates":
        # magnitude * RATES_BP_SCALE bp → decimal zero = bp / 10000
        decimal = float(magnitude) * RATES_BP_SCALE / 10000.0
        for ccy in base.rates:
            shocks.append(FactorShock(RateZero(currency=ccy, tenor="ALL"), decimal))
    else:
        raise ValueError(f"unsupported reverse-stress factor: {factor!r}")
    return tuple(shocks)


def build_reverse_scenario(
    factor: FactorFamily,
    magnitude: float,
    base,
    *,
    scenario_id: str = "reverse",
) -> Scenario:
    """Formal reverse-stress ``Scenario`` for a single factor family move."""
    return Scenario(
        id=scenario_id,
        name=f"Reverse {factor}",
        category=ScenarioCategory.REVERSE,
        description=(
            f"Single-factor reverse stress on {factor}: search magnitude={magnitude}."
        ),
        shocks=build_single_factor_shocks(factor, magnitude, base),
        metadata={"factor_family": factor, "search_magnitude": magnitude},
    )


def _portfolio_mv(pricing_engine: PricingEngine, portfolio: Portfolio, market) -> float:
    return sum(pricing_engine.value(p, market).market_value for p in portfolio.positions)


def evaluate_factor_shock(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    base_market,
    base_mv: float,
    factor: FactorFamily,
    magnitude: float,
) -> tuple[float, float, float]:
    """Return ``(pnl, loss, loss_pct_nav)`` for one shock magnitude."""
    scenario = build_reverse_scenario(factor, magnitude, base_market)
    shocked = apply_scenario(base_market, scenario)
    stressed_mv = _portfolio_mv(pricing_engine, portfolio, shocked)
    pnl = stressed_mv - base_mv
    denom = abs(base_mv) or 1.0
    loss = max(0.0, -pnl)
    return pnl, loss, loss / denom


class ReverseStressEngine:
    """Finds the smallest one-factor shock that reaches a requested loss % of |NAV|."""

    def __init__(self) -> None:
        self.market_data = DemoAggregateMarketDataProvider()

    def solve(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        target_loss_pct: float,
        factor: FactorFamily | str,
        max_shock: float = 0.80,
        *,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        loss_tolerance: float = DEFAULT_LOSS_TOLERANCE,
    ) -> ReverseStressResult:
        if target_loss_pct <= 0:
            raise ValueError("target_loss_pct must be > 0")
        if max_shock <= 0:
            raise ValueError("max_shock must be > 0")
        if factor not in ("equity", "rates", "vol", "fx"):
            raise ValueError(f"unsupported reverse-stress factor: {factor!r}")
        family: FactorFamily = factor  # type: ignore[assignment]

        base_market = self.market_data.snapshot(portfolio)
        base_mv = _portfolio_mv(pricing_engine, portfolio, base_market)
        denom = abs(base_mv) or 1.0
        target_loss = float(target_loss_pct) * denom
        search_bound = from_wire_bound(family, float(max_shock))
        unit = shock_unit_for(family)

        def metrics(magnitude: float) -> tuple[float, float, float]:
            return evaluate_factor_shock(
                portfolio, pricing_engine, base_market, base_mv, family, magnitude
            )

        # Zero-shock baseline (should be ~0 P&L).
        _, _, zero_loss_pct = metrics(0.0)
        if zero_loss_pct + loss_tolerance >= target_loss_pct:
            pnl, _, achieved = metrics(0.0)
            return ReverseStressResult(
                factor=family,
                target_loss_pct=target_loss_pct,
                target_loss=target_loss,
                required_shock=0.0,
                achieved_loss_pct=achieved,
                pnl=pnl,
                converged=True,
                shock_unit=unit,
                base_market_value=base_mv,
                convergence=ReverseStressConvergence(
                    iterations=0,
                    tolerance=loss_tolerance,
                    search_bound=to_wire_shock(family, search_bound),
                    bound_loss_pct=achieved,
                    method="binary_search",
                    message="Target already met at zero shock.",
                ),
            )

        bound_pnl, _, bound_loss_pct = metrics(search_bound)
        if bound_loss_pct + loss_tolerance < target_loss_pct:
            return ReverseStressResult(
                factor=family,
                target_loss_pct=target_loss_pct,
                target_loss=target_loss,
                required_shock=None,
                achieved_loss_pct=bound_loss_pct,
                pnl=bound_pnl,
                converged=False,
                shock_unit=unit,
                base_market_value=base_mv,
                convergence=ReverseStressConvergence(
                    iterations=0,
                    tolerance=loss_tolerance,
                    search_bound=to_wire_shock(family, search_bound),
                    bound_loss_pct=bound_loss_pct,
                    method="binary_search",
                    message="Target loss not reachable within search bound.",
                ),
            )

        lo, hi = 0.0, search_bound
        iterations = 0
        for iterations in range(1, max_iterations + 1):
            mid = 0.5 * (lo + hi)
            _, _, mid_loss = metrics(mid)
            if mid_loss >= target_loss_pct:
                hi = mid
            else:
                lo = mid
            # Early exit when shock bracket is tighter than loss tolerance mapping.
            if (hi - lo) <= max(1e-12, loss_tolerance * search_bound):
                break

        solved_pnl, _, achieved = metrics(hi)
        # Prefer the upper bracket edge so achieved_loss_pct >= target when possible.
        converged = achieved + loss_tolerance >= target_loss_pct
        return ReverseStressResult(
            factor=family,
            target_loss_pct=target_loss_pct,
            target_loss=target_loss,
            required_shock=to_wire_shock(family, hi) if converged else None,
            achieved_loss_pct=achieved,
            pnl=solved_pnl,
            converged=converged,
            shock_unit=unit,
            base_market_value=base_mv,
            convergence=ReverseStressConvergence(
                iterations=iterations,
                tolerance=loss_tolerance,
                search_bound=to_wire_shock(family, search_bound),
                bound_loss_pct=bound_loss_pct,
                method="binary_search",
                message=None if converged else "Solver did not meet target within tolerance.",
            ),
        )


def risk_factors_touched(factor: FactorFamily, base) -> list[RiskFactor]:
    """Risk factors that a single-family reverse scenario would shock on ``base``."""
    return [s.factor for s in build_single_factor_shocks(factor, 1.0, base)]


__all__ = [
    "DEFAULT_LOSS_TOLERANCE",
    "DEFAULT_MAX_ITERATIONS",
    "FactorFamily",
    "RATES_BP_SCALE",
    "ReverseStressEngine",
    "build_reverse_scenario",
    "build_single_factor_shocks",
    "evaluate_factor_shock",
    "from_wire_bound",
    "risk_factors_touched",
    "shock_unit_for",
    "to_wire_shock",
]
