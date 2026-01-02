from app.domain.models import (
    Portfolio,
    PositionStressContribution,
    ScenarioEvaluationReport,
    ScenarioKind,
    StressEvaluation,
    StressResult,
    StressScenario,
)
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import PositionMarketDataProvider


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
        description="Equity crash, volatility spike and higher rates occurring together.",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.20,
        vol_shock=0.50,
        rates_shift_bps=125,
        max_loss_pct=0.10,
    ),
]


THREAT_SCENARIOS = [
    StressScenario(
        id="gfc_style",
        name="Global Financial Crisis-style",
        description="Historical-style severe risk-off shock; illustrative, not a replay of observed 2008 paths.",
        kind=ScenarioKind.HISTORICAL_STYLE,
        equity_shock=-0.35,
        vol_shock=1.00,
        rates_shift_bps=-100,
        max_loss_pct=0.15,
    ),
    StressScenario(
        id="covid_style",
        name="COVID Crash-style",
        description="Fast equity drawdown with an extreme volatility expansion; illustrative historical-style scenario.",
        kind=ScenarioKind.HISTORICAL_STYLE,
        equity_shock=-0.30,
        vol_shock=1.50,
        rates_shift_bps=-75,
        max_loss_pct=0.15,
    ),
    StressScenario(
        id="stagflation",
        name="Stagflation Shock",
        description="Equities fall while rates and volatility rise together.",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.20,
        vol_shock=0.60,
        rates_shift_bps=200,
        max_loss_pct=0.12,
    ),
    StressScenario(
        id="tech_crash",
        name="Equity / Tech Crash Proxy",
        description="Large equity shock with elevated volatility, useful for equity-option heavy books.",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.40,
        vol_shock=0.80,
        rates_shift_bps=-50,
        max_loss_pct=0.18,
    ),
    StressScenario(
        id="rate_shock",
        name="Rates Regime Break",
        description="Abrupt 300bp parallel rate increase with moderate volatility expansion.",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.10,
        vol_shock=0.30,
        rates_shift_bps=300,
        max_loss_pct=0.12,
    ),
    StressScenario(
        id="vol_dislocation",
        name="Volatility Dislocation",
        description="Implied volatility doubles while spot and rates are initially unchanged.",
        kind=ScenarioKind.FACTOR,
        vol_shock=1.00,
        max_loss_pct=0.08,
    ),
]


def _threat_level(loss_pct_nav: float) -> str:
    if loss_pct_nav >= 0.15:
        return "SEVERE"
    if loss_pct_nav >= 0.08:
        return "HIGH"
    if loss_pct_nav >= 0.03:
        return "MODERATE"
    return "LOW"


class StressEngine:
    def __init__(self): self.market_data = PositionMarketDataProvider()

    def run(self, portfolio: Portfolio, pricing_engine: PricingEngine, scenarios: list[StressScenario]) -> list[StressResult]:
        market = self.market_data.snapshot(portfolio)
        base = {p.id: pricing_engine.value(p, market).market_value for p in portfolio.positions}
        output = []
        for scenario in scenarios:
            by_position = {
                p.id: pricing_engine.shocked_value(p, scenario, market) - base[p.id]
                for p in portfolio.positions
            }
            output.append(StressResult(
                scenario=scenario.name,
                pnl=sum(by_position.values()),
                by_position=by_position,
            ))
        return output

    def evaluate(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        scenarios: list[StressScenario],
    ) -> ScenarioEvaluationReport:
        market = self.market_data.snapshot(portfolio)
        base_by_position = {p.id: pricing_engine.value(p, market).market_value for p in portfolio.positions}
        base_mv = sum(base_by_position.values())
        nav_denominator = abs(base_mv) or 1.0
        evaluations: list[StressEvaluation] = []

        for index, scenario in enumerate(scenarios):
            by_position = {
                p.id: pricing_engine.shocked_value(p, scenario, market) - base_by_position[p.id]
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
            threshold = scenario.max_loss_pct
            evaluations.append(
                StressEvaluation(
                    scenario_id=scenario.id or f"scenario_{index + 1}",
                    scenario=scenario.name,
                    kind=scenario.kind,
                    description=scenario.description,
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


class ReverseStressEngine:
    """Finds the smallest one-factor shock that reaches a requested loss percentage."""
    def __init__(self): self.engine = StressEngine()

    def solve(self, portfolio, pricing_engine, target_loss_pct: float, factor: str, max_shock: float = 0.80):
        from app.domain.models import ReverseStressResult, StressScenario, ScenarioKind
        base = sum(pricing_engine.value(p).market_value for p in portfolio.positions)
        denom = abs(base) or 1.0
        def scenario(x):
            kwargs={"id":"reverse","name":f"Reverse {factor}","kind":ScenarioKind.REVERSE}
            if factor=="equity": kwargs["equity_shock"]=-x
            elif factor=="vol": kwargs["vol_shock"]=x
            elif factor=="fx": kwargs["fx_shock"]=-x
            elif factor=="rates": kwargs["rates_shift_bps"]=x*1000.0
            return StressScenario(**kwargs)
        def loss_pct(x):
            r=self.engine.run(portfolio,pricing_engine,[scenario(x)])[0]
            return max(0.0,-r.pnl)/denom
        hi_loss=loss_pct(max_shock)
        if hi_loss < target_loss_pct:
            return ReverseStressResult(factor=factor,target_loss_pct=target_loss_pct,required_shock=None,achieved_loss_pct=hi_loss,converged=False)
        lo,hi=0.0,max_shock
        for _ in range(40):
            mid=(lo+hi)/2
            if loss_pct(mid)>=target_loss_pct: hi=mid
            else: lo=mid
        achieved=loss_pct(hi)
        required=hi*1000 if factor=="rates" else hi
        return ReverseStressResult(factor=factor,target_loss_pct=target_loss_pct,required_shock=required,achieved_loss_pct=achieved,converged=True)


class ScenarioComparisonEngine:
    def __init__(self): self.engine=StressEngine()
    def compare(self, base_portfolio, hedged_portfolio, pricing_engine, scenarios):
        from app.domain.models import ScenarioComparison
        a=self.engine.run(base_portfolio,pricing_engine,scenarios); b=self.engine.run(hedged_portfolio,pricing_engine,scenarios)
        return [ScenarioComparison(scenario=x.scenario,base_pnl=x.pnl,hedged_pnl=y.pnl,improvement=y.pnl-x.pnl) for x,y in zip(a,b)]
