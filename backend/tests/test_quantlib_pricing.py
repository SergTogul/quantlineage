from datetime import date

import pytest

ql = pytest.importorskip("QuantLib")

from app.domain.models import (
    BondPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    StressScenario,
    SwapPosition,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine


@pytest.fixture
def engine():
    return QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))


def _forbid_builtin_fallback(monkeypatch):
    """Fail loudly if QuantLib adapter still delegates to the reference engine."""

    def boom(self, position, market=None):
        raise AssertionError(
            f"QuantLibPricingEngine must not fall back to Builtin for {type(position).__name__}"
        )

    monkeypatch.setattr(BuiltinPricingEngine, "value", boom)


def test_equity_value(engine):
    p = EquityPosition(type="equity", id="e", symbol="ABC", quantity=10, price=25)
    v = engine.value(p)
    assert v.market_value == 250
    assert v.delta == 250


def test_european_option_matches_builtin_closely(engine):
    p = EuropeanOptionPosition(
        type="european_option", id="o", symbol="ABC", quantity=100,
        spot=100, strike=100, maturity_years=1, volatility=.2,
        risk_free_rate=.03, option_type="call"
    )
    ql_v = engine.value(p)
    builtin_v = BuiltinPricingEngine().value(p)
    assert ql_v.market_value == pytest.approx(builtin_v.market_value, rel=2e-3)
    assert ql_v.delta == pytest.approx(builtin_v.delta, rel=2e-3)
    assert ql_v.gamma == pytest.approx(builtin_v.gamma, rel=2e-3)
    assert ql_v.vega == pytest.approx(builtin_v.vega, rel=2e-3)


def test_long_zero_coupon_bond_has_negative_dv01(engine):
    p = BondPosition(type="bond", id="b", issuer="UST", face_value=1_000_000,
                     maturity_years=5, yield_rate=.04, duration=4.5)
    v = engine.value(p)
    assert v.market_value > 0
    assert v.dv01 < 0


def test_pay_fixed_swap_value_increases_when_rates_rise(engine):
    p = SwapPosition(type="swap", id="s", notional=1_000_000, maturity_years=5,
                     fixed_rate=.04, market_swap_rate=.04, pay_fixed=True, duration=4)
    base = engine.value(p).market_value
    higher = engine.value(p.model_copy(update={"market_swap_rate": .05})).market_value
    assert higher > base


def test_stress_revalues_option(engine):
    p = EuropeanOptionPosition(
        type="european_option", id="o", symbol="ABC", quantity=10,
        spot=100, strike=100, maturity_years=1, volatility=.2,
        risk_free_rate=.03, option_type="put"
    )
    scenario = StressScenario(name="down-vol-up", equity_shock=-.1, vol_shock=.25)
    assert engine.shocked_value(p, scenario) != engine.value(p).market_value


def test_equity_future_matches_builtin_without_fallback(engine, monkeypatch):
    p = EquityFuturePosition(
        type="equity_future",
        id="fut",
        symbol="SPY",
        quantity=10,
        spot=500.0,
        multiplier=50.0,
        maturity_years=0.25,
        risk_free_rate=0.04,
        dividend_yield=0.01,
    )
    builtin_v = BuiltinPricingEngine().value(p)
    _forbid_builtin_fallback(monkeypatch)
    ql_v = engine.value(p)
    # Algebraic identity via Time-based FlatForward DFs — require near-exact parity.
    assert ql_v.market_value == pytest.approx(builtin_v.market_value, rel=1e-12, abs=1e-9)
    assert ql_v.delta == pytest.approx(builtin_v.delta, rel=1e-12, abs=1e-9)
    assert ql_v.dv01 == pytest.approx(builtin_v.dv01, rel=1e-12, abs=1e-9)


def test_fx_forward_matches_builtin_without_fallback(engine, monkeypatch):
    p = FXForwardPosition(
        type="fx_forward",
        id="fxf",
        pair="EURUSD",
        notional_base=1_000_000,
        spot=1.10,
        strike=1.105,
        maturity_years=0.5,
        domestic_rate=0.04,
        foreign_rate=0.03,
    )
    builtin_v = BuiltinPricingEngine().value(p)
    _forbid_builtin_fallback(monkeypatch)
    ql_v = engine.value(p)
    assert ql_v.market_value == pytest.approx(builtin_v.market_value, rel=1e-12, abs=1e-9)
    assert ql_v.fx_delta == pytest.approx(builtin_v.fx_delta, rel=1e-12, abs=1e-9)


def test_fx_option_matches_builtin_without_fallback(engine, monkeypatch):
    # Non-integer year fraction so calendar-day exercise rounding is exercised.
    p = FXOptionPosition(
        type="fx_option",
        id="fxo",
        pair="EURUSD",
        notional_base=250_000,
        spot=1.10,
        strike=1.12,
        maturity_years=0.37,
        volatility=0.12,
        domestic_rate=0.04,
        foreign_rate=0.03,
        option_type="put",
    )
    builtin_v = BuiltinPricingEngine().value(p)
    _forbid_builtin_fallback(monkeypatch)
    ql_v = engine.value(p)
    # Date-rounded exercise vs continuous T — allow modest relative gap.
    assert ql_v.market_value == pytest.approx(builtin_v.market_value, rel=5e-3)
    assert ql_v.fx_delta == pytest.approx(builtin_v.fx_delta, rel=5e-3)
    assert ql_v.gamma == pytest.approx(builtin_v.gamma, rel=5e-3)
    assert ql_v.vega == pytest.approx(builtin_v.vega, rel=5e-3)


def test_fx_option_sub_day_maturity_uses_one_day_exercise(engine, monkeypatch):
    """Documented policy: T < ~1/365 clamps QL exercise to 1 calendar day."""
    p = FXOptionPosition(
        type="fx_option",
        id="fxo-tiny",
        pair="EURUSD",
        notional_base=100_000,
        spot=1.10,
        strike=1.10,
        maturity_years=1.0 / 3650.0,
        volatility=0.12,
        option_type="call",
    )
    builtin_v = BuiltinPricingEngine().value(p)
    _forbid_builtin_fallback(monkeypatch)
    ql_v = engine.value(p)
    assert ql_v.market_value > 0.0
    # Builtin uses continuous T → near-zero; QL one-day clamp diverges by design.
    assert abs(ql_v.market_value - builtin_v.market_value) > abs(builtin_v.market_value)


def test_extended_instruments_respect_market_snapshot(engine, monkeypatch):
    future = EquityFuturePosition(
        type="equity_future", id="fut", symbol="SPY", quantity=2, spot=500.0,
        multiplier=50.0, maturity_years=0.25, risk_free_rate=0.04,
    )
    fx_fwd = FXForwardPosition(
        type="fx_forward", id="fxf", pair="EURUSD", notional_base=100_000,
        spot=1.10, strike=1.10, maturity_years=1.0, domestic_rate=0.04, foreign_rate=0.03,
    )
    fx_opt = FXOptionPosition(
        type="fx_option", id="fxo", pair="EURUSD", notional_base=50_000,
        spot=1.10, strike=1.10, maturity_years=0.5, volatility=0.10,
        domestic_rate=0.04, foreign_rate=0.03, option_type="call",
    )
    market = MarketSnapshot(
        equity_spots={"SPY": 520.0},
        fx_spots={"EURUSD": 1.20},
        fx_vols={"EURUSD": 0.18},
        rates={"USD": 0.05, "EUR": 0.02},
    )
    expected = {
        p.id: BuiltinPricingEngine().value(p, market)
        for p in (future, fx_fwd, fx_opt)
    }
    _forbid_builtin_fallback(monkeypatch)
    for position in (future, fx_fwd, fx_opt):
        ql_shocked = engine.value(position, market)
        builtin_shocked = expected[position.id]
        assert ql_shocked.market_value == pytest.approx(
            builtin_shocked.market_value,
            rel=5e-3 if isinstance(position, FXOptionPosition) else 1e-12,
            abs=1e-6,
        )
    assert engine.value(future, market).market_value > engine.value(future).market_value


def test_ir_future_matches_builtin_without_fallback(engine, monkeypatch):
    p = InterestRateFuturePosition(
        type="ir_future",
        id="ed",
        currency="USD",
        quantity=10,
        pv01=25.0,
        quoted_rate=0.042,
        forward_rate=0.040,
        maturity_years=0.25,
    )
    builtin_v = BuiltinPricingEngine().value(p)
    _forbid_builtin_fallback(monkeypatch)
    ql_v = engine.value(p)
    assert ql_v.market_value == pytest.approx(builtin_v.market_value, rel=1e-12, abs=1e-9)
    assert ql_v.dv01 == pytest.approx(builtin_v.dv01, rel=1e-12, abs=1e-9)
    # Long future: higher forward → lower MV
    higher = engine.value(p, MarketSnapshot(rates={"USD": 0.045}))
    assert higher.market_value < ql_v.market_value
