from __future__ import annotations

import pytest

from app.domain.models import BondPosition, Portfolio, SwapPosition
from app.market.demo_snapshot import (
    ConflictingSampleMarkError,
    DemoSampleMarksSnapshotAdapter,
)
from app.market.snapshot import PositionMarketDataProvider
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.sample import RATES_MACRO_PORTFOLIO, SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService


def _usd_rate_book(*, reverse: bool = False, shared_rate: float | None = None) -> Portfolio:
    bond_rate = 0.041
    swap_rate = shared_rate if shared_rate is not None else 0.043
    positions = [
        BondPosition(
            type="bond",
            id="bond-usd",
            issuer="UST",
            face_value=1_000_000,
            maturity_years=2.0,
            yield_rate=bond_rate,
            duration=1.9,
        ),
        SwapPosition(
            type="swap",
            id="swap-usd",
            notional=1_000_000,
            maturity_years=2.0,
            fixed_rate=0.04,
            market_swap_rate=swap_rate,
            duration=1.9,
        ),
    ]
    if reverse:
        positions.reverse()
    return Portfolio(id="rates", name="rates", positions=positions)


@pytest.mark.parametrize("reverse", [False, True])
def test_unequal_duplicate_usd_marks_raise_in_both_orders(reverse: bool) -> None:
    with pytest.raises(ConflictingSampleMarkError) as exc_info:
        DemoSampleMarksSnapshotAdapter().snapshot(_usd_rate_book(reverse=reverse))

    message = str(exc_info.value)
    assert "USD" in message
    assert "bond-usd" in message
    assert "0.041" in message
    assert "swap-usd" in message
    assert "0.043" in message


def test_equal_duplicate_usd_marks_seed_one_rate() -> None:
    snapshot = DemoSampleMarksSnapshotAdapter().snapshot(
        _usd_rate_book(shared_rate=0.041)
    )

    assert dict(snapshot.rates) == {"USD": 0.041}


def test_deprecated_position_provider_inherits_conflict_behavior() -> None:
    with pytest.raises(ConflictingSampleMarkError):
        PositionMarketDataProvider().snapshot(_usd_rate_book())


def test_mixed_usd_demo_uses_explicit_snapshot_successfully() -> None:
    snapshot = demo_market_snapshot(RATES_MACRO_PORTFOLIO)

    assert snapshot.id == "demo:rates-macro"
    assert snapshot.key_rates["USD"]
    assert snapshot.projection_rates["USD"] == pytest.approx(0.0425)
    valuations = BuiltinPricingEngine().value_portfolio(
        RATES_MACRO_PORTFOLIO, snapshot
    )
    assert len(valuations) == len(RATES_MACRO_PORTFOLIO.positions)

    with pytest.raises(ConflictingSampleMarkError):
        DemoSampleMarksSnapshotAdapter().snapshot(RATES_MACRO_PORTFOLIO)


def _sample_desk_subset() -> Portfolio:
    """Hierarchy desk node: same trades as SAMPLE, different id so canned bind misses."""
    return Portfolio(
        id="desk:Global Macro",
        name="Global Macro",
        positions=list(SAMPLE_PORTFOLIO.positions),
        firm=SAMPLE_PORTFOLIO.firm,
        desk="Global Macro",
        strategy=SAMPLE_PORTFOLIO.strategy,
    )


def test_sample_desk_subset_still_raises_conflicting_usd_marks() -> None:
    """Adapter stay fail-closed; the fix is threading the root snapshot, not this."""
    with pytest.raises(ConflictingSampleMarkError) as exc_info:
        DemoSampleMarksSnapshotAdapter().snapshot(_sample_desk_subset())

    message = str(exc_info.value)
    assert "rates[USD]" in message
    assert "0.041" in message
    assert "0.04" in message


def test_hierarchy_and_stress_do_not_rebuild_market_from_sample_desk_subset(
    monkeypatch,
) -> None:
    """Acc 5 lock: service paths must not call the adapter on a SAMPLE desk subset."""
    seen: list[str] = []
    original = DemoSampleMarksSnapshotAdapter.snapshot

    def tracking(self, portfolio: Portfolio):
        seen.append(portfolio.id)
        return original(self, portfolio)

    monkeypatch.setattr(DemoSampleMarksSnapshotAdapter, "snapshot", tracking)

    service = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
    )
    assert service.stresses(SAMPLE_PORTFOLIO)
    assert service.threat_evaluation(SAMPLE_PORTFOLIO).evaluations
    assert service.limits(SAMPLE_PORTFOLIO)
    root = service.hierarchy(SAMPLE_PORTFOLIO)
    assert root.level == "firm"
    assert service.demo_attribution(SAMPLE_PORTFOLIO).total_change != 0.0
    assert seen == []


def test_portfolio_service_threads_one_resolved_snapshot_to_dashboard_paths() -> None:
    snapshot = demo_market_snapshot(SAMPLE_PORTFOLIO)
    pricing = BuiltinPricingEngine()
    service = PortfolioService(
        pricing,
        HistoricalRiskEngine(seed=1, observations=20),
    )
    calls: list[str] = []

    class _Provider:
        def snapshot(self, portfolio: Portfolio):
            calls.append(portfolio.id)
            return snapshot

    service.market_data = _Provider()

    service.stresses(SAMPLE_PORTFOLIO, [])
    assert calls == [SAMPLE_PORTFOLIO.id]

    service.threat_evaluation(SAMPLE_PORTFOLIO, [])
    assert calls == [SAMPLE_PORTFOLIO.id, SAMPLE_PORTFOLIO.id]

    service.limits(SAMPLE_PORTFOLIO)
    assert calls[-1] == SAMPLE_PORTFOLIO.id
    after_limits = len(calls)
    assert after_limits >= 3

    service.hierarchy(SAMPLE_PORTFOLIO)
    assert len(calls) == after_limits + 1
    assert calls[-1] == SAMPLE_PORTFOLIO.id

    service.demo_attribution(SAMPLE_PORTFOLIO)
    assert len(calls) == after_limits + 2
    assert calls[-1] == SAMPLE_PORTFOLIO.id
    assert all(portfolio_id == SAMPLE_PORTFOLIO.id for portfolio_id in calls)


def _flat_spy_hedge(*, portfolio_id: str | None = None) -> Portfolio:
    hedge = SAMPLE_PORTFOLIO.model_copy(deep=True)
    if portfolio_id is not None:
        hedge.id = portfolio_id
    for position in hedge.positions:
        if getattr(position, "symbol", None) == "SPY" and position.type == "equity":
            position.quantity = 0.0
            break
    return hedge


def test_compare_stress_and_var_legs_use_same_base_snapshot(monkeypatch) -> None:
    """Hedge-compare stress and VaR legs share the base book's snapshot object."""
    from app.domain.models import StressScenario
    from app.risk.stress import StressEngine

    stress_markets: list = []
    var_markets: list = []
    orig_run = StressEngine.run
    orig_calc = HistoricalRiskEngine.calculate

    def tracking_run(self, portfolio, pricing, scenarios, market=None):
        stress_markets.append(market)
        return orig_run(self, portfolio, pricing, scenarios, market=market)

    def tracking_calc(self, portfolio, pricing_engine, methodology=None, market=None):
        var_markets.append(market)
        return orig_calc(
            self, portfolio, pricing_engine, methodology=methodology, market=market
        )

    monkeypatch.setattr(StressEngine, "run", tracking_run)
    monkeypatch.setattr(HistoricalRiskEngine, "calculate", tracking_calc)

    service = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
    )
    hedge = _flat_spy_hedge(portfolio_id="hedged-global-macro")
    service.compare_scenarios(
        SAMPLE_PORTFOLIO,
        hedge,
        [StressScenario(name="Crash", equity_shock=-0.2)],
    )

    assert stress_markets and var_markets
    shared = stress_markets[0]
    assert shared is not None
    assert all(market is shared for market in stress_markets)
    assert all(market is shared for market in var_markets)
    assert shared.id == demo_market_snapshot(SAMPLE_PORTFOLIO).id


def test_compare_does_not_call_adapter_on_sample(monkeypatch) -> None:
    """Acc 5: SAMPLE hedge-compare must not infer a market from either book's trades."""
    from app.domain.models import StressScenario

    seen: list[str] = []
    original = DemoSampleMarksSnapshotAdapter.snapshot

    def tracking(self, portfolio: Portfolio):
        seen.append(portfolio.id)
        return original(self, portfolio)

    monkeypatch.setattr(DemoSampleMarksSnapshotAdapter, "snapshot", tracking)

    service = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
    )
    hedge = _flat_spy_hedge(portfolio_id="hedged-global-macro")
    service.compare_scenarios(
        SAMPLE_PORTFOLIO,
        hedge,
        [StressScenario(name="Crash", equity_shock=-0.2)],
    )
    assert seen == []


def test_reverse_stress_uses_root_market_snapshot_not_aggregate() -> None:
    """Service reverse-stress resolves market_data.snapshot(root), not DemoAggregate."""
    snapshot = demo_market_snapshot(SAMPLE_PORTFOLIO)
    service = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
    )
    calls: list[str] = []
    aggregate_calls: list[str] = []

    class _Provider:
        def snapshot(self, portfolio: Portfolio):
            calls.append(portfolio.id)
            return snapshot

    service.market_data = _Provider()
    orig_agg = service.reverse_stress_engine.market_data.snapshot

    def tracking_agg(portfolio: Portfolio):
        aggregate_calls.append(portfolio.id)
        return orig_agg(portfolio)

    service.reverse_stress_engine.market_data.snapshot = tracking_agg

    result = service.reverse_stress(SAMPLE_PORTFOLIO, 0.01, "equity", 0.8)
    assert calls == [SAMPLE_PORTFOLIO.id]
    assert aggregate_calls == []
    assert result.base_market_value != 0.0


def test_reverse_stress_multi_uses_root_market_snapshot_not_aggregate() -> None:
    """Service reverse-multi resolves market_data.snapshot(root), not DemoAggregate."""
    snapshot = demo_market_snapshot(SAMPLE_PORTFOLIO)
    service = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
    )
    calls: list[str] = []
    aggregate_calls: list[str] = []

    class _Provider:
        def snapshot(self, portfolio: Portfolio):
            calls.append(portfolio.id)
            return snapshot

    service.market_data = _Provider()
    orig_agg = service.multi_reverse_stress_engine.market_data.snapshot

    def tracking_agg(portfolio: Portfolio):
        aggregate_calls.append(portfolio.id)
        return orig_agg(portfolio)

    service.multi_reverse_stress_engine.market_data.snapshot = tracking_agg

    result = service.reverse_stress_multi(
        SAMPLE_PORTFOLIO, 0.01, factors=["equity", "vol"]
    )
    assert calls == [SAMPLE_PORTFOLIO.id]
    assert aggregate_calls == []
    assert result.base_market_value != 0.0


def test_limit_drilldown_does_not_rebuild_market_from_sample_desk_subset(
    monkeypatch,
) -> None:
    """Acc 5: desk-scoped drilldown uses the root snapshot, not the adapter."""
    from app.domain.models import HierarchyLevel, HierarchyRef

    seen: list[str] = []
    original = DemoSampleMarksSnapshotAdapter.snapshot

    def tracking(self, portfolio: Portfolio):
        seen.append(portfolio.id)
        return original(self, portfolio)

    monkeypatch.setattr(DemoSampleMarksSnapshotAdapter, "snapshot", tracking)

    service = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=20),
    )
    ref = HierarchyRef(
        level=HierarchyLevel.DESK,
        firm=SAMPLE_PORTFOLIO.firm,
        portfolio_id=SAMPLE_PORTFOLIO.id,
        desk=SAMPLE_PORTFOLIO.desk,
    )
    report = service.limit_drilldown(
        portfolio=SAMPLE_PORTFOLIO,
        hierarchy=ref,
        breaches_only=False,
    )
    assert report.hierarchy_level == "desk"
    assert seen == []
