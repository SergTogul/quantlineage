"""Incremental VaR and what-if portfolio transforms (M2.8 / M2.9).

Methodology
-----------
Incremental VaR for a hypothetical portfolio change is the difference between
risk metrics on the transformed book and the current book:

    IVaR = VaR(P') − VaR(P)

where ``P'`` is obtained by applying add / remove / modify operations to a
deep copy of ``P`` (the persisted or request portfolio is never mutated).

Same definition applies to VaR95, VaR99, and Expected Shortfall 99:

    incremental.metric = after.metric − before.metric

Sign convention (loss VaR, currency units — same as ``HistoricalRiskEngine``):
- positive incremental ⇒ the change *increases* portfolio risk
- negative incremental ⇒ the change is risk-reducing
- zero positions / empty changes ⇒ zero risk / zero incremental

Default methodology is ``DELTA_GAMMA`` (legacy historical Δ-Γ path). Callers
may select ``LINEAR`` or ``FULL_REVALUATION``; all P&L / quantile math is
delegated to ``HistoricalRiskEngine`` (or a compatible ``RiskEngine``).

What-if analysis (M2.9) additionally diffs factor exposures and stress P&Ls
between before and after books without writing any portfolio state.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.domain.models import (
    FactorExposureChange,
    MarketSnapshot,
    Portfolio,
    Position,
    RiskFactorExposure,
    RiskSummary,
    StressLossChange,
    StressResult,
    StressScenario,
    VaRMethodology,
    WhatIfChange,
    WhatIfIncrementalRisk,
    WhatIfReport,
)
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.risk.factors import RiskFactorEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.stress import DEFAULT_SCENARIOS, StressEngine


def _as_change(raw: WhatIfChange | Mapping[str, Any]) -> WhatIfChange:
    if isinstance(raw, WhatIfChange):
        return raw
    return WhatIfChange.model_validate(raw)


def apply_what_if_changes(
    portfolio: Portfolio,
    changes: Sequence[WhatIfChange | Mapping[str, Any]],
) -> Portfolio:
    """Return a new portfolio after add/remove/modify; never mutates ``portfolio``."""
    positions: list[Position] = list(portfolio.positions)
    by_id = {p.id: i for i, p in enumerate(positions)}

    for raw in changes:
        change = _as_change(raw)
        op = change.operation
        if op == "add":
            if change.position is None:
                raise ValueError("add requires position")
            if change.position.id in by_id:
                raise ValueError(f"position id already exists: {change.position.id}")
            positions.append(change.position)
            by_id[change.position.id] = len(positions) - 1
        elif op == "remove":
            pid = change.position_id or (change.position.id if change.position else None)
            if not pid:
                raise ValueError("remove requires position_id")
            if pid not in by_id:
                raise ValueError(f"unknown position: {pid}")
            idx = by_id.pop(pid)
            positions.pop(idx)
            by_id = {p.id: i for i, p in enumerate(positions)}
        elif op == "modify":
            if change.position is None:
                raise ValueError("modify requires position")
            pid = change.position_id or change.position.id
            if pid not in by_id:
                raise ValueError(f"unknown position: {pid}")
            if change.position.id != pid and change.position.id in by_id:
                raise ValueError(f"position id already exists: {change.position.id}")
            idx = by_id[pid]
            positions[idx] = change.position
            if change.position.id != pid:
                by_id.pop(pid)
                by_id[change.position.id] = idx
        else:
            raise ValueError(f"unsupported operation: {op}")

    return portfolio.model_copy(update={"positions": positions})


def _calculate(
    portfolio: Portfolio,
    pricing: PricingEngine,
    risk_engine: RiskEngine,
    methodology: VaRMethodology,
    market: MarketSnapshot | None = None,
) -> RiskSummary:
    if isinstance(risk_engine, HistoricalRiskEngine):
        return risk_engine.calculate(
            portfolio, pricing, methodology=methodology, market=market
        )
    result = risk_engine.calculate(portfolio, pricing)
    if result.methodology == methodology:
        return result
    return result.model_copy(update={"methodology": methodology})


def _incremental(before: RiskSummary, after: RiskSummary) -> WhatIfIncrementalRisk:
    return WhatIfIncrementalRisk(
        market_value=after.market_value - before.market_value,
        delta=after.delta - before.delta,
        gamma=after.gamma - before.gamma,
        vega=after.vega - before.vega,
        dv01=after.dv01 - before.dv01,
        fx_delta=after.fx_delta - before.fx_delta,
        var_95=after.var_95 - before.var_95,
        var_99=after.var_99 - before.var_99,
        expected_shortfall_99=after.expected_shortfall_99 - before.expected_shortfall_99,
    )


def incremental_var(
    portfolio: Portfolio,
    pricing: PricingEngine,
    *,
    changes: Sequence[WhatIfChange | Mapping[str, Any]],
    risk_engine: RiskEngine | None = None,
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    market: MarketSnapshot | None = None,
) -> WhatIfReport:
    """Compute before/after risk and incremental VaR for hypothetical changes.

    Does not compute factor/stress diffs (those are filled by ``what_if_analysis``).
    After-book risk uses the same ``market`` as the before book when supplied.
    """
    engine = risk_engine or HistoricalRiskEngine()
    after_portfolio = apply_what_if_changes(portfolio, changes)
    before = _calculate(portfolio, pricing, engine, methodology, market)
    after = _calculate(after_portfolio, pricing, engine, methodology, market)
    return WhatIfReport(
        portfolio_id=portfolio.id,
        methodology=methodology,
        before=before,
        after=after,
        incremental=_incremental(before, after),
        changed_factor_exposures=[],
        changed_stress_losses=[],
    )


def _exposure_map(items: list[RiskFactorExposure]) -> dict[str, RiskFactorExposure]:
    return {x.factor: x for x in items}


def _diff_exposures(
    before: list[RiskFactorExposure],
    after: list[RiskFactorExposure],
) -> list[FactorExposureChange]:
    bmap, amap = _exposure_map(before), _exposure_map(after)
    keys = sorted(set(bmap) | set(amap))
    out: list[FactorExposureChange] = []
    for key in keys:
        b = bmap.get(key)
        a = amap.get(key)
        b_exp = b.exposure if b else 0.0
        a_exp = a.exposure if a else 0.0
        delta = a_exp - b_exp
        if delta == 0.0:
            continue
        meta = a or b
        assert meta is not None
        out.append(
            FactorExposureChange(
                factor=key,
                factor_type=meta.factor_type,
                bucket=meta.bucket,
                before=b_exp,
                after=a_exp,
                delta=delta,
            )
        )
    out.sort(key=lambda x: abs(x.delta), reverse=True)
    return out


def _stress_map(results: list[StressResult]) -> dict[str, StressResult]:
    return {r.scenario: r for r in results}


def _diff_stress(
    before: list[StressResult],
    after: list[StressResult],
) -> list[StressLossChange]:
    bmap, amap = _stress_map(before), _stress_map(after)
    keys = sorted(set(bmap) | set(amap))
    out: list[StressLossChange] = []
    for key in keys:
        b_pnl = bmap[key].pnl if key in bmap else 0.0
        a_pnl = amap[key].pnl if key in amap else 0.0
        out.append(
            StressLossChange(
                scenario=key,
                before_pnl=b_pnl,
                after_pnl=a_pnl,
                delta_pnl=a_pnl - b_pnl,
            )
        )
    out.sort(key=lambda x: x.delta_pnl)  # most adverse (more negative) first
    return out


def what_if_analysis(
    portfolio: Portfolio,
    pricing: PricingEngine,
    *,
    changes: Sequence[WhatIfChange | Mapping[str, Any]],
    risk_engine: RiskEngine | None = None,
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    factor_engine: RiskFactorEngine | None = None,
    stress_engine: StressEngine | None = None,
    scenarios: list[StressScenario] | None = None,
    market: MarketSnapshot | None = None,
) -> WhatIfReport:
    """Full what-if: incremental VaR plus factor exposure and stress P&L diffs.

    ``market`` is the single base snapshot for before and after books. Mutated
    add/remove books must not re-infer marks from the changed position set.
    """
    engine = risk_engine or HistoricalRiskEngine()
    factors = factor_engine or RiskFactorEngine()
    stress = stress_engine or StressEngine()
    scen = scenarios if scenarios is not None else DEFAULT_SCENARIOS

    after_portfolio = apply_what_if_changes(portfolio, changes)
    before = _calculate(portfolio, pricing, engine, methodology, market)
    after = _calculate(after_portfolio, pricing, engine, methodology, market)

    before_fx = factors.calculate(portfolio, pricing, market)
    after_fx = factors.calculate(after_portfolio, pricing, market)
    before_stress = stress.run(portfolio, pricing, scen, market=market)
    after_stress = stress.run(after_portfolio, pricing, scen, market=market)

    return WhatIfReport(
        portfolio_id=portfolio.id,
        methodology=methodology,
        before=before,
        after=after,
        incremental=_incremental(before, after),
        changed_factor_exposures=_diff_exposures(before_fx, after_fx),
        changed_stress_losses=_diff_stress(before_stress, after_stress),
    )
