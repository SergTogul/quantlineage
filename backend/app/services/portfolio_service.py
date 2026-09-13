from types import MappingProxyType

from app.domain.models import (
    Contributor,
    ESContributionReport,
    HierarchyRef,
    LimitDrilldownReport,
    LimitMetric,
    Portfolio,
    Position,
    RiskChangeAttributionReport,
    RiskChangeAttributionRequest,
    RiskChangeReport,
    RiskLimit,
    RiskSummary,
    ScenarioEvaluationReport,
    StressResult,
    VaRMethodology,
    VaRMethodologyComparison,
    WhatIfReport,
    WhatIfRequest,
)
from app.interfaces.pricing import PricingEngine
from app.interfaces.risk import RiskEngine
from app.market.snapshot import FixedMarketDataProvider, MarketDataProvider
from app.pricing.instrument_capabilities import get_capability
from app.risk.attribution import AttributionEngine
from app.risk.es import ESContributionAnalytics
from app.risk.factors import RiskFactorEngine
from app.risk.hierarchy import HierarchyEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_analytics import (
    HistoricalAnalyticsRequest,
    HistoricalAnalyticsResult,
    compute_historical_analytics,
)
from app.risk.limit_drilldown import LimitDrilldownEngine
from app.risk.limits import DEFAULT_LIMITS, LimitEngine
from app.risk.query import RiskQueryEngine
from app.risk.risk_attribution import RiskChangeAttributionEngine
from app.risk.scenario_attribution import ScenarioLike
from app.risk.stress import (
    DEFAULT_SCENARIOS,
    THREAT_SCENARIOS,
    MultiFactorReverseStressEngine,
    ReverseStressEngine,
    ScenarioComparisonEngine,
    StressEngine,
)
from app.risk.var import VaRAnalytics
from app.sample import DemoPortfolioMarketDataProvider


def _label_equity(position: Position) -> str:
    return f"{position.symbol} equity"


def _label_equity_future(position: Position) -> str:
    return f"{position.symbol} future"


def _label_european_option(position: Position) -> str:
    return f"{position.symbol} {position.option_type}"


def _label_bond(position: Position) -> str:
    return position.issuer


def _label_swap(position: Position) -> str:
    tenor = (
        f"{int(position.maturity_years)}Y"
        if position.maturity_years == int(position.maturity_years)
        else f"{position.maturity_years}Y"
    )
    return f"{position.currency} {tenor} swap"


def _label_fx_forward(position: Position) -> str:
    return f"{position.pair} fwd"


def _label_fx_option(position: Position) -> str:
    return f"{position.pair} {position.option_type}"


def _label_ir_future(position: Position) -> str:
    return f"{position.currency} IR future"


def _label_by_id(position: Position) -> str:
    return position.id


_LABEL_HANDLERS = MappingProxyType(
    {
        "equity": _label_equity,
        "equity_future": _label_equity_future,
        "european_option": _label_european_option,
        "bond": _label_bond,
        "swap": _label_swap,
        "fx_forward": _label_fx_forward,
        "fx_option": _label_fx_option,
        "ir_future": _label_ir_future,
        "cap_floor": _label_by_id,
        "swaption": _label_by_id,
    }
)


def position_label(position: Position) -> str:
    """Human-readable trade label that distinguishes instrument type."""
    family = getattr(position, "type", None)
    get_capability(family)
    if not isinstance(family, str):
        raise TypeError(f"unknown instrument family: {family!r}")
    try:
        handler = _LABEL_HANDLERS[family]
    except KeyError:
        raise TypeError(f"unknown instrument family: {family!r}") from None
    return handler(position)


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
                "factor_panel": risk.factor_panel,
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
        self.risk_run_compare = None

    def market_snapshot(self, portfolio: Portfolio): return self.market_data.snapshot(portfolio)

    def summary(
        self,
        portfolio: Portfolio,
        methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    ) -> RiskSummary:
        market = self.market_snapshot(portfolio)
        if isinstance(self.risk, HistoricalRiskEngine):
            return self.risk.calculate(
                portfolio,
                self.pricing,
                methodology=methodology,
                market=market,
            )
        result = self.risk.calculate(portfolio, self.pricing)
        if result.methodology == methodology:
            return result
        return result.model_copy(update={"methodology": methodology})

    def historical_analytics(self, request: HistoricalAnalyticsRequest) -> HistoricalAnalyticsResult:
        """Wealth / drawdown / Sharpe / VaR-ES from frozen dataset + snapshot identity."""
        from app.risk.factor_panel import factor_panel_from_dataset
        from app.risk.historical_data import create_historical_dataset
        from app.services.risk_factories import dataset_identity, resolve_dataset_source

        if not isinstance(self.risk, HistoricalRiskEngine):
            raise ValueError("historical analytics requires HistoricalRiskEngine")
        engine = self.risk
        bound_id, bound_version = dataset_identity(engine.dataset)
        requested_id = request.historical_dataset_id
        if requested_id is None or requested_id == bound_id:
            dataset_id, dataset_version = bound_id, bound_version
            panel = engine.factor_panel
            if panel is None:
                panel = factor_panel_from_dataset(
                    engine.dataset,
                    observations=engine.observations,
                    seed=engine.seed,
                )
        else:
            source = resolve_dataset_source(requested_id)
            dataset = create_historical_dataset(
                source, seed=engine.seed, observations=engine.observations
            )
            dataset_id, dataset_version = dataset_identity(dataset)
            panel = factor_panel_from_dataset(
                dataset, observations=engine.observations, seed=engine.seed
            )
        if (
            request.historical_dataset_version is not None
            and request.historical_dataset_version != dataset_version
        ):
            raise ValueError("historical_dataset_version does not match resolved dataset")
        market = self.market_snapshot(request.portfolio)
        if (
            request.market_snapshot_id is not None
            and request.market_snapshot_id != market.id
        ):
            raise ValueError("market_snapshot_id does not match bound snapshot")
        return compute_historical_analytics(
            portfolio=request.portfolio,
            pricing_engine=self.pricing,
            market=market,
            panel=panel,
            start=request.start,
            end=request.end,
            frequency=request.frequency,
            methodology=request.methodology,
            annualization=request.annualization,
            historical_dataset_id=dataset_id,
            historical_dataset_version=dataset_version,
            rolling_window=request.rolling_window,
            risk_free_rate=request.risk_free_rate,
            missing_date_policy=request.missing_date_policy,
            period_window=request.period_window,
            include_benchmark=request.include_benchmark,
        )

    def stresses(self, portfolio: Portfolio, scenarios: list[ScenarioLike] | None = None) -> list[StressResult]:
        market = self.market_snapshot(portfolio)
        return self.stress_engine.run(
            portfolio, self.pricing, scenarios or DEFAULT_SCENARIOS, market=market
        )

    def threat_evaluation(self, portfolio: Portfolio, scenarios: list[ScenarioLike] | None = None) -> ScenarioEvaluationReport:
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
                factor_panel=self.risk.factor_panel,
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
            from app.services.risk_factories import resize_historical_risk_engine

            if observations is None:
                engine = self.risk
            else:
                engine = resize_historical_risk_engine(self.risk, observations)
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

    def hierarchy(self, portfolio):
        """Build the firm tree from one trade-artifact producer pass (R0.7.6).

        Delegates to ``HierarchyEngine.build`` without a pre-built map so the
        engine default path values each position once, attaches historical
        P&L, fills default-scenario stress (scenario-once / price-many), and
        aggregates. Limits are evaluated from the artifact RiskSummary.
        """
        market = self.market_snapshot(portfolio)
        return self.hierarchy_engine.build(
            portfolio, self.pricing, market=market
        )
    def attribution(self, request): return self.attribution_engine.explain(request,self.pricing)
    def risk_change_attribution(
        self, request: RiskChangeAttributionRequest
    ) -> RiskChangeAttributionReport:
        return self.risk_change_engine.explain(request, self.pricing)

    def explain_risk_change(
        self,
        t0_run_id: str,
        t1_run_id: str,
        metric: str = "var_99",
    ) -> RiskChangeReport:
        compare = self.risk_run_compare
        if compare is None:
            raise ValueError("risk-run compare is not configured")
        return compare(t0_run_id, t1_run_id, metric=metric)
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
        scenarios: list[ScenarioLike] | None = None,
        threat_scenarios: list[ScenarioLike] | None = None,
    ) -> dict:
        """One sequential pass of existing dashboard methods (R0.10.2).

        Resolves a single market snapshot and runs every slice on a temporary
        service bound to that snapshot. Does not mutate ``self.market_data``.
        """
        market = self.market_snapshot(portfolio)
        bound = PortfolioService(
            self.pricing,
            self.risk,
            market_data=FixedMarketDataProvider(market),
        )
        return {
            "portfolio": portfolio,
            "summary": bound.summary(portfolio),
            "stress": bound.stresses(portfolio, scenarios),
            "threats": bound.threat_evaluation(portfolio, threat_scenarios),
            "contributors": bound.contributors(portfolio),
            "limits": bound.limits(portfolio),
            "factors": bound.factors(portfolio),
            "varReport": bound.var_report(portfolio),
            "hierarchy": bound.hierarchy(portfolio),
            "attribution": bound.demo_attribution(portfolio),
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
        extra = {
            "stress_loss": max(0.0, max((-float(s.pnl) for s in stress), default=0.0)),
        }
        return self.limit_engine.evaluate(
            portfolio,
            self.pricing,
            risk,
            DEFAULT_LIMITS,
            market=market,
            extra=extra,
        )

    def limit_drilldown(
        self,
        *,
        portfolio: Portfolio | None = None,
        metric: LimitMetric | None = None,
        hierarchy: HierarchyRef | None = None,
        limits: list[RiskLimit] | None = None,
        top_n: int = 5,
        breaches_only: bool = True,
    ) -> LimitDrilldownReport:
        """Hierarchy-scoped limit drill-down with top contributors (M4.6)."""
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
