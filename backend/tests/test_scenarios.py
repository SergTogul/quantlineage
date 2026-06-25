"""M2.2 historical scenario generation tests.

Pipeline: FactorObservationSeries → AggregateFactorChange → Scenario → shocked MarketSnapshot.

Conventions / tolerances:
- equity / FX: relative; vol: relative vol-level; rates: bp in observations, decimal in bump
- Exact equality for discrete marks; abs 1e-12 for derived decimal rate shifts
- Empty scenario → content_hash unchanged (zero P&L precondition for M2.3)
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.domain.models import MarketSnapshot
from app.market.snapshot import shock_snapshot
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_panel import HistoricalFactorPanel
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero
from app.risk.historical_data import (
    ArrayHistoricalDataset,
    FactorObservationSeries,
    SyntheticHistoricalDataset,
)
from app.risk.scenario_engine import apply_scenario
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    ScenarioCategory,
    scenario_to_market_scenario,
)
from app.risk.scenarios import (
    AggregateFactorChange,
    apply_market_scenario,
    expand_aggregate_change,
    historical_market_scenarios,
    historical_market_scenarios_from_panel,
    historical_shocked_snapshots,
    iter_aggregate_changes,
    market_scenario_from_change,
    shocked_snapshots,
    to_stress_scenario,
)
from app.risk.var import VaRAnalytics
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot


def _base_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        id="base",
        equity_spots={"SPY": 100.0, "NVDA": 200.0},
        equity_vols={"SPY": 0.20},
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.12},
        rates={"USD": 0.04, "EUR": 0.03},
    )


def _series() -> FactorObservationSeries:
    return FactorObservationSeries(
        equity_returns=np.array([0.0, -0.10, 0.05]),
        vol_moves=np.array([0.0, 0.25, 0.0]),
        rate_moves_bps=np.array([0.0, 50.0, -25.0]),
        fx_returns=np.array([0.0, -0.05, 0.01]),
    )


def test_iter_aggregate_changes_preserves_row_values():
    changes = iter_aggregate_changes(_series())
    assert len(changes) == 3
    assert changes[0] == AggregateFactorChange(0, 0.0, 0.0, 0.0, 0.0)
    assert changes[1].equity_return == pytest.approx(-0.10)
    assert changes[1].rate_move_bps == pytest.approx(50.0)
    assert changes[2].index == 2


def test_expand_zero_observation_yields_no_shocks():
    base = _base_snapshot()
    shocks = expand_aggregate_change(AggregateFactorChange(0, 0.0, 0.0, 0.0, 0.0), base)
    assert shocks == ()


def test_expand_broadcasts_aggregate_moves_to_typed_factors():
    base = _base_snapshot()
    shocks = expand_aggregate_change(
        AggregateFactorChange(1, equity_return=-0.10, vol_move=0.25, rate_move_bps=50.0, fx_return=-0.05),
        base,
    )
    factors = [(type(s.factor).__name__, s.amount) for s in shocks]
    assert factors.count(("EquitySpot", -0.10)) == 2
    assert ("EquityVol", 0.25) in factors
    assert ("FXSpot", -0.05) in factors
    assert ("FXVol", 0.25) in factors
    assert factors.count(("RateZero", 0.005)) == 2  # 50bp → 0.005 decimal


def test_empty_scenario_leaves_content_hash_unchanged():
    base = _base_snapshot()
    scenario = market_scenario_from_change(AggregateFactorChange(0, 0.0, 0.0, 0.0, 0.0), base)
    assert scenario.shocks == ()
    shocked = apply_market_scenario(base, scenario)
    assert shocked.content_hash() == base.content_hash()
    assert shocked.id == "base:hist_0"


def test_apply_market_scenario_matches_manual_apply():
    base = _base_snapshot()
    scenario = market_scenario_from_change(
        AggregateFactorChange(1, -0.10, 0.25, 50.0, -0.05),
        base,
    )
    shocked = apply_market_scenario(base, scenario)
    via_apply = base.apply(
        [
            (EquitySpot("SPY"), -0.10),
            (EquitySpot("NVDA"), -0.10),
            (EquityVol(underlying="SPY"), 0.25),
            (FXSpot("EURUSD"), -0.05),
            (FXVol(pair="EURUSD"), 0.25),
            (RateZero(currency="USD", tenor="ALL"), 0.005),
            (RateZero(currency="EUR", tenor="ALL"), 0.005),
        ]
    )
    assert shocked.equity_spots == via_apply.equity_spots
    assert shocked.equity_vols == via_apply.equity_vols
    assert shocked.fx_spots == via_apply.fx_spots
    assert shocked.fx_vols == via_apply.fx_vols
    assert shocked.rates == via_apply.rates
    assert shocked.equity_spots["SPY"] == pytest.approx(90.0)
    assert shocked.equity_vols["SPY"] == pytest.approx(0.25)
    assert shocked.rates["USD"] == pytest.approx(0.045)
    assert shocked.fx_spots["EURUSD"] == pytest.approx(1.10 * 0.95)


def test_to_stress_scenario_matches_shock_snapshot():
    base = _base_snapshot()
    scenario = market_scenario_from_change(
        AggregateFactorChange(1, -0.10, 0.25, 50.0, -0.05),
        base,
    )
    via_typed = apply_market_scenario(base, scenario)
    via_legacy = shock_snapshot(base, to_stress_scenario(scenario))
    assert via_typed.equity_spots == via_legacy.equity_spots
    assert via_typed.equity_vols == via_legacy.equity_vols
    assert via_typed.fx_spots == via_legacy.fx_spots
    assert via_typed.fx_vols == via_legacy.fx_vols
    assert via_typed.rates == via_legacy.rates


def test_historical_scenarios_count_and_kind():
    base = _base_snapshot()
    scenarios = historical_market_scenarios(base, _series())
    assert len(scenarios) == 3
    assert all(s.category == ScenarioCategory.HISTORICAL_REPLAY for s in scenarios)
    assert [s.metadata["observation_index"] for s in scenarios] == [0, 1, 2]


def test_shocked_snapshots_are_independent_not_cumulative():
    base = _base_snapshot()
    scenarios = historical_market_scenarios(base, _series())
    snaps = shocked_snapshots(base, scenarios)
    assert len(snaps) == 3
    # First observation is zero → same marks as base
    assert snaps[0].content_hash() == base.content_hash()
    # Second and third must not compound on each other
    assert snaps[1].equity_spots["SPY"] == pytest.approx(90.0)
    assert snaps[2].equity_spots["SPY"] == pytest.approx(105.0)
    assert base.equity_spots["SPY"] == 100.0


def test_historical_shocked_snapshots_from_dataset():
    base = _base_snapshot()
    dataset = ArrayHistoricalDataset(_series())
    snaps = historical_shocked_snapshots(base, dataset)
    assert len(snaps) == 3
    assert snaps[1].rates["USD"] == pytest.approx(0.045)


def test_deep_freeze_preserved_on_shocked_snapshot():
    base = _base_snapshot()
    scenario = market_scenario_from_change(
        AggregateFactorChange(1, -0.05, 0.0, 10.0, 0.0),
        base,
    )
    shocked = apply_market_scenario(base, scenario)
    with pytest.raises(TypeError):
        shocked.equity_spots["SPY"] = 1.0  # type: ignore[index]
    with pytest.raises(TypeError):
        shocked.rates["USD"] = 0.99  # type: ignore[index]


def test_var_analytics_unaffected_by_scenario_module():
    """M2.2 must not change Δ-Γ VaR numerical path."""
    series = FactorObservationSeries(
        equity_returns=np.linspace(-0.02, 0.02, 40),
        vol_moves=np.zeros(40),
        rate_moves_bps=np.zeros(40),
        fx_returns=np.zeros(40),
    )
    report = VaRAnalytics(dataset=ArrayHistoricalDataset(series)).report(
        SAMPLE_PORTFOLIO,
        BuiltinPricingEngine(),
        confidence=0.95,
        market=demo_market_snapshot(SAMPLE_PORTFOLIO),
    )
    hist = next(m for m in report.methods if m.method == "historical")
    assert hist.var >= 0.0
    # Scenario generation from same series is available for M2.3 without feeding VaR yet
    base = MarketSnapshot(id="m", equity_spots={"SPY": 100.0}, rates={"USD": 0.04})
    assert len(historical_market_scenarios(base, series)) == 40


def test_synthetic_pipeline_is_deterministic():
    base = _base_snapshot()
    ds = SyntheticHistoricalDataset(seed=11, observations=25)
    a = historical_shocked_snapshots(base, ds)
    b = historical_shocked_snapshots(base, ds)
    assert len(a) == 25
    assert [s.content_hash() for s in a] == [s.content_hash() for s in b]


def test_historical_market_scenarios_yield_canonical_scenario_not_market_scenario():
    """R0.4.2-G: generation stores/yields Scenario + FactorShock, not MarketScenario."""
    base = _base_snapshot()
    scenarios = historical_market_scenarios(base, _series())
    assert scenarios
    for scenario in scenarios:
        assert type(scenario) is Scenario
        assert all(isinstance(shock, FactorShock) for shock in scenario.shocks)
        assert scenario.category == ScenarioCategory.HISTORICAL_REPLAY
        assert "observation_index" in scenario.metadata


def test_historical_scenario_apply_matches_market_scenario_adapter_identity():
    """Canonical apply must match the MarketScenario adapter (snapshot + P&L)."""
    book = SAMPLE_PORTFOLIO
    market = demo_market_snapshot(book)
    pricing = BuiltinPricingEngine()
    series = _series()
    scenarios = historical_market_scenarios(market, series)
    base_mv = sum(pricing.value(p, market).market_value for p in book.positions)
    for formal in scenarios:
        adapted = scenario_to_market_scenario(formal)
        via_formal = apply_scenario(market, formal)
        via_adapter = apply_market_scenario(market, adapted)
        assert via_formal.content_hash() == via_adapter.content_hash()
        assert via_formal.id == via_adapter.id
        formal_mv = sum(pricing.value(p, via_formal).market_value for p in book.positions)
        adapter_mv = sum(pricing.value(p, via_adapter).market_value for p in book.positions)
        assert formal_mv == pytest.approx(adapter_mv, abs=1e-12)
        assert (formal_mv - base_mv) == pytest.approx(adapter_mv - base_mv, abs=1e-12)
    # Live snapshot expansion: a name absent from demo still receives the aggregate.
    live = MarketSnapshot(
        id="live-hist",
        equity_spots={"NEWEQ": 50.0, "SPY": 100.0},
        equity_vols={"NEWEQ": 0.25},
        rates={"USD": 0.04},
    )
    live_scenarios = historical_market_scenarios(live, series)
    eq_symbols = {
        shock.factor.symbol
        for scenario in live_scenarios
        for shock in scenario.shocks
        if isinstance(shock.factor, EquitySpot)
    }
    assert "NEWEQ" in eq_symbols
    assert "SPY" in eq_symbols


def test_panel_historical_scenarios_yield_canonical_scenario():
    panel = HistoricalFactorPanel.from_pairs(
        dates=[date(2024, 1, 2)],
        rows=[[(EquitySpot("AAA"), 0.10), (EquitySpot("BBB"), -0.20)]],
    )
    scenarios = historical_market_scenarios_from_panel(panel)
    assert len(scenarios) == 1
    scenario = scenarios[0]
    assert type(scenario) is Scenario
    assert all(isinstance(shock, FactorShock) for shock in scenario.shocks)
    assert scenario.category == ScenarioCategory.HISTORICAL_REPLAY
    amounts = {
        shock.factor.symbol: shock.amount
        for shock in scenario.shocks
        if isinstance(shock.factor, EquitySpot)
    }
    assert amounts["AAA"] == pytest.approx(0.10)
    assert amounts["BBB"] == pytest.approx(-0.20)
