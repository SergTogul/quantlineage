"""Stress evaluation, reverse stress, and hedge comparison.

Multi-factor snapshot shocks (equity / rates / FX / vol) live in
``app.risk.scenario_engine`` (M3.2). Named historical crises live in
``app.risk.crisis_library`` (M3.3) as formal HISTORICAL_APPROXIMATION scenarios.
Single-factor reverse stress lives in ``app.risk.reverse_stress`` (M3.5).
Multi-factor reverse stress lives in ``app.risk.reverse_stress_multi`` (M3.6).
Stress loops apply each scenario once via ``apply_scenario``, then revalue
every position on that shared shocked snapshot (``PricingEngine.value``).
``PricingEngine.shocked_value`` remains available for single-position callers.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import (
    FactorExposureChange,
    HedgeComparisonReport,
    MarketSnapshot,
    Portfolio,
    PositionStressContribution,
    RiskFactorExposure,
    RiskSummary,
    ScenarioComparison,
    ScenarioContributionBreakdown,
    ScenarioEvaluationReport,
    ScenarioKind,
    StressEvaluation,
    StressResult,
    StressScenario,
    VaRMethodology,
)
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.risk.crisis_library import CRISIS_STRESS_SCENARIOS
from app.risk.factors import RiskFactorEngine
from app.risk.historical import HistoricalRiskEngine, require_explicit_market
from app.risk.reverse_stress import ReverseStressEngine
from app.risk.reverse_stress_multi import MultiFactorReverseStressEngine
from app.risk.scenario_attribution import ScenarioAttributionEngine, ScenarioLike
from app.risk.scenario_engine import ScenarioEngine, apply_scenario
from app.risk.scenario_model import Scenario, category_to_kind, to_canonical_scenario, to_canonical_scenarios
from app.sample import DemoAggregateMarketDataProvider

__all__ = [
    "DEFAULT_SCENARIOS",
    "THREAT_SCENARIOS",
    "HYPOTHETICAL_THREAT_SCENARIOS",
    "StressEngine",
    "ReverseStressEngine",
    "MultiFactorReverseStressEngine",
    "ScenarioComparisonEngine",
    "ScenarioAttributionEngine",
    "ScenarioEngine",
    "apply_scenario",
]


DEFAULT_SCENARIOS = [
    StressScenario(
        id="eq_down_10",
        name="Equities -10%",
        description="Broad equity selloff with other factors unchanged.",
        kind=ScenarioKind.FACTOR,
        equity_shock=-0.10,
        max_loss_pct=0.06,
    ),
    StressScenario(
        id="rates_up_100",
        name="Rates +100bp",
        description="Parallel upward shift of the rates curve by 100bp.",
        kind=ScenarioKind.FACTOR,
        rates_shift_bps=100,
        max_loss_pct=0.05,
    ),
    StressScenario(
        id="vol_up_25",
        name="Vol +25%",
        description="Relative 25% increase in implied volatility.",
        kind=ScenarioKind.FACTOR,
        vol_shock=0.25,
        max_loss_pct=0.04,
    ),
    StressScenario(
        id="eq_down_vol_up",
        name="Equities -15% / Vol +40%",
        description="Risk-off equity shock with a volatility spike.",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.15,
        vol_shock=0.40,
        max_loss_pct=0.08,
    ),
    StressScenario(
        id="combined_crisis",
        name="Combined Crisis",
        description=(
            "Hypothetical multi-factor crisis (not a named historical episode): "
            "equity crash, volatility spike and higher rates occurring together."
        ),
        kind=ScenarioKind.MACRO,
        equity_shock=-0.20,
        vol_shock=0.50,
        rates_shift_bps=125,
        max_loss_pct=0.10,
    ),
]


# Non-historical hypothetical / factor threats (kept separate from crisis library).
HYPOTHETICAL_THREAT_SCENARIOS = [
    StressScenario(
        id="stagflation",
        name="Stagflation Shock",
        description="Hypothetical: equities fall while rates and volatility rise together.",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.20,
        vol_shock=0.60,
        rates_shift_bps=200,
        max_loss_pct=0.12,
    ),
]

# Crisis library first (HISTORICAL_APPROXIMATION via formal Scenario), then hypotheticals.
# Wire shape remains StressScenario (kind=HISTORICAL_STYLE); honest labeling lives in
# crisis_library descriptions / formal Scenario.category when expanded.
THREAT_SCENARIOS = list(CRISIS_STRESS_SCENARIOS) + list(HYPOTHETICAL_THREAT_SCENARIOS)


def _threat_level(loss_pct_nav: float) -> str:
    if loss_pct_nav >= 0.15:
        return "SEVERE"
    if loss_pct_nav >= 0.08:
        return "HIGH"
    if loss_pct_nav >= 0.03:
        return "MODERATE"
    return "LOW"


def _evaluation_fields(
    scenario: Scenario, index: int
) -> tuple[str, str, ScenarioKind, str, float | None]:
    """Read canonical ``Scenario`` fields for ``StressEvaluation``."""
    return (
        scenario.id or f"scenario_{index + 1}",
        scenario.name,
        category_to_kind(scenario.category),
        scenario.description,
        scenario.threshold.max_loss_pct,
    )


class StressEngine:
    def __init__(self):
        self.market_data = DemoAggregateMarketDataProvider()
        self.attribution = ScenarioAttributionEngine()

    def run(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        scenarios: Sequence[ScenarioLike],
        market: MarketSnapshot | None = None,
    ) -> list[StressResult]:
        """Full-reval stress P&L on canonical ``Scenario``.

        Legacy ``StressScenario`` is adapted once at this boundary via
        ``to_canonical_scenarios`` (HTTP should convert first). Apply uses
        typed ``Scenario`` only — callers need not collapse through
        ``scenario_to_stress``.
        """
        market = require_explicit_market(market)
        scenarios = to_canonical_scenarios(scenarios, market)
        base = {p.id: pricing_engine.value(p, market).market_value for p in portfolio.positions}
        output = []
        for scenario in scenarios:
            shocked = apply_scenario(market, scenario)
            by_position = {
                p.id: pricing_engine.value(p, shocked).market_value - base[p.id]
                for p in portfolio.positions
            }
            output.append(StressResult(
                scenario=scenario.name,
                pnl=sum(by_position.values()),
                by_position=by_position,
            ))
        return output

    def contributions(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        scenario: ScenarioLike,
        *,
        market=None,
        by_trade_pnl: dict[str, float] | None = None,
    ) -> ScenarioContributionBreakdown:
        """Hierarchy + risk-factor stress P&L decomposition for one scenario (M3.4)."""
        market = require_explicit_market(market)
        scenario = to_canonical_scenario(scenario, market)
        return self.attribution.decompose(
            portfolio,
            pricing_engine,
            scenario,
            market=market,
            by_trade_pnl=by_trade_pnl,
        )

    def evaluate(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        scenarios: Sequence[ScenarioLike],
        market: MarketSnapshot | None = None,
    ) -> ScenarioEvaluationReport:
        """Threat evaluation on canonical ``Scenario``.

        Legacy ``StressScenario`` is adapted once at this boundary; internals
        do not branch on the wire type.
        """
        market = require_explicit_market(market)
        scenarios = to_canonical_scenarios(scenarios, market)
        base_by_position = {p.id: pricing_engine.value(p, market).market_value for p in portfolio.positions}
        base_mv = sum(base_by_position.values())
        nav_denominator = abs(base_mv) or 1.0
        evaluations: list[StressEvaluation] = []

        for index, scenario in enumerate(scenarios):
            shocked = apply_scenario(market, scenario)
            by_position = {
                p.id: pricing_engine.value(p, shocked).market_value - base_by_position[p.id]
                for p in portfolio.positions
            }
            pnl = sum(by_position.values())
            stressed_mv = base_mv + pnl
            loss = max(0.0, -pnl)
            loss_pct_nav = loss / nav_denominator
            loss_positions = [(pid, -position_pnl) for pid, position_pnl in by_position.items() if position_pnl < 0]
            total_position_loss = sum(amount for _, amount in loss_positions) or 1.0
            contributors = sorted(
                [
                    PositionStressContribution(
                        position_id=pid,
                        pnl=by_position[pid],
                        contribution_pct=amount / total_position_loss * 100.0,
                    )
                    for pid, amount in loss_positions
                ],
                key=lambda x: x.pnl,
            )[:5]
            scenario_id, name, kind, description, threshold = _evaluation_fields(
                scenario, index
            )
            breakdown = self.contributions(
                portfolio,
                pricing_engine,
                scenario,
                market=market,
                by_trade_pnl=by_position,
            )
            evaluations.append(
                StressEvaluation(
                    scenario_id=scenario_id,
                    scenario=name,
                    kind=kind,
                    description=description,
                    base_market_value=base_mv,
                    stressed_market_value=stressed_mv,
                    pnl=pnl,
                    loss=loss,
                    loss_pct_nav=loss_pct_nav,
                    threat_level=_threat_level(loss_pct_nav),
                    breached=threshold is not None and loss_pct_nav > threshold,
                    max_loss_pct=threshold,
                    by_position=by_position,
                    top_loss_contributors=contributors,
                    contributions=breakdown,
                )
            )

        evaluations.sort(key=lambda x: x.loss, reverse=True)
        worst = evaluations[0] if evaluations else None
        return ScenarioEvaluationReport(
            portfolio_id=portfolio.id,
            base_market_value=base_mv,
            worst_scenario=worst.scenario if worst else None,
            worst_loss=worst.loss if worst else 0.0,
            severe_count=sum(x.threat_level == "SEVERE" for x in evaluations),
            breach_count=sum(x.breached for x in evaluations),
            evaluations=evaluations,
        )


def _diff_factor_exposures(
    before: list[RiskFactorExposure],
    after: list[RiskFactorExposure],
) -> list[FactorExposureChange]:
    bmap = {x.factor: x for x in before}
    amap = {x.factor: x for x in after}
    out: list[FactorExposureChange] = []
    for key in sorted(set(bmap) | set(amap)):
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


def _risk_summary(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    risk_engine: RiskEngine,
    methodology: VaRMethodology,
    market: MarketSnapshot | None = None,
) -> RiskSummary:
    if isinstance(risk_engine, HistoricalRiskEngine):
        raw = risk_engine.calculate(
            portfolio, pricing_engine, methodology=methodology, market=market
        )
    else:
        raw = risk_engine.calculate(portfolio, pricing_engine)
        raw = {**raw, "methodology": methodology.value}
    return RiskSummary(portfolio_id=portfolio.id, **raw)


class ScenarioComparisonEngine:
    """Before/after hedge comparison: scenarios, VaR/ES, cost, factor exposures (M3.7)."""

    def __init__(
        self,
        risk_engine: RiskEngine | None = None,
        factor_engine: RiskFactorEngine | None = None,
    ):
        self.engine = StressEngine()
        self.risk_engine = risk_engine or HistoricalRiskEngine()
        self.factor_engine = factor_engine or RiskFactorEngine()

    def compare(
        self,
        base_portfolio: Portfolio,
        hedged_portfolio: Portfolio,
        pricing_engine: PricingEngine,
        scenarios: Sequence[ScenarioLike],
        *,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
        market: MarketSnapshot | None = None,
    ) -> HedgeComparisonReport:
        market = require_explicit_market(market)
        scenarios = to_canonical_scenarios(scenarios, market)
        base_stress = self.engine.run(
            base_portfolio, pricing_engine, scenarios, market=market
        )
        hedged_stress = self.engine.run(
            hedged_portfolio, pricing_engine, scenarios, market=market
        )
        scenario_rows: list[ScenarioComparison] = []
        for x, y in zip(base_stress, hedged_stress):
            base_loss = max(0.0, -x.pnl)
            hedged_loss = max(0.0, -y.pnl)
            scenario_rows.append(
                ScenarioComparison(
                    scenario=x.scenario,
                    base_pnl=x.pnl,
                    hedged_pnl=y.pnl,
                    improvement=y.pnl - x.pnl,
                    base_loss=base_loss,
                    hedged_loss=hedged_loss,
                    loss_improvement=base_loss - hedged_loss,
                )
            )

        base_risk = _risk_summary(
            base_portfolio, pricing_engine, self.risk_engine, methodology, market=market
        )
        hedged_risk = _risk_summary(
            hedged_portfolio, pricing_engine, self.risk_engine, methodology, market=market
        )
        base_fx = self.factor_engine.calculate(
            base_portfolio, pricing_engine, market=market
        )
        hedged_fx = self.factor_engine.calculate(
            hedged_portfolio, pricing_engine, market=market
        )

        return HedgeComparisonReport(
            hedge_cost=hedged_risk.market_value - base_risk.market_value,
            base_market_value=base_risk.market_value,
            hedged_market_value=hedged_risk.market_value,
            base_var_99=base_risk.var_99,
            hedged_var_99=hedged_risk.var_99,
            base_expected_shortfall_99=base_risk.expected_shortfall_99,
            hedged_expected_shortfall_99=hedged_risk.expected_shortfall_99,
            var_improvement=base_risk.var_99 - hedged_risk.var_99,
            es_improvement=base_risk.expected_shortfall_99 - hedged_risk.expected_shortfall_99,
            methodology=methodology,
            factor_exposure_changes=_diff_factor_exposures(base_fx, hedged_fx),
            scenarios=scenario_rows,
        )
