from app.domain.models import Contributor, Portfolio, RiskSummary, ScenarioEvaluationReport, StressResult, StressScenario
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.market.snapshot import PositionMarketDataProvider
from app.risk.attribution import AttributionEngine
from app.risk.factors import RiskFactorEngine
from app.risk.hierarchy import HierarchyEngine
from app.risk.limits import DEFAULT_LIMITS, LimitEngine
from app.risk.query import RiskQueryEngine
from app.risk.stress import DEFAULT_SCENARIOS, THREAT_SCENARIOS, ReverseStressEngine, ScenarioComparisonEngine, StressEngine
from app.risk.var import VaRAnalytics


class PortfolioService:
    def __init__(self, pricing: PricingEngine, risk: RiskEngine):
        self.pricing = pricing
        self.risk = risk
        self.market_data = PositionMarketDataProvider()
        self.stress_engine = StressEngine()
        self.reverse_stress_engine = ReverseStressEngine()
        self.scenario_comparison_engine = ScenarioComparisonEngine()
        self.limit_engine = LimitEngine()
        self.factor_engine = RiskFactorEngine(self.market_data)
        self.var_engine = VaRAnalytics()
        self.hierarchy_engine = HierarchyEngine(risk)
        self.attribution_engine = AttributionEngine(self.market_data)
        self.query_engine = RiskQueryEngine()

    def market_snapshot(self, portfolio: Portfolio): return self.market_data.snapshot(portfolio)

    def summary(self, portfolio: Portfolio) -> RiskSummary:
        r = self.risk.calculate(portfolio, self.pricing)
        return RiskSummary(portfolio_id=portfolio.id, **r)

    def stresses(self, portfolio: Portfolio, scenarios: list[StressScenario] | None = None) -> list[StressResult]:
        return self.stress_engine.run(portfolio, self.pricing, scenarios or DEFAULT_SCENARIOS)

    def threat_evaluation(self, portfolio: Portfolio, scenarios: list[StressScenario] | None = None) -> ScenarioEvaluationReport:
        return self.stress_engine.evaluate(portfolio, self.pricing, scenarios or THREAT_SCENARIOS)

    def reverse_stress(self, portfolio, target_loss_pct, factor, max_shock=.80):
        return self.reverse_stress_engine.solve(portfolio,self.pricing,target_loss_pct,factor,max_shock)

    def compare_scenarios(self, base, hedged, scenarios):
        return self.scenario_comparison_engine.compare(base,hedged,self.pricing,scenarios)

    def factors(self, portfolio): return self.factor_engine.calculate(portfolio,self.pricing)
    def var_report(self, portfolio): return self.var_engine.report(portfolio,self.pricing)
    def hierarchy(self, portfolio): return self.hierarchy_engine.build(portfolio,self.pricing)
    def attribution(self, request): return self.attribution_engine.explain(request,self.pricing)
    def demo_attribution(self, portfolio):
        from app.domain.models import AttributionRequest
        current=self.market_data.snapshot(portfolio)
        previous=current.model_copy(update={
            "id":"illustrative_previous",
            "equity_spots":{k:v*.99 for k,v in current.equity_spots.items()},
            "equity_vols":{k:v*.95 for k,v in current.equity_vols.items()},
            "fx_spots":{k:v*.995 for k,v in current.fx_spots.items()},
            "fx_vols":{k:v*.95 for k,v in current.fx_vols.items()},
            "rates":{k:v-.001 for k,v in current.rates.items()},
        })
        return self.attribution(AttributionRequest(previous_portfolio=portfolio,current_portfolio=portfolio,previous_market=previous,current_market=current))
    def query(self, portfolio, question): return self.query_engine.answer(question,portfolio,self)

    def contributors(self, portfolio: Portfolio) -> list[Contributor]:
        vals = [(p, self.pricing.value(p)) for p in portfolio.positions]
        amounts = []
        for p, v in vals:
            proxy = abs(v.delta) + abs(v.fx_delta) + abs(v.vega) + abs(v.dv01) * 10.0 + 0.1 * abs(v.gamma)
            label = getattr(p, "symbol", getattr(p, "pair", getattr(p, "issuer", getattr(p, "currency", p.id))))
            amounts.append((p.id, str(label), proxy))
        total = sum(x[2] for x in amounts) or 1.0
        return sorted(
            [Contributor(position_id=i, label=label, risk_amount=a, contribution_pct=a / total * 100.0) for i, label, a in amounts],
            key=lambda x: x.risk_amount,
            reverse=True,
        )

    def limits(self, portfolio: Portfolio):
        risk = self.risk.calculate(portfolio, self.pricing)
        return self.limit_engine.evaluate(portfolio, self.pricing, risk, DEFAULT_LIMITS)
