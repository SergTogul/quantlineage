"""Constrained multi-factor reverse stress (M3.6).

Answers: which joint adverse moves across factor families reach a target loss
fraction of |NAV|, under an explicit L2-normalized box constraint.

Assumptions
-----------
1. **Adverse orthant** (same as M3.5 single-factor): equity/FX relative down,
   vol relative up, rates parallel up.
2. **Objective**: minimize ``‖u‖₂`` where ``u_i = s_i / max_i``, ``s_i`` is the
   internal search magnitude for family ``i``, and ``max_i`` is the per-family
   bound. Equivalent to minimize √(Σ u_i²) s.t. loss_pct ≥ target and
   ``0 ≤ u_i ≤ 1``.
3. **Loss**: ``loss = max(0, -pnl)``; ``loss_pct = loss / |base_mv|``.
4. **Monotonicity**: loss is assumed non-decreasing in each adverse magnitude
   (not guaranteed for every book; documented, not proven).
5. **Algorithm**:
   a. Feasibility at the box corner (all selected families at max).
   b. Ray search along non-negative weights (default equal) to a feasible point.
   c. Coordinate descent: for each family, binary-search the smallest magnitude
      that keeps loss ≥ target with others fixed; repeat until L2 stalls.
6. **Not a global optimum**: greedy refinement from the ray solution; deterministic
   (no RNG), fixed iteration caps.
7. **Reuse**: builds on M3.5 ``build_single_factor_shocks`` / wire-unit helpers;
   does not modify the single-factor solver.

Wire units per factor match M3.5 (relative for equity/vol/fx; bp for rates).
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

from app.domain.models import (
    FactorShockSolution,
    MarketSnapshot,
    MultiFactorReverseStressResult,
    Portfolio,
)
from app.interfaces.pricing import PricingEngine
from app.risk.historical import require_explicit_market
from app.risk.reverse_stress import (
    DEFAULT_LOSS_TOLERANCE,
    DEFAULT_MAX_ITERATIONS,
    FactorFamily,
    build_single_factor_shocks,
    from_wire_bound,
    shock_unit_for,
    to_wire_shock,
)
from app.risk.scenario_engine import apply_scenario
from app.risk.scenario_model import FactorShock, Scenario, ScenarioCategory
from app.sample import DemoAggregateMarketDataProvider

DEFAULT_FACTORS: tuple[FactorFamily, ...] = ("equity", "rates", "vol", "fx")
DEFAULT_COORDINATE_PASSES = 8

ASSUMPTIONS: tuple[str, ...] = (
    "Adverse orthant: equity/FX down, vol up, rates up (parallel).",
    "Minimize L2 of magnitudes normalized by per-factor search bounds.",
    "loss = max(0,-pnl); loss_pct = loss / |NAV|.",
    "Loss assumed monotone in each adverse magnitude (not guaranteed).",
    "Ray search then coordinate descent; not a certified global optimum.",
    "Wire units: relative (equity/vol/fx) or bp (rates), same as M3.5.",
)


def build_multi_factor_shocks(
    magnitudes: Mapping[str, float],
    base,
) -> tuple[FactorShock, ...]:
    """Compose typed shocks for several factor families at once."""
    shocks: list[FactorShock] = []
    for factor, magnitude in magnitudes.items():
        if magnitude == 0.0:
            continue
        if factor not in ("equity", "rates", "vol", "fx"):
            raise ValueError(f"unsupported reverse-stress factor: {factor!r}")
        shocks.extend(build_single_factor_shocks(factor, float(magnitude), base))  # type: ignore[arg-type]
    return tuple(shocks)


def build_multi_reverse_scenario(
    magnitudes: Mapping[str, float],
    base,
    *,
    scenario_id: str = "reverse_multi",
) -> Scenario:
    return Scenario(
        id=scenario_id,
        name="Reverse multi-factor",
        category=ScenarioCategory.REVERSE,
        description="Constrained multi-factor reverse stress (M3.6).",
        shocks=build_multi_factor_shocks(magnitudes, base),
        metadata={"magnitudes": dict(magnitudes)},
    )


def _portfolio_mv(pricing_engine: PricingEngine, portfolio: Portfolio, market) -> float:
    return sum(pricing_engine.value(p, market).market_value for p in portfolio.positions)


def evaluate_multi_shock(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    base_market,
    base_mv: float,
    magnitudes: Mapping[str, float],
) -> tuple[float, float, float]:
    """Return ``(pnl, loss, loss_pct_nav)`` for a multi-factor magnitude map."""
    scenario = build_multi_reverse_scenario(magnitudes, base_market)
    shocked = apply_scenario(base_market, scenario)
    stressed_mv = _portfolio_mv(pricing_engine, portfolio, shocked)
    pnl = stressed_mv - base_mv
    denom = abs(base_mv) or 1.0
    loss = max(0.0, -pnl)
    return pnl, loss, loss / denom


def _normalized_l2(magnitudes: Mapping[str, float], bounds: Mapping[str, float]) -> float:
    acc = 0.0
    for f, mag in magnitudes.items():
        b = bounds[f]
        if b <= 0:
            continue
        u = mag / b
        acc += u * u
    return math.sqrt(acc)


def _normalize_weights(
    factors: Sequence[FactorFamily],
    weights: Mapping[str, float] | None,
) -> dict[str, float]:
    raw = {f: float(weights.get(f, 1.0)) if weights else 1.0 for f in factors}
    for f, w in raw.items():
        if w < 0:
            raise ValueError(f"weight for {f} must be >= 0")
    peak = max(raw.values()) if raw else 0.0
    if peak <= 0:
        raise ValueError("at least one positive weight is required")
    return {f: raw[f] / peak for f in factors}


def _resolve_bounds(
    factors: Sequence[FactorFamily],
    max_shock: float,
    max_shocks: Mapping[str, float] | None,
) -> dict[str, float]:
    """Internal search magnitudes per family."""
    out: dict[str, float] = {}
    for f in factors:
        wire = float(max_shocks[f]) if max_shocks and f in max_shocks else float(max_shock)
        if wire <= 0:
            raise ValueError(f"max_shock for {f} must be > 0")
        out[f] = from_wire_bound(f, wire)
    return out


def _ray_point(
    scale: float,
    factors: Sequence[FactorFamily],
    weights: Mapping[str, float],
    bounds: Mapping[str, float],
) -> dict[str, float]:
    """``scale`` in [0, 1] along weighted box direction."""
    return {f: scale * weights[f] * bounds[f] for f in factors}


class MultiFactorReverseStressEngine:
    """Constrained multi-factor reverse stress via ray search + coordinate descent."""

    def __init__(self) -> None:
        self.market_data = DemoAggregateMarketDataProvider()

    def solve(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        target_loss_pct: float,
        *,
        factors: Iterable[str] | None = None,
        weights: Mapping[str, float] | None = None,
        max_shock: float = 0.80,
        max_shocks: Mapping[str, float] | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        loss_tolerance: float = DEFAULT_LOSS_TOLERANCE,
        coordinate_passes: int = DEFAULT_COORDINATE_PASSES,
        market: MarketSnapshot | None = None,
    ) -> MultiFactorReverseStressResult:
        if target_loss_pct <= 0:
            raise ValueError("target_loss_pct must be > 0")
        if max_shock <= 0:
            raise ValueError("max_shock must be > 0")

        selected: list[FactorFamily] = []
        raw_factors = list(factors) if factors is not None else list(DEFAULT_FACTORS)
        if not raw_factors:
            raise ValueError("factors must be non-empty")
        for f in raw_factors:
            if f not in ("equity", "rates", "vol", "fx"):
                raise ValueError(f"unsupported reverse-stress factor: {f!r}")
            if f not in selected:
                selected.append(f)  # type: ignore[arg-type]

        w = _normalize_weights(selected, weights)
        bounds = _resolve_bounds(selected, max_shock, max_shocks)

        base_market = require_explicit_market(market)
        base_mv = _portfolio_mv(pricing_engine, portfolio, base_market)
        denom = abs(base_mv) or 1.0
        target_loss = float(target_loss_pct) * denom

        def metrics(mags: Mapping[str, float]) -> tuple[float, float, float]:
            return evaluate_multi_shock(
                portfolio, pricing_engine, base_market, base_mv, mags
            )

        zero = {f: 0.0 for f in selected}
        zero_pnl, _, zero_loss = metrics(zero)
        if zero_loss + loss_tolerance >= target_loss_pct:
            return MultiFactorReverseStressResult(
                target_loss_pct=target_loss_pct,
                target_loss=target_loss,
                achieved_loss_pct=zero_loss,
                pnl=zero_pnl,
                base_market_value=base_mv,
                converged=True,
                objective_l2=0.0,
                shocks=[
                    FactorShockSolution(
                        factor=f,
                        required_shock=0.0,
                        shock_unit=shock_unit_for(f),
                        weight=w[f],
                        max_shock=to_wire_shock(f, bounds[f]),
                    )
                    for f in selected
                ],
                factors=list(selected),
                method="ray_search_coordinate_descent",
                iterations=0,
                message="Target already met at zero shock.",
                assumptions=list(ASSUMPTIONS),
            )

        corner = {f: bounds[f] for f in selected}
        corner_pnl, _, corner_loss = metrics(corner)
        if corner_loss + loss_tolerance < target_loss_pct:
            return MultiFactorReverseStressResult(
                target_loss_pct=target_loss_pct,
                target_loss=target_loss,
                achieved_loss_pct=corner_loss,
                pnl=corner_pnl,
                base_market_value=base_mv,
                converged=False,
                objective_l2=_normalized_l2(corner, bounds),
                shocks=[
                    FactorShockSolution(
                        factor=f,
                        required_shock=to_wire_shock(f, bounds[f]),
                        shock_unit=shock_unit_for(f),
                        weight=w[f],
                        max_shock=to_wire_shock(f, bounds[f]),
                    )
                    for f in selected
                ],
                factors=list(selected),
                method="ray_search_coordinate_descent",
                iterations=0,
                message="Target loss not reachable within multi-factor search bounds.",
                assumptions=list(ASSUMPTIONS),
            )

        # Ray search: scale in [0, 1] along weighted direction.
        lo, hi = 0.0, 1.0
        ray_iters = 0
        for ray_iters in range(1, max_iterations + 1):
            mid = 0.5 * (lo + hi)
            _, _, mid_loss = metrics(_ray_point(mid, selected, w, bounds))
            if mid_loss >= target_loss_pct:
                hi = mid
            else:
                lo = mid
            if (hi - lo) <= max(1e-12, loss_tolerance):
                break

        mags = _ray_point(hi, selected, w, bounds)
        total_iters = ray_iters

        # Coordinate descent: shrink each family while preserving feasibility.
        for _ in range(max(0, coordinate_passes)):
            prev_l2 = _normalized_l2(mags, bounds)
            for f in selected:
                # Can we drop this factor entirely?
                trial = dict(mags)
                trial[f] = 0.0
                _, _, trial_loss = metrics(trial)
                if trial_loss + loss_tolerance >= target_loss_pct:
                    mags[f] = 0.0
                    continue
                clo, chi = 0.0, mags[f]
                for _ in range(max_iterations):
                    cmid = 0.5 * (clo + chi)
                    trial[f] = cmid
                    _, _, c_loss = metrics(trial)
                    if c_loss >= target_loss_pct:
                        chi = cmid
                    else:
                        clo = cmid
                    if (chi - clo) <= max(1e-12, loss_tolerance * bounds[f]):
                        break
                mags[f] = chi
                total_iters += 1
            new_l2 = _normalized_l2(mags, bounds)
            if abs(prev_l2 - new_l2) <= loss_tolerance:
                break

        pnl, _, achieved = metrics(mags)
        converged = achieved + loss_tolerance >= target_loss_pct
        return MultiFactorReverseStressResult(
            target_loss_pct=target_loss_pct,
            target_loss=target_loss,
            achieved_loss_pct=achieved,
            pnl=pnl,
            base_market_value=base_mv,
            converged=converged,
            objective_l2=_normalized_l2(mags, bounds) if converged else None,
            shocks=[
                FactorShockSolution(
                    factor=f,
                    required_shock=to_wire_shock(f, mags[f]) if converged else to_wire_shock(f, bounds[f]),
                    shock_unit=shock_unit_for(f),
                    weight=w[f],
                    max_shock=to_wire_shock(f, bounds[f]),
                )
                for f in selected
            ],
            factors=list(selected),
            method="ray_search_coordinate_descent",
            iterations=total_iters,
            message=None if converged else "Solver did not meet target within tolerance.",
            assumptions=list(ASSUMPTIONS),
        )


__all__ = [
    "ASSUMPTIONS",
    "DEFAULT_COORDINATE_PASSES",
    "DEFAULT_FACTORS",
    "MultiFactorReverseStressEngine",
    "build_multi_factor_shocks",
    "build_multi_reverse_scenario",
    "evaluate_multi_shock",
]
