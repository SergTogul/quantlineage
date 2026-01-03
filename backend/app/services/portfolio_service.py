from app.domain.models import (
    BondPosition,
    Contributor,
    EquityFuturePosition,
    EquityPosition,
    ESContributionReport,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    HierarchyRef,
    InterestRateFuturePosition,
    LimitDrilldownReport,
    LimitDrilldownRequest,
    LimitMetric,
    Portfolio,
    Position,
    RiskChangeAttributionReport,
    RiskChangeAttributionRequest,
    RiskLimit,
    RiskSummary,
    ScenarioEvaluationReport,
    StressResult,
    StressScenario,
    SwapPosition,
    VaRMethodology,
    VaRMethodologyComparison,
    WhatIfReport,
    WhatIfRequest,
)
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.market.snapshot import PositionMarketDataProvider
from app.risk.attribution import AttributionEngine
from app.risk.factors import RiskFactorEngine
from app.risk.hierarchy import HierarchyEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.limit_drilldown import LimitDrilldownEngine
from app.risk.limits import DEFAULT_LIMITS, LimitEngine
from app.risk.query import RiskQueryEngine
from app.risk.risk_attribution import RiskChangeAttributionEngine
from app.risk.stress import (
    DEFAULT_SCENARIOS,
    THREAT_SCENARIOS,
    MultiFactorReverseStressEngine,
    ReverseStressEngine,
    ScenarioComparisonEngine,
    StressEngine,
)
from app.risk.es import ESContributionAnalytics
from app.risk.var import VaRAnalytics


def position_label(position: Position) -> str:
    """Human-readable trade label that distinguishes instrument type."""
    if isinstance(position, EquityPosition):
        return f"{position.symbol} equity"
    if isinstance(position, EquityFuturePosition):
        return f"{position.symbol} future"
    if isinstance(position, EuropeanOptionPosition):
        return f"{position.symbol} {position.option_type}"
    if isinstance(position, BondPosition):
        return position.issuer
    if isinstance(position, SwapPosition):
        tenor = (
            f"{int(position.maturity_years)}Y"
            if position.maturity_years == int(position.maturity_years)
            else f"{position.maturity_years}Y"
        )
        return f"{position.currency} {tenor} swap"
    if isinstance(position, FXForwardPosition):
        return f"{position.pair} fwd"
    if isinstance(position, FXOptionPosition):
        return f"{position.pair} {position.option_type}"
    if isinstance(position, InterestRateFuturePosition):
        return f"{position.currency} IR future"
    return position.id


class PortfolioService:
    def __init__(self, pricing: PricingEngine, risk: RiskEngine):
        self.pricing = pricing
        self.risk = risk
        self.market_data = PositionMarketDataProvider()
        self.stress_engine = StressEngine()
        self.reverse_stress_engine = ReverseStressEngine()
        self.multi_reverse_stress_engine = MultiFactorReverseStressEngine()
        self.limit_engine = LimitEngine()
        self.var_engine = VaRAnalytics()
        self.limit_drilldown_engine = LimitDrilldownEngine(
            risk, limit_engine=self.limit_engine, var_engine=self.var_engine
        )
        self.factor_engine = RiskFactorEngine(self.market_data)
        self.scenario_comparison_engine = ScenarioComparisonEngine(
            risk_engine=risk if isinstance(risk, HistoricalRiskEngine) else HistoricalRiskEngine(),
            factor_engine=self.factor_engine,
        )
        self.es_engine = ESContributionAnalytics()
        self.hierarchy_engine = HierarchyEngine(risk)
        self.attribution_engine = AttributionEngine(self.market_data)
        self.risk_change_engine = RiskChangeAttributionEngine(
            risk_engine=risk if isinstance(risk, HistoricalRiskEngine) else HistoricalRiskEngine(),
            market_data=self.market_data,
        )
        self.query_engine = RiskQueryEngine()

    def market_snapshot(self, portfolio: Portfolio): return self.market_data.snapshot(portfolio)

    def summary(
        self,
        portfolio: Portfolio,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    ) -> RiskSummary:
        if isinstance(self.risk, HistoricalRiskEngine):
            r = self.risk.calculate(portfolio, self.pricing, methodology=methodology)
        else:
            r = self.risk.calculate(portfolio, self.pricing)
            r = {**r, "methodology": methodology.value}
        return RiskSummary(portfolio_id=portfolio.id, **r)

    def stresses(self, portfolio: Portfolio, scenarios: list[StressScenario] | None = None) -> list[StressResult]:
        return self.stress_engine.run(portfolio, self.pricing, scenarios or DEFAULT_SCENARIOS)

    def threat_evaluation(self, portfolio: Portfolio, scenarios: list[StressScenario] | None = None) -> ScenarioEvaluationReport:
        return self.stress_engine.evaluate(portfolio, self.pricing, scenarios or THREAT_SCENARIOS)

    def reverse_stress(self, portfolio, target_loss_pct, factor, max_shock=.80):
        return self.reverse_stress_engine.solve(portfolio,self.pricing,target_loss_pct,factor,max_shock)

    def reverse_stress_multi(
        self,
        portfolio,
        target_loss_pct,
        *,
        factors=None,
        weights=None,
        max_shock=0.80,
        max_shocks=None,
    ):
        """Constrained multi-factor reverse stress (M3.6)."""
        return self.multi_reverse_stress_engine.solve(
            portfolio,
            self.pricing,
            target_loss_pct,
            factors=factors,
            weights=weights,
            max_shock=max_shock,
            max_shocks=max_shocks,
        )

    def compare_scenarios(self, base, hedged, scenarios, methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA):
        """Hedge comparison with VaR/ES/cost/exposures (M3.7)."""
        return self.scenario_comparison_engine.compare(
            base, hedged, self.pricing, scenarios, methodology=methodology
        )

    def factors(self, portfolio): return self.factor_engine.calculate(portfolio,self.pricing)

    def var_report(
        self,
        portfolio: Portfolio,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    ):
        return self.var_engine.report(portfolio, self.pricing, methodology=methodology)

    def es_contributions(
        self,
        portfolio: Portfolio,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
        confidence: float = 0.99,
    ) -> ESContributionReport:
        """Historical Expected Shortfall contributions (M2.5)."""
        if isinstance(self.risk, HistoricalRiskEngine):
            engine = ESContributionAnalytics(
                seed=self.risk.seed,
                observations=self.risk.observations,
                dataset=self.risk.dataset,
                methodology=methodology,
            )
        else:
            engine = self.es_engine
        return engine.report(
            portfolio, self.pricing, confidence=confidence, methodology=methodology
        )

    def compare_var_methodologies(
        self,
        portfolio: Portfolio,
        *,
        observations: int | None = None,
        methodologies: list[VaRMethodology] | None = None,
    ) -> VaRMethodologyComparison:
        """Side-by-side LINEAR / DELTA_GAMMA / FULL_REVALUATION VaR (M2.4)."""
        from app.risk.var_compare import compare_methodologies

        if isinstance(self.risk, HistoricalRiskEngine):
            if observations is not None and observations != self.risk.observations:
                engine = HistoricalRiskEngine(seed=self.risk.seed, observations=observations)
            else:
                engine = self.risk
        else:
            engine = HistoricalRiskEngine(observations=observations or 750)
        return compare_methodologies(
            portfolio,
            self.pricing,
            risk_engine=engine,
            methodologies=methodologies,
        )

    def what_if(
        self,
        request: WhatIfRequest,
        *,
        methodology: VaRMethodology | None = None,
    ) -> WhatIfReport:
        """Hypothetical add/remove/modify trades; does not mutate request.portfolio (M2.9)."""
        from app.risk.incremental_var import what_if_analysis

        meth = methodology if methodology is not None else request.methodology
        return what_if_analysis(
            request.portfolio,
            self.pricing,
            changes=request.changes,
            risk_engine=self.risk if isinstance(self.risk, HistoricalRiskEngine) else None,
            methodology=meth,
            factor_engine=self.factor_engine,
            stress_engine=self.stress_engine,
            scenarios=request.scenarios,
        )

    def hierarchy(self, portfolio): return self.hierarchy_engine.build(portfolio,self.pricing)
    def attribution(self, request): return self.attribution_engine.explain(request,self.pricing)
    def risk_change_attribution(
        self, request: RiskChangeAttributionRequest
    ) -> RiskChangeAttributionReport:
        return self.risk_change_engine.explain(request, self.pricing)
    def demo_attribution(self, portfolio):
        from app.domain.models import AttributionRequest
        current=self.market_data.snapshot(portfolio)
        previous=current.model_copy(update={
            "id":"illustrative_previous",
            "as_of":"illustrative_previous",
            "equity_spots":{k:v*.99 for k,v in current.equity_spots.items()},
            "equity_vols":{k:v*.95 for k,v in current.equity_vols.items()},
            "fx_spots":{k:v*.995 for k,v in current.fx_spots.items()},
            "fx_vols":{k:v*.95 for k,v in current.fx_vols.items()},
            "rates":{k:v-.001 for k,v in current.rates.items()},
        })
        # One business day of theta on options/futures with maturity.
        return self.attribution(AttributionRequest(
            previous_portfolio=portfolio,
            current_portfolio=portfolio,
            previous_market=previous,
            current_market=current,
            dt_years=1.0 / 252.0,
        ))
    def query(self, portfolio, question): return self.query_engine.answer(question,portfolio,self)

    def contributors(self, portfolio: Portfolio) -> list[Contributor]:
        """Rank positions by parametric component VaR with distinct trade labels."""
        report = self.var_engine.report(portfolio, self.pricing)
        labels = {p.id: position_label(p) for p in portfolio.positions}
        return [
            Contributor(
                position_id=c.position_id,
                label=labels.get(c.position_id, c.position_id),
                risk_amount=c.component_var,
                contribution_pct=c.contribution_pct,
            )
            for c in report.contributions
        ]

    def limits(self, portfolio: Portfolio):
        risk = self.risk.calculate(portfolio, self.pricing)
        stress = self.stress_engine.run(portfolio, self.pricing, DEFAULT_SCENARIOS)
        enriched = {
            **risk,
            "stress_loss": max(0.0, max((-float(s.pnl) for s in stress), default=0.0)),
        }
        return self.limit_engine.evaluate(portfolio, self.pricing, enriched, DEFAULT_LIMITS)

    def limit_drilldown(
        self,
        request: LimitDrilldownRequest | None = None,
        *,
        portfolio: Portfolio | None = None,
        metric: LimitMetric | None = None,
        hierarchy: HierarchyRef | None = None,
        limits: list[RiskLimit] | None = None,
        top_n: int = 5,
        breaches_only: bool = True,
    ) -> LimitDrilldownReport:
        """Hierarchy-scoped limit drill-down with top contributors (M4.6)."""
        if request is not None:
            portfolio = request.portfolio
            metric = request.metric
            hierarchy = request.hierarchy
            limits = request.limits
            top_n = request.top_n
            breaches_only = request.breaches_only
        if portfolio is None:
            raise ValueError("portfolio is required")
        return self.limit_drilldown_engine.report(
            portfolio,
            self.pricing,
            hierarchy=hierarchy,
            metric=metric,
            limits=limits,
            top_n=top_n,
            breaches_only=breaches_only,
            label_fn=position_label,
        )
