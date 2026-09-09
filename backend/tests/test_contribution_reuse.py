"""R0.6.6 — full-reval factor contributions must reuse trade/scenario grain.

Family contributions must not reprice the whole book once per factor family.
Pin reconcile and cash-equity identity against existing LINEAR / ES / scenario
attribution invariants (no invented risk numbers).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from tests.market_fixtures import equity_spots_market

import app.risk.es as es_mod
import app.risk.scenario_attribution as attr_mod
import app.risk.scenarios as scenarios_mod
from app.domain.models import (
    EquityPosition,
    EuropeanOptionPosition,
    MarketSnapshot,
    Portfolio,
    ScenarioKind,
    StressScenario,
    Valuation,
    VaRMethodology,
)
from app.interfaces.pricing import PricingEngine
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.es import (
    ESContributionAnalytics,
    _aggregate_factor_pnl_full_reval,
    _aggregate_factor_pnl_full_reval_from_panel,
    _aggregate_factor_pnl_linear,
)
from app.risk.factor_panel import HistoricalFactorPanel
from app.risk.factor_types import EquitySpot, EquityVol
from app.risk.historical import full_revaluation_pnl_series
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.scenario_attribution import ScenarioAttributionEngine
from app.risk.scenario_model import FactorShock, Scenario, ScenarioCategory
from app.risk.scenarios import apply_market_scenario

N_FAMILIES = 4
N_OBS = 5


class CountingPricingEngine(PricingEngine):
    def __init__(self) -> None:
        self.calls = 0
        self._inner = BuiltinPricingEngine()

    def value(self, position, market=None) -> Valuation:
        self.calls += 1
        return self._inner.value(position, market)


def _cash_book() -> Portfolio:
    return Portfolio(
        id="reuse-eq",
        name="reuse-eq",
        positions=[
            EquityPosition(type="equity", id="eq-a", symbol="SPY", quantity=10.0),
            EquityPosition(type="equity", id="eq-b", symbol="NVDA", quantity=4.0),
        ],
    )


def _cash_market() -> MarketSnapshot:
    return equity_spots_market(
        {"SPY": 100.0, "NVDA": 50.0},
        vols={"SPY": 0.2, "NVDA": 0.4},
    )


def _mixed_series(n: int = N_OBS) -> FactorObservationSeries:
    rng = np.random.default_rng(7)
    return FactorObservationSeries(
        equity_returns=rng.normal(-0.002, 0.02, n),
        vol_moves=rng.normal(0.0, 0.08, n),
        rate_moves_bps=rng.normal(0.0, 4.0, n),
        fx_returns=rng.normal(0.0, 0.008, n),
    )


def _option_book() -> Portfolio:
    return Portfolio(
        id="reuse-opt",
        name="reuse-opt",
        positions=[
            EquityPosition(type="equity", id="eq", symbol="SPY", quantity=10.0),
            EuropeanOptionPosition(
                type="european_option",
                id="opt",
                symbol="SPY",
                quantity=2.0,
                strike=100.0,
                maturity_years=0.5,
                option_type="call",
            ),
        ],
    )


def _option_panel() -> HistoricalFactorPanel:
    spy = EquitySpot("SPY")
    vol = EquityVol(underlying="SPY")
    dates = [date(2024, 1, i + 1) for i in range(N_OBS)]
    rows = [[(spy, -0.04 + 0.01 * i), (vol, 0.10 + 0.02 * i)] for i in range(N_OBS)]
    return HistoricalFactorPanel.from_pairs(dates=dates, rows=rows)


def test_full_reval_factor_helper_does_not_apply_or_value_per_family(monkeypatch):
    """Bound: family contributions stay O(S) grain — not O(families × S) extra books."""
    book, market = _cash_book(), _cash_market()
    dataset = ArrayHistoricalDataset(_mixed_series())
    pricing = CountingPricingEngine()
    total = full_revaluation_pnl_series(book, BuiltinPricingEngine(), market, dataset)

    applies: list[object] = []

    def counting_apply(base, scenario):
        applies.append(scenario)
        return apply_market_scenario(base, scenario)

    monkeypatch.setattr(scenarios_mod, "apply_market_scenario", counting_apply)
    if hasattr(es_mod, "apply_market_scenario"):
        monkeypatch.setattr(es_mod, "apply_market_scenario", counting_apply)

    factor_pnl = _aggregate_factor_pnl_full_reval(book, pricing, market, dataset, total)

    n_pos = len(book.positions)
    # One base value_portfolio for Greeks — not a reprice per family × observation.
    assert pricing.calls == n_pos
    assert applies == []
    assert pricing.calls < n_pos * N_OBS * N_FAMILIES
    residual = total - sum(factor_pnl[k] for k in ("equity", "vol", "rate", "fx"))
    np.testing.assert_allclose(factor_pnl["interaction"], residual, atol=1e-12)


def test_full_reval_panel_factor_helper_does_not_apply_per_family(monkeypatch):
    book, market = _option_book(), _cash_market()
    panel = _option_panel()
    pricing = CountingPricingEngine()
    n = panel.n_observations
    total = np.zeros(n)

    applies: list[object] = []

    def counting_apply(base, scenario):
        applies.append(scenario)
        return apply_market_scenario(base, scenario)

    monkeypatch.setattr(scenarios_mod, "apply_market_scenario", counting_apply)
    if hasattr(es_mod, "apply_market_scenario"):
        monkeypatch.setattr(es_mod, "apply_market_scenario", counting_apply)

    factor_pnl = _aggregate_factor_pnl_full_reval_from_panel(
        book, pricing, market, panel, total
    )

    n_pos = len(book.positions)
    assert applies == []
    assert pricing.calls == n_pos
    assert pricing.calls < n_pos * n * 2
    residual = total - sum(factor_pnl[k] for k in ("equity", "vol", "rate", "fx"))
    np.testing.assert_allclose(factor_pnl["interaction"], residual, atol=1e-12)


def test_full_reval_factor_pnl_matches_linear_for_cash_equity():
    """Cash equity isolated full-reval P&L is the LINEAR Greek split (existing units)."""
    book, market = _cash_book(), _cash_market()
    series = _mixed_series()
    dataset = ArrayHistoricalDataset(series)
    pricing = BuiltinPricingEngine()
    total = full_revaluation_pnl_series(book, pricing, market, dataset)
    linear = _aggregate_factor_pnl_linear(
        book,
        pricing,
        market,
        VaRMethodology.LINEAR,
        series.equity_returns,
        series.vol_moves,
        series.rate_moves_bps,
        series.fx_returns,
    )
    full = _aggregate_factor_pnl_full_reval(book, pricing, market, dataset, total)
    np.testing.assert_allclose(full["equity"], linear["equity"], atol=1e-12)
    np.testing.assert_allclose(full["vol"], 0.0, atol=1e-12)
    np.testing.assert_allclose(full["rate"], 0.0, atol=1e-12)
    np.testing.assert_allclose(full["fx"], 0.0, atol=1e-12)
    np.testing.assert_allclose(full["interaction"], 0.0, atol=1e-12)
    np.testing.assert_allclose(full["equity"], total, atol=1e-12)


def test_es_full_reval_report_value_calls_do_not_scale_with_families():
    book, market = _cash_book(), _cash_market()
    dataset = ArrayHistoricalDataset(_mixed_series())
    pricing = CountingPricingEngine()
    report = ESContributionAnalytics(dataset=dataset).report(
        book,
        pricing,
        confidence=0.8,
        methodology=VaRMethodology.FULL_REVALUATION,
        market=market,
    )
    n_pos = len(book.positions)
    # Joint full-reval: N base + N×S shocked. Family split: one more base valuation.
    # Old path: + N×S×4 isolated books.
    assert pricing.calls <= n_pos * (N_OBS + 3)
    assert pricing.calls < n_pos * (1 + N_OBS * (1 + N_FAMILIES))
    assert abs(report.reconciliation_error_position) < 1e-6
    assert abs(report.reconciliation_error_risk_factor) < 1e-6


def test_es_full_reval_cash_equity_matches_linear_factor_es():
    book, market = _cash_book(), _cash_market()
    dataset = ArrayHistoricalDataset(_mixed_series())
    pricing = BuiltinPricingEngine()
    full = ESContributionAnalytics(dataset=dataset).report(
        book, pricing, confidence=0.8, methodology=VaRMethodology.FULL_REVALUATION, market=market
    )
    linear = ESContributionAnalytics(dataset=dataset).report(
        book, pricing, confidence=0.8, methodology=VaRMethodology.LINEAR, market=market
    )
    full_by = {c.key: c.component_es for c in full.by_risk_factor}
    linear_by = {c.key: c.component_es for c in linear.by_risk_factor}
    assert full_by["equity"] == pytest.approx(linear_by["equity"], abs=1e-12)
    assert full_by.get("interaction", 0.0) == pytest.approx(0.0, abs=1e-9)


def test_scenario_attribution_does_not_apply_isolated_factor_scenarios(monkeypatch):
    book, market = _option_book(), _cash_market()
    pricing = CountingPricingEngine()
    scenario = StressScenario(
        id="multi",
        name="Eq+Vol+Rates",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.15,
        vol_shock=0.4,
        rates_shift_bps=100,
    )
    applies: list[object] = []
    real_apply = attr_mod.apply_scenario

    def counting_apply(base, scen):
        applies.append(scen)
        return real_apply(base, scen)

    monkeypatch.setattr(attr_mod, "apply_scenario", counting_apply)

    report = ScenarioAttributionEngine().decompose(book, pricing, scenario, market=market)

    full_id_applies = [s for s in applies if getattr(s, "id", None) == scenario.id]
    isolated = [s for s in applies if getattr(s, "id", None) != scenario.id]
    assert len(full_id_applies) == 1
    assert isolated == []
    n_pos = len(book.positions)
    # Base + one shocked snapshot; not × number of factor keys.
    assert pricing.calls == n_pos * 2
    assert abs(report.reconciliation_error_risk_factor) < 1e-6
    assert abs(report.reconciliation_error_trade) < 1e-9


def test_formal_scenario_factor_reuse_reconciles_without_extra_apply(monkeypatch):
    book, market = _option_book(), _cash_market()
    pricing = BuiltinPricingEngine()
    formal = Scenario(
        id="typed_eq_vol",
        name="Typed equity+vol",
        category=ScenarioCategory.MACRO,
        shocks=(
            FactorShock(EquitySpot("SPY"), -0.1),
            FactorShock(EquityVol(underlying="SPY"), 0.25),
        ),
    )
    applies: list[object] = []
    real_apply = attr_mod.apply_scenario

    def counting_apply(base, scen):
        applies.append(scen)
        return real_apply(base, scen)

    monkeypatch.setattr(attr_mod, "apply_scenario", counting_apply)

    report = ScenarioAttributionEngine().decompose(book, pricing, formal, market=market)
    assert [getattr(s, "id", None) for s in applies] == ["typed_eq_vol"]
    keys = {c.key for c in report.by_risk_factor}
    assert "SPY" in keys
    assert "SPY:VOL" in keys
    assert "interaction" in keys
    assert abs(report.reconciliation_error_risk_factor) < 1e-6
