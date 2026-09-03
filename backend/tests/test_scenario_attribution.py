"""M3.4 / M4.1 Scenario contribution decomposition and reconciliation.

Conventions:
- Stress P&L in currency units; negative = loss (same as StressEvaluation.pnl)
- Hierarchy (portfolio/desk/strategy/book/trade) = exact sums of trade P&L
- Desk/strategy keys via resolve_desk / resolve_strategy (per-position placement)
- Risk-factor = factor-isolated full revaluation + ``interaction`` residual
- Empty / zero shocks → portfolio_pnl = 0; factor list empty
- Tolerances: abs 1e-6 (currency) or rel 1e-8 for reconciliation
"""

from __future__ import annotations

import math

from app.domain.models import (
    EquityPosition,
    EuropeanOptionPosition,
    Portfolio,
    ScenarioKind,
    StressScenario,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import EquitySpot, EquityVol, RateZero
from app.risk.scenario_attribution import ScenarioAttributionEngine
from app.risk.scenario_model import FactorShock, Scenario, ScenarioCategory, ScenarioThreshold
from app.risk.stress import DEFAULT_SCENARIOS, StressEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)


def _two_book_portfolio() -> Portfolio:
    return Portfolio(
        id="stress-books",
        name="Stress Books",
        desk="Macro Desk",
        strategy="Directional",
        positions=[
            EquityPosition(
                type="equity",
                id="eq-a",
                symbol="SPY",
                quantity=100,
                price=500.0,
                book="Equity Cash",
            ),
            EquityPosition(
                type="equity",
                id="eq-b",
                symbol="NVDA",
                quantity=50,
                price=120.0,
                book="Equity Cash",
            ),
            EuropeanOptionPosition(
                type="european_option",
                id="opt-a",
                symbol="SPY",
                quantity=20,
                spot=500.0,
                strike=480.0,
                maturity_years=0.5,
                volatility=0.20,
                option_type="put",
                book="Equity Derivatives",
            ),
        ],
    )


def _assert_reconciles(contributions, portfolio_pnl: float, *, abs_tol: float = 1e-6) -> None:
    total = sum(c.pnl for c in contributions)
    assert math.isclose(total, portfolio_pnl, abs_tol=abs_tol, rel_tol=1e-8), (
        f"contribution sum {total} vs portfolio P&L {portfolio_pnl}"
    )
    if portfolio_pnl:
        assert math.isclose(sum(c.contribution_pct for c in contributions), 100.0, abs_tol=1e-6)


def test_scenario_attribution_importable():
    assert ScenarioAttributionEngine is not None


def _multi_desk_portfolio() -> Portfolio:
    """Positions with per-trade desk/strategy overrides (M4.1 placement)."""
    return Portfolio(
        id="multi-desk-stress",
        name="Multi Desk Stress",
        firm="Acme Capital",
        desk="Default Desk",
        strategy="Default Strat",
        positions=[
            EquityPosition(
                type="equity",
                id="eq-a",
                symbol="SPY",
                quantity=100,
                price=500.0,
                book="Cash A",
                desk="Rates Desk",
                strategy="Carry",
            ),
            EquityPosition(
                type="equity",
                id="eq-b",
                symbol="NVDA",
                quantity=50,
                price=120.0,
                book="Cash B",
                desk="Equity Desk",
                strategy="Momentum",
            ),
            EquityPosition(
                type="equity",
                id="eq-c",
                symbol="QQQ",
                quantity=25,
                price=40.0,
                book="Cash B",
                # desk/strategy omitted → inherit portfolio defaults
            ),
        ],
    )


def test_trade_book_desk_strategy_portfolio_reconcile():
    pricing = BuiltinPricingEngine()
    book = _two_book_portfolio()
    scenario = StressScenario(
        id="eq_down",
        name="Equities -10%",
        kind=ScenarioKind.FACTOR,
        equity_shock=-0.10,
    )
    report = ScenarioAttributionEngine().decompose(
        book, pricing, scenario, market=demo_market_snapshot(book)
    )

    assert math.isclose(report.portfolio_pnl, sum(c.pnl for c in report.by_trade), abs_tol=1e-9)
    _assert_reconciles(report.by_trade, report.portfolio_pnl)
    _assert_reconciles(report.by_book, report.portfolio_pnl)
    _assert_reconciles(report.by_desk, report.portfolio_pnl)
    _assert_reconciles(report.by_strategy, report.portfolio_pnl)
    _assert_reconciles(report.by_portfolio, report.portfolio_pnl)

    assert {c.key for c in report.by_book} == {"Equity Cash", "Equity Derivatives"}
    assert report.by_desk[0].key == "Macro Desk"
    assert report.by_strategy[0].key == "Directional"
    assert report.by_portfolio[0].key == book.id

    cash_trades = sum(
        c.pnl for c in report.by_trade if c.key in {"eq-a", "eq-b"}
    )
    cash_book = next(c.pnl for c in report.by_book if c.key == "Equity Cash")
    assert math.isclose(cash_trades, cash_book, abs_tol=1e-9)

    assert report.reconciliation_error_trade < 1e-9
    assert report.reconciliation_error_book < 1e-9


def test_multi_desk_strategy_placement_attribution():
    """Desk/strategy stress contributions follow position placement, not portfolio defaults only."""
    pricing = BuiltinPricingEngine()
    book = _multi_desk_portfolio()
    scenario = StressScenario(
        id="eq_down",
        name="Equities -10%",
        kind=ScenarioKind.FACTOR,
        equity_shock=-0.10,
    )
    report = ScenarioAttributionEngine().decompose(
        book, pricing, scenario, market=demo_market_snapshot(book)
    )

    assert {c.key for c in report.by_desk} == {"Rates Desk", "Equity Desk", "Default Desk"}
    assert {c.key for c in report.by_strategy} == {"Carry", "Momentum", "Default Strat"}
    _assert_reconciles(report.by_desk, report.portfolio_pnl)
    _assert_reconciles(report.by_strategy, report.portfolio_pnl)
    assert report.reconciliation_error_desk < 1e-9
    assert report.reconciliation_error_strategy < 1e-9

    trade_by_id = {c.key: c.pnl for c in report.by_trade}
    desk_by_key = {c.key: c.pnl for c in report.by_desk}
    strategy_by_key = {c.key: c.pnl for c in report.by_strategy}

    assert math.isclose(desk_by_key["Rates Desk"], trade_by_id["eq-a"], abs_tol=1e-9)
    assert math.isclose(desk_by_key["Equity Desk"], trade_by_id["eq-b"], abs_tol=1e-9)
    assert math.isclose(desk_by_key["Default Desk"], trade_by_id["eq-c"], abs_tol=1e-9)
    assert math.isclose(strategy_by_key["Carry"], trade_by_id["eq-a"], abs_tol=1e-9)
    assert math.isclose(strategy_by_key["Momentum"], trade_by_id["eq-b"], abs_tol=1e-9)
    assert math.isclose(strategy_by_key["Default Strat"], trade_by_id["eq-c"], abs_tol=1e-9)


def test_risk_factor_contributions_reconcile_with_interaction():
    pricing = BuiltinPricingEngine()
    scenario = StressScenario(
        id="multi",
        name="Eq+Vol+Rates",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.15,
        vol_shock=0.40,
        rates_shift_bps=100,
    )
    report = ScenarioAttributionEngine().decompose(
        SAMPLE_PORTFOLIO, pricing, scenario, market=SAMPLE_MARKET
    )

    assert report.by_risk_factor
    keys = {c.key for c in report.by_risk_factor}
    assert "interaction" in keys
    assert keys & {"SPY", "NVDA"}  # equity spots from SAMPLE_PORTFOLIO
    _assert_reconciles(report.by_risk_factor, report.portfolio_pnl)
    assert report.reconciliation_error_risk_factor < 1e-6


def test_formal_scenario_decomposition():
    pricing = BuiltinPricingEngine()
    formal = Scenario(
        id="typed_eq_vol",
        name="Typed equity+vol",
        category=ScenarioCategory.MACRO,
        description="Formal Scenario path",
        shocks=(
            FactorShock(EquitySpot("SPY"), -0.10),
            FactorShock(EquityVol(underlying="SPY"), 0.25),
            FactorShock(RateZero(currency="USD", tenor="ALL"), 0.01),
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.10),
    )
    report = ScenarioAttributionEngine().decompose(
        SAMPLE_PORTFOLIO, pricing, formal, market=SAMPLE_MARKET
    )
    assert report.scenario_id == "typed_eq_vol"
    _assert_reconciles(report.by_trade, report.portfolio_pnl)
    _assert_reconciles(report.by_risk_factor, report.portfolio_pnl)
    factor_keys = {c.key for c in report.by_risk_factor}
    assert "SPY" in factor_keys
    assert "SPY:VOL" in factor_keys
    assert "USD:RATE" in factor_keys
    assert "interaction" in factor_keys


def test_empty_scenario_zero_pnl():
    pricing = BuiltinPricingEngine()
    zero = StressScenario(id="flat", name="Flat", kind=ScenarioKind.FACTOR)
    report = ScenarioAttributionEngine().decompose(
        SAMPLE_PORTFOLIO, pricing, zero, market=SAMPLE_MARKET
    )
    assert report.portfolio_pnl == 0.0
    assert all(c.pnl == 0.0 for c in report.by_trade)
    assert report.by_risk_factor == []
    _assert_reconciles(report.by_trade, 0.0)


def test_empty_portfolio_yields_empty_contributions():
    pricing = BuiltinPricingEngine()
    empty = Portfolio(id="empty", name="Empty", positions=[])
    scenario = StressScenario(id="eq", name="Eq", equity_shock=-0.1)
    report = ScenarioAttributionEngine().decompose(
        empty, pricing, scenario, market=demo_market_snapshot(empty)
    )
    assert report.portfolio_pnl == 0.0
    assert report.by_trade == []
    assert report.by_book == []
    assert report.by_risk_factor == []


def test_stress_engine_evaluate_includes_contributions():
    pricing = BuiltinPricingEngine()
    report = StressEngine().evaluate(
        SAMPLE_PORTFOLIO, pricing, DEFAULT_SCENARIOS[:2], market=SAMPLE_MARKET
    )
    for ev in report.evaluations:
        assert ev.contributions is not None
        assert math.isclose(ev.contributions.portfolio_pnl, ev.pnl, abs_tol=1e-9)
        _assert_reconciles(ev.contributions.by_trade, ev.pnl)
        _assert_reconciles(ev.contributions.by_book, ev.pnl)
        if ev.contributions.by_risk_factor:
            _assert_reconciles(ev.contributions.by_risk_factor, ev.pnl)


def test_single_factor_interaction_near_zero():
    """Isolating the only shocked factor should leave ~0 interaction."""
    pricing = BuiltinPricingEngine()
    scenario = StressScenario(
        id="eq_only",
        name="Equity only",
        kind=ScenarioKind.FACTOR,
        equity_shock=-0.10,
    )
    # Equity-only book: no rates/vol instruments beyond spot.
    book = Portfolio(
        id="eq-only",
        name="Eq Only",
        positions=[
            EquityPosition(type="equity", id="eq1", symbol="SPY", quantity=10, price=100.0),
        ],
    )
    report = ScenarioAttributionEngine().decompose(
        book, pricing, scenario, market=demo_market_snapshot(book)
    )
    interaction = next(c for c in report.by_risk_factor if c.key == "interaction")
    assert abs(interaction.pnl) < 1e-9
    _assert_reconciles(report.by_risk_factor, report.portfolio_pnl)


def test_deterministic_decomposition():
    pricing = BuiltinPricingEngine()
    scenario = DEFAULT_SCENARIOS[3]  # eq_down_vol_up
    a = ScenarioAttributionEngine().decompose(
        SAMPLE_PORTFOLIO, pricing, scenario, market=SAMPLE_MARKET
    )
    b = ScenarioAttributionEngine().decompose(
        SAMPLE_PORTFOLIO, pricing, scenario, market=SAMPLE_MARKET
    )
    assert a.model_dump() == b.model_dump()
