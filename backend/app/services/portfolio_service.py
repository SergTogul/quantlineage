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
from app.market.snapshot import MarketDataProvider
from app.risk.attribution import AttributionEngine
from app.risk.es import ESContributionAnalytics
from app.risk.factors import RiskFactorEngine
from app.risk.hierarchy import HierarchyEngine
from app.risk.historical import HistoricalRiskEngine, approximate_pnl_series
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
from app.risk.trade_artifacts import TradeCalculationArtifact
from app.risk.var import VaRAnalytics
from app.sample import DemoPortfolioMarketDataProvider


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
    def __init__(
        self,
        pricing: PricingEngine,
        risk: RiskEngine,
        *,
        market_data: MarketDataProvider | None = None,
    ):
        self.pricing = pricing
        self.risk = risk
        self.market_data = market_data or DemoPortfolioMarketDataProvider()
        self.stress_engine = StressEngine()
        self.reverse_stress_engine = ReverseStressEngine()
        self.multi_reverse_stress_engine = MultiFactorReverseStressEngine()
        self.limit_engine = LimitEngine()
        # Share historical factor source with HistoricalRiskEngine when injected (M10.2).
        # isinstance must be a statement so mypy narrows risk before .seed/.observations.
        hist_kwargs: dict = {}
        if isinstance(risk, HistoricalRiskEngine):
            hist_kwargs = {
                "seed": risk.seed,
                "observations": risk.observations,
                "dataset": risk.dataset,
            }
        self.var_engine = VaRAnalytics(**hist_kwargs) if hist_kwargs else VaRAnalytics()
        self.limit_drilldown_engine = LimitDrilldownEngine(
            risk, limit_engine=self.limit_engine, var_engine=self.var_engine
        )
        self.factor_engine = RiskFactorEngine(self.market_data)
        hist_risk = (
            risk
            if isinstance(risk, HistoricalRiskEngine)
            else HistoricalRiskEngine(**hist_kwargs)
            if hist_kwargs
            else HistoricalRiskEngine()
        )
        self.scenario_comparison_engine = ScenarioComparisonEngine(
            risk_engine=hist_risk,
            factor_engine=self.factor_engine,
        )
        self.es_engine = (
            ESContributionAnalytics(**hist_kwargs) if hist_kwargs else ESContributionAnalytics()
        )
        self.hierarchy_engine = HierarchyEngine(risk)
        self.attribution_engine = AttributionEngine(self.market_data)
        self.risk_change_engine = RiskChangeAttributionEngine(
            risk_engine=hist_risk,
            market_data=self.market_data,
        )
        self.query_engine = RiskQueryEngine()

    def market_snapshot(self, portfolio: Portfolio): return self.market_data.snapshot(portfolio)

    def summary(
        self,
        portfolio: Portfolio,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    ) -> RiskSummary:
        market = self.market_snapshot(portfolio)
        if isinstance(self.risk, HistoricalRiskEngine):
            r = self.risk.calculate(
                portfolio,
                self.pricing,
                methodology=methodology,
                market=market,
            )
        else:
            r = self.risk.calculate(portfolio, self.pricing)
            r = {**r, "methodology": methodology.value}
        return RiskSummary(portfolio_id=portfolio.id, **r)

    def stresses(self, portfolio: Portfolio, scenarios: list[StressScenario] | None = None) -> list[StressResult]:
        market = self.market_snapshot(portfolio)
        return self.stress_engine.run(
            portfolio, self.pricing, scenarios or DEFAULT_SCENARIOS, market=market
        )

    def threat_evaluation(self, portfolio: Portfolio, scenarios: list[StressScenario] | None = None) -> ScenarioEvaluationReport:
        market = self.market_snapshot(portfolio)
        return self.stress_engine.evaluate(
            portfolio, self.pricing, scenarios or THREAT_SCENARIOS, market=market
        )

    def reverse_stress(self, portfolio, target_loss_pct, factor, max_shock=.80):
        market = self.market_snapshot(portfolio)
        return self.reverse_stress_engine.solve(
            portfolio, self.pricing, target_loss_pct, factor, max_shock, market=market
        )

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
        market = self.market_snapshot(portfolio)
        return self.multi_reverse_stress_engine.solve(
            portfolio,
            self.pricing,
            target_loss_pct,
            factors=factors,
            weights=weights,
            max_shock=max_shock,
            max_shocks=max_shocks,
            market=market,
        )

    def compare_scenarios(self, base, hedged, scenarios, methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA):
        """Hedge comparison with VaR/ES/cost/exposures (M3.7)."""
        # Snapshot the base book once and reuse for the hedged book. Identity
        # differences must not infer a second market from either book's trades.
        market = self.market_snapshot(base)
        return self.scenario_comparison_engine.compare(
            base, hedged, self.pricing, scenarios, methodology=methodology, market=market
        )

    def factors(self, portfolio): return self.factor_engine.calculate(portfolio,self.pricing)

    def var_report(
        self,
        portfolio: Portfolio,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    ):
        market = self.market_snapshot(portfolio)
        return self.var_engine.report(
            portfolio,
            self.pricing,
            methodology=methodology,
            market=market,
        )

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
        market = self.market_snapshot(portfolio)
        return engine.report(
            portfolio,
            self.pricing,
            confidence=confidence,
            methodology=methodology,
            market=market,
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
            market=self.market_snapshot(portfolio),
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
        market = self.market_snapshot(request.portfolio)
        return what_if_analysis(
            request.portfolio,
            self.pricing,
            changes=request.changes,
            risk_engine=self.risk if isinstance(self.risk, HistoricalRiskEngine) else None,
            methodology=meth,
            factor_engine=self.factor_engine,
            stress_engine=self.stress_engine,
            scenarios=request.scenarios,
            market=market,
        )

    def _historical_pnl_for_valuation(self, valuation):
        """One historical P&L series from already-valued Greeks (no reprice).

        Uses the injected ``HistoricalRiskEngine`` dataset + methodology and
        ``approximate_pnl_series`` (LINEAR / DELTA_GAMMA). One series per
        trade, shared factor observations so lengths match. Not a book-level
        series split.

        FULL_REVALUATION and an opt-in ``factor_panel`` are omitted (``None``):
        those paths would call ``value`` again. Default engine is DELTA_GAMMA
        with no panel.
        """
        if not isinstance(self.risk, HistoricalRiskEngine):
            return None
        if self.risk.methodology is VaRMethodology.FULL_REVALUATION:
            return None
        if self.risk.factor_panel is not None:
            return None
        observations = self.risk.dataset.factor_observations()
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
            methodology=self.risk.methodology,
            scenario_kernel=self.risk.scenario_kernel,
            scenario_backend=self.risk.scenario_backend,
        )
        if series.size == 0:
            return None
        return tuple(float(point) for point in series)

    def hierarchy(self, portfolio):
        """Build the firm tree from one valuation per trade (R0.7.3 leftover).

        PV and additive Greeks come from ``self.pricing.value`` once per
        position. Historical P&L is attached once per trade from those
        Greeks via ``approximate_pnl_series`` (same dataset as ``self.risk``).
        ``HierarchyEngine`` sums the vectors and computes node VaR / ES.
        Stress P&L is left empty: ``self.stresses`` would snapshot again and
        ``StressEngine.run`` would re-call ``value`` plus ``shocked_value``
        per scenario (once-per-trade, not once-per-node, but not value-once).
        """
        market = self.market_snapshot(portfolio)
        artifacts = {}
        for position in portfolio.positions:
            valuation = self.pricing.value(position, market)
            artifacts[position.id] = TradeCalculationArtifact.from_valuation(
                valuation,
                trade_id=position.id,
                historical_pnl=self._historical_pnl_for_valuation(valuation),
            )
        return self.hierarchy_engine.build(
            portfolio, self.pricing, market=market, artifacts=artifacts
        )
    def attribution(self, request): return self.attribution_engine.explain(request,self.pricing)
    def risk_change_attribution(
        self, request: RiskChangeAttributionRequest
    ) -> RiskChangeAttributionReport:
        return self.risk_change_engine.explain(request, self.pricing)
    def demo_attribution(self, portfolio):
        from app.domain.models import AttributionRequest
        current=self.market_snapshot(portfolio)
        previous=current.model_copy(update={
            "id":"illustrative_previous",
            "as_of":"t0",
            "equity_spots":{k:v*.99 for k,v in current.equity_spots.items()},
            "equity_vols":{k:v*.95 for k,v in current.equity_vols.items()},
            "fx_spots":{k:v*.995 for k,v in current.fx_spots.items()},
            "fx_vols":{k:v*.95 for k,v in current.fx_vols.items()},
            "rates":{k:v-.001 for k,v in current.rates.items()},
            "key_rates":{
                ccy:{tenor:val-0.001 for tenor,val in pillars.items()}
                for ccy,pillars in current.key_rates.items()
            },
            "projection_rates":{k:v-.001 for k,v in current.projection_rates.items()},
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

    def dashboard(
        self,
        portfolio: Portfolio,
        *,
        scenarios: list[StressScenario] | None = None,
        threat_scenarios: list[StressScenario] | None = None,
    ) -> dict:
        """One sequential pass of existing dashboard methods (R0.10.2).

        Does not share a market snapshot across methods (market-required
        semantics on each method stay unchanged). The HTTP batch is one
        request; each method still snapshots as it does today.
        """
        return {
            "portfolio": portfolio,
            "summary": self.summary(portfolio),
            "stress": self.stresses(portfolio, scenarios),
            "threats": self.threat_evaluation(portfolio, threat_scenarios),
            "contributors": self.contributors(portfolio),
            "limits": self.limits(portfolio),
            "factors": self.factors(portfolio),
            "varReport": self.var_report(portfolio),
            "hierarchy": self.hierarchy(portfolio),
            "attribution": self.demo_attribution(portfolio),
        }

    def contributors(self, portfolio: Portfolio) -> list[Contributor]:
        """Rank positions by parametric component VaR with distinct trade labels."""
        report = self.var_engine.report(
            portfolio,
            self.pricing,
            market=self.market_snapshot(portfolio),
        )
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
        market = self.market_snapshot(portfolio)
        if isinstance(self.risk, HistoricalRiskEngine):
            risk = self.risk.calculate(portfolio, self.pricing, market=market)
        else:
            risk = self.risk.calculate(portfolio, self.pricing)
        stress = self.stress_engine.run(
            portfolio, self.pricing, DEFAULT_SCENARIOS, market=market
        )
        enriched = {
            **risk,
            "stress_loss": max(0.0, max((-float(s.pnl) for s in stress), default=0.0)),
        }
        return self.limit_engine.evaluate(
            portfolio,
            self.pricing,
            enriched,
            DEFAULT_LIMITS,
            market=market,
        )

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
        market = self.market_snapshot(portfolio)
        return self.limit_drilldown_engine.report(
            portfolio,
            self.pricing,
            hierarchy=hierarchy,
            metric=metric,
            limits=limits,
            top_n=top_n,
            breaches_only=breaches_only,
            label_fn=position_label,
            market=market,
        )
