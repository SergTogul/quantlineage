"""Limit breach drill-down (M4.6 / M4.7).

Consumes ``LimitResult`` from ``LimitEngine`` and enriches each selected row with
hierarchy node identity plus the biggest position-level contributors for that
metric. Does not reimplement limit evaluation or touch P&L attribution.

``key_rate_dv01`` contributors use tenor key-rate DV01 on the same binding
pillar as ``LimitEngine`` (max |portfolio KR|), not parallel Valuation.dv01.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.domain.models import (
    Contributor,
    HierarchyLevel,
    HierarchyRef,
    LimitBreachDrilldown,
    LimitDrilldownReport,
    LimitMetric,
    LimitResult,
    LimitScope,
    MarketSnapshot,
    Portfolio,
    Position,
    RiskLimit,
)
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.risk.hierarchy import _ref_path, portfolio_at
from app.risk.historical import HistoricalRiskEngine
from app.risk.limits import DEFAULT_LIMITS, LimitEngine
from app.risk.var import VaRAnalytics

LabelFn = Callable[[Position], str]

# Metrics where position contributions are defined for drill-down.
# key_rate_dv01 is handled separately (tenor KR via SensitivityEngine).
_GREEK_METRICS = frozenset({"dv01", "vega", "fx_delta"})
_VAR_METRICS = frozenset({"var_99", "var_95"})
_ES_METRICS = frozenset({"expected_shortfall_99"})


def _stress_loss_amounts(
    portfolio: Portfolio,
    pricing: PricingEngine,
    market: MarketSnapshot | None = None,
) -> dict[str, float]:
    """Position losses on the worst default stress scenario (loss = max(0, -pnl))."""
    from app.risk.stress import DEFAULT_SCENARIOS, StressEngine

    results = StressEngine().run(portfolio, pricing, DEFAULT_SCENARIOS, market=market)
    if not results:
        return {p.id: 0.0 for p in portfolio.positions}
    worst = max(results, key=lambda r: max(0.0, -float(r.pnl)))
    return {
        p.id: max(0.0, -float(worst.by_position.get(p.id, 0.0)))
        for p in portfolio.positions
    }


def _key_rate_dv01_amounts(
    portfolio: Portfolio,
    pricing: PricingEngine,
    market: MarketSnapshot | None = None,
) -> dict[str, float]:
    """Abs position KR DV01 on the LimitEngine binding pillar.

    ``LimitEngine`` takes ``max_T |portfolio KR_T|``. Contributors use that same
    tenor ``T*`` so signed position KR sum to portfolio KR (within FD tolerance).
    When no key-rate measures exist, fall back to abs parallel ``dv01`` (same as
    ``_key_rate_dv01_abs``).
    """
    from app.risk.factor_types import RateZero
    from app.risk.sensitivities import SensitivityEngine

    sens = SensitivityEngine()
    measures = sens.calculate(
        portfolio, pricing, measures=("key_rate_dv01",), market=market
    )
    if not measures:
        return {
            p.id: abs(float(pricing.value(p, market).dv01 or 0.0))
            for p in portfolio.positions
        }

    binding = max(measures, key=lambda m: abs(m.value))
    factor = binding.factor
    if not isinstance(factor, RateZero):
        return {
            p.id: abs(float(pricing.value(p, market).dv01 or 0.0))
            for p in portfolio.positions
        }

    # Same market the portfolio KR used (engine snapshots when market is None).
    snap = market if market is not None else sens.market_data.snapshot(portfolio)
    bp = sens.rate_bump_bps
    amounts: dict[str, float] = {}
    for p in portfolio.positions:
        up = pricing.value(
            p, SensitivityEngine._bump_key_rate(snap, factor.currency, factor.tenor, bp)
        ).market_value
        down = pricing.value(
            p, SensitivityEngine._bump_key_rate(snap, factor.currency, factor.tenor, -bp)
        ).market_value
        # Match SensitivityEngine._central_scaled(up, down, bp, 1.0) → per-bp.
        kr = (up - down) / (2.0 * bp)
        amounts[p.id] = abs(kr)
    return amounts


def _default_ref(portfolio: Portfolio) -> HierarchyRef:
    return HierarchyRef(
        level=HierarchyLevel.PORTFOLIO,
        firm=portfolio.firm,
        portfolio_id=portfolio.id,
    )


def _level_scope(level: HierarchyLevel) -> LimitScope:
    return level.value  # type: ignore[return-value]


def _rank_amounts(
    amounts: dict[str, float],
    labels: dict[str, str],
    top_n: int,
) -> list[Contributor]:
    total = sum(abs(v) for v in amounts.values())
    ranked = sorted(amounts.items(), key=lambda kv: abs(kv[1]), reverse=True)
    out: list[Contributor] = []
    for pid, amount in ranked[:top_n]:
        out.append(
            Contributor(
                position_id=pid,
                label=labels.get(pid, pid),
                risk_amount=float(amount),
                contribution_pct=(abs(amount) / total * 100.0) if total else 0.0,
            )
        )
    return out


def contributors_for_metric(
    portfolio: Portfolio,
    pricing: PricingEngine,
    metric: str,
    *,
    top_n: int = 5,
    label_fn: LabelFn | None = None,
    var_engine: VaRAnalytics | None = None,
    market: MarketSnapshot | None = None,
) -> list[Contributor]:
    """Biggest position contributors for a limit metric (abs share of total)."""
    labels = {p.id: (label_fn(p) if label_fn else p.id) for p in portfolio.positions}
    if not portfolio.positions:
        return []

    if metric == "single_position_pct":
        amounts = {
            p.id: abs(pricing.value(p, market).market_value) for p in portfolio.positions
        }
        return _rank_amounts(amounts, labels, top_n)

    if metric == "key_rate_dv01":
        return _rank_amounts(
            _key_rate_dv01_amounts(portfolio, pricing, market=market),
            labels,
            top_n,
        )

    if metric in _GREEK_METRICS:
        amounts = {
            p.id: abs(getattr(pricing.value(p, market), metric, 0.0) or 0.0)
            for p in portfolio.positions
        }
        return _rank_amounts(amounts, labels, top_n)

    if metric in _VAR_METRICS or metric in _ES_METRICS:
        engine = var_engine or VaRAnalytics()
        report = engine.report(portfolio, pricing, market=market)
        amounts: dict[str, float] = {}
        for c in report.contributions:
            if metric in _ES_METRICS:
                amounts[c.position_id] = float(c.component_es or 0.0)
            else:
                amounts[c.position_id] = float(c.component_var)
        return _rank_amounts(amounts, labels, top_n)

    if metric == "stress_loss":
        return _rank_amounts(
            _stress_loss_amounts(portfolio, pricing, market=market), labels, top_n
        )

    # Unknown metrics: no position decomposition here.
    return []


def enrich_limit_result(
    result: LimitResult,
    *,
    hierarchy_node: str,
    hierarchy_level: LimitScope,
    contributors: Sequence[Contributor],
) -> LimitBreachDrilldown:
    """Lift a ``LimitResult`` into a drill-down row (preserves M4.5 fields)."""
    return LimitBreachDrilldown(
        hierarchy_node=hierarchy_node,
        hierarchy_level=hierarchy_level,
        metric=result.metric,
        value=result.value,
        limit=result.limit,
        utilization_pct=result.utilization_pct,
        breached=result.breached,
        status=result.status,
        warning_threshold_pct=result.warning_threshold_pct,
        scope=result.scope,
        label=result.label,
        contributors=list(contributors),
    )


class LimitDrilldownEngine:
    """Build hierarchy-scoped limit drill-downs from ``LimitEngine`` results."""

    def __init__(
        self,
        risk: RiskEngine,
        *,
        limit_engine: LimitEngine | None = None,
        var_engine: VaRAnalytics | None = None,
    ):
        self.risk = risk
        self.limit_engine = limit_engine or LimitEngine()
        self.var_engine = var_engine or VaRAnalytics()

    def report(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        *,
        hierarchy: HierarchyRef | None = None,
        metric: LimitMetric | str | None = None,
        limits: list[RiskLimit] | None = None,
        top_n: int = 5,
        breaches_only: bool = True,
        label_fn: LabelFn | None = None,
        market: MarketSnapshot | None = None,
    ) -> LimitDrilldownReport:
        ref = hierarchy or _default_ref(portfolio)
        node_path = _ref_path(portfolio, ref)
        level = _level_scope(ref.level)
        sub = portfolio_at(portfolio, ref)
        # Always the root book's snapshot — never demo_market_snapshot(sub).
        if isinstance(self.risk, HistoricalRiskEngine):
            risk = self.risk.calculate(sub, pricing, market=market)
        else:
            risk = self.risk.calculate(sub, pricing)
        limit_defs = list(limits) if limits is not None else list(DEFAULT_LIMITS)
        if metric is not None:
            limit_defs = [lim for lim in limit_defs if lim.metric == metric]
            if not limit_defs:
                # Metric requested but absent from config: synthesize a probe row
                # so callers can still inspect contributors against engine value.
                raise ValueError(
                    f"metric {metric!r} not present in supplied/default limits"
                )

        results = self.limit_engine.evaluate(
            sub, pricing, risk, limit_defs, market=market
        )
        items: list[LimitBreachDrilldown] = []
        for result in results:
            if breaches_only and not result.breached:
                continue
            contribs = contributors_for_metric(
                sub,
                pricing,
                result.metric,
                top_n=top_n,
                label_fn=label_fn,
                var_engine=self.var_engine,
                market=market,
            )
            items.append(
                enrich_limit_result(
                    result,
                    hierarchy_node=node_path,
                    hierarchy_level=level,
                    contributors=contribs,
                )
            )

        return LimitDrilldownReport(
            portfolio_id=portfolio.id,
            hierarchy_node=node_path,
            hierarchy_level=level,
            items=items,
        )


__all__ = [
    "LimitDrilldownEngine",
    "contributors_for_metric",
    "enrich_limit_result",
]
