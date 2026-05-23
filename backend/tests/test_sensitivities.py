"""Tests for bump-and-revalue SensitivityEngine (M1.7).

Reference: BuiltinPricingEngine analytic Greeks / DV01 conventions.
Tolerances are FD truncation error vs closed form (relative spot bump 1%,
vol ±1pt, rate ±1bp).
"""

from __future__ import annotations

import math

import pytest
from tests.market_fixtures import equity_spot_market, fx_market, usd_rate_market

from app.domain.models import (
    BondPosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    MarketSnapshot,
    Portfolio,
    SwapPosition,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, RateZero
from app.risk.sensitivities import FUTURE_MEASURES, SensitivityEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

pricing = BuiltinPricingEngine()
SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)


def _close(a: float, b: float, *, rel: float = 0.05, abs_tol: float = 1.0) -> None:
    assert math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol), f"{a} !~ {b} (rel={rel}, abs={abs_tol})"


def test_equity_cash_delta_matches_analytic():
    pos = EquityPosition(type="equity", id="e", symbol="ABC", quantity=10)
    market = equity_spot_market("ABC", 25.0)
    engine = SensitivityEngine(spot_bump=0.001)
    measures = engine.calculate_position(pos, pricing, measures=("delta",), market=market)
    assert len(measures) == 1
    assert measures[0].factor == EquitySpot("ABC")
    analytic = pricing.value(pos, market).delta
    _close(measures[0].value, analytic, rel=1e-6, abs_tol=1e-6)


def test_option_delta_gamma_vega_vs_analytic():
    pos = EuropeanOptionPosition(
        type="european_option",
        id="o",
        symbol="XYZ",
        quantity=100,
        strike=100.0,
        maturity_years=1.0,
        option_type="call",
    )
    market = equity_spot_market("XYZ", 100.0, rate=0.03, vol=0.2)
    analytic = pricing.value(pos, market)
    # Tighter spot bump for gamma accuracy on BS.
    engine = SensitivityEngine(spot_bump=0.005, vol_bump=0.01)
    out = {
        m.name: m
        for m in engine.calculate_position(
            pos, pricing, measures=("delta", "gamma", "vega"), market=market
        )
    }
    _close(out["delta"].value, analytic.delta, rel=0.02, abs_tol=0.5)
    _close(out["gamma"].value, analytic.gamma, rel=0.08, abs_tol=2.0)
    _close(out["vega"].value, analytic.vega, rel=0.02, abs_tol=0.5)
    assert out["vega"].unit == "per_vol_point"
    assert out["gamma"].factor == EquitySpot("XYZ")
    assert any(
        m.factor == EquityVol("XYZ")
        for m in engine.calculate_position(pos, pricing, measures=("vega",), market=market)
    )


def test_bond_dv01_sign_and_scale():
    pos = BondPosition(
        type="bond",
        id="b",
        issuer="UST",
        face_value=1_000_000,
        quantity=1,
        maturity_years=10.0,
        duration=8.0,
    )
    market = usd_rate_market(0.04)
    analytic = pricing.value(pos, market).dv01
    engine = SensitivityEngine(rate_bump_bps=1.0)
    measures = engine.calculate_position(pos, pricing, measures=("dv01",), market=market)
    assert len(measures) == 1
    assert measures[0].factor == RateZero("USD", "PARALLEL")
    assert measures[0].value < 0
    # Builtin DV01 is duration-based; FD uses actual yield bump of PV.
    # Agree on sign and order of magnitude (within ~25%).
    _close(measures[0].value, analytic, rel=0.25, abs_tol=5.0)


def test_key_rate_dv01_isolates_maturity_tenor_when_key_rates_present():
    """10Y bond: maturity tenor DV01 is non-zero; off-pillar 2Y bump leaves PV unchanged."""
    pos = BondPosition(
        type="bond",
        id="b",
        issuer="UST",
        face_value=1_000_000,
        quantity=1,
        maturity_years=10.0,
        duration=8.0,
    )
    market = MarketSnapshot(
        id="kr",
        rates={"USD": 0.04},
        key_rates={"USD": {"10Y": 0.04, "2Y": 0.03}},
    )
    engine = SensitivityEngine(rate_bump_bps=1.0)
    portfolio = Portfolio(id="p", name="p", positions=[pos])
    kr = [
        m
        for m in engine.calculate(portfolio, pricing, measures=("key_rate_dv01",), market=market)
        if m.name == "key_rate_dv01" and m.factor == RateZero("USD", "10Y")
    ]
    assert len(kr) == 1
    assert kr[0].method == "bump_revalue"
    assert abs(kr[0].value) > 1.0
    assert kr[0].value < 0

    base_pv = pricing.value(pos, market).market_value
    bumped_2y = market.bump(RateZero("USD", "2Y"), 0.0025)
    assert pricing.value(pos, bumped_2y).market_value == pytest.approx(base_pv, rel=1e-12)
    bumped_10y = market.bump(RateZero("USD", "10Y"), 0.0025)
    assert pricing.value(pos, bumped_10y).market_value < base_pv


def test_key_rate_falls_back_to_parallel_when_missing():
    pos = BondPosition(
        type="bond",
        id="b",
        issuer="UST",
        face_value=1_000_000,
        quantity=1,
        maturity_years=10.0,
        duration=8.0,
    )
    market = usd_rate_market(0.04)
    engine = SensitivityEngine(rate_bump_bps=1.0)
    dv01 = engine.calculate_position(pos, pricing, measures=("dv01",), market=market)[0].value
    kr_m = engine.calculate_position(pos, pricing, measures=("key_rate_dv01",), market=market)[0]
    _close(kr_m.value, dv01, rel=1e-9, abs_tol=1e-9)
    assert kr_m.method == "bump_revalue_parallel_fallback"


def test_swap_key_rate_dv01_uses_true_tenor_bump():
    pos = SwapPosition(
        type="swap",
        id="s",
        notional=5_000_000,
        maturity_years=5.0,
        fixed_rate=0.039,
        pay_fixed=True,
        duration=4.3,
    )
    market = MarketSnapshot(
        id="kr-swap",
        rates={"USD": 0.041},
        key_rates={"USD": {"5Y": 0.041, "10Y": 0.04}},
    )
    engine = SensitivityEngine(rate_bump_bps=1.0)
    portfolio = Portfolio(id="p", name="p", positions=[pos])
    kr = [
        m
        for m in engine.calculate(portfolio, pricing, measures=("key_rate_dv01",), market=market)
        if m.name == "key_rate_dv01"
    ]
    assert len(kr) == 1
    assert kr[0].factor == RateZero("USD", "5Y")
    assert kr[0].method == "bump_revalue"
    analytic = pricing.value(pos, market).dv01
    # 5Y pillar bump on a 5Y swap ≈ analytic flat DV01 (same 1bp at maturity).
    _close(kr[0].value, analytic, rel=1e-6, abs_tol=1e-3)


def test_fx_delta_forward_and_option():
    fwd = FXForwardPosition(
        type="fx_forward",
        id="f",
        pair="EURUSD",
        notional_base=1_000_000,
        strike=1.105,
        maturity_years=0.5,
    )
    market = fx_market("EURUSD", 1.10, domestic_rate=0.04, foreign_rate=0.03)
    engine = SensitivityEngine(spot_bump=0.001)
    m = engine.calculate_position(fwd, pricing, measures=("fx_delta",), market=market)[0]
    assert m.factor == FXSpot("EURUSD")
    _close(m.value, pricing.value(fwd, market).fx_delta, rel=0.02, abs_tol=50.0)

    opt = FXOptionPosition(
        type="fx_option",
        id="o",
        pair="EURUSD",
        notional_base=250_000,
        strike=1.12,
        maturity_years=0.4,
        option_type="call",
    )
    opt_market = fx_market("EURUSD", 1.10, domestic_rate=0.04, foreign_rate=0.03, vol=0.12)
    m2 = engine.calculate_position(opt, pricing, measures=("fx_delta",), market=opt_market)[0]
    _close(m2.value, pricing.value(opt, opt_market).fx_delta, rel=0.05, abs_tol=100.0)


def test_swap_dv01_matches_analytic_linear():
    pos = SwapPosition(
        type="swap",
        id="s",
        notional=5_000_000,
        maturity_years=5.0,
        fixed_rate=0.039,
        pay_fixed=True,
        duration=4.3,
    )
    market = usd_rate_market(0.041)
    analytic = pricing.value(pos, market).dv01
    engine = SensitivityEngine(rate_bump_bps=1.0)
    fd = engine.calculate_position(pos, pricing, measures=("dv01",), market=market)[0].value
    # Linear in rate → FD exact.
    _close(fd, analytic, rel=1e-9, abs_tol=1e-6)


def test_sample_portfolio_emits_core_measures():
    engine = SensitivityEngine()
    results = engine.calculate(SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET)
    names = {m.name for m in results}
    assert {"delta", "gamma", "vega", "dv01", "key_rate_dv01", "fx_delta"} <= names
    assert any(m.factor == EquitySpot("NVDA") and m.name == "delta" for m in results)
    assert any(m.factor == EquityVol("SPY") and m.name == "vega" for m in results)
    assert any(m.factor == RateZero("USD", "PARALLEL") and m.name == "dv01" for m in results)
    # Parallel DV01 once per currency
    assert sum(1 for m in results if m.name == "dv01") == 1


def test_zero_positions_empty_sensitivities():
    empty = Portfolio(id="e", name="empty", positions=[])
    assert SensitivityEngine().calculate(empty, pricing, market=MarketSnapshot(id="empty")) == []


def test_future_measures_raise():
    pos = EquityPosition(type="equity", id="e", symbol="ABC", quantity=1)
    market = equity_spot_market("ABC", 10.0)
    engine = SensitivityEngine()
    for name in sorted(FUTURE_MEASURES):
        with pytest.raises(NotImplementedError):
            engine.calculate_position(pos, pricing, measures=(name,), market=market)  # type: ignore[arg-type]


def test_unknown_measure_raises():
    pos = EquityPosition(type="equity", id="e", symbol="ABC", quantity=1)
    market = equity_spot_market("ABC", 10.0)
    with pytest.raises(ValueError, match="unknown"):
        SensitivityEngine().calculate_position(
            pos, pricing, measures=("theta",), market=market
        )  # type: ignore[arg-type]


def test_portfolio_delta_aggregates_like_sum_of_positions():
    """Invariant: portfolio cash delta for a symbol equals sum of position FD deltas."""
    engine = SensitivityEngine(spot_bump=0.01)
    portfolio = SAMPLE_PORTFOLIO
    port = {
        m.factor.key: m.value
        for m in engine.calculate(portfolio, pricing, measures=("delta",), market=SAMPLE_MARKET)
        if m.name == "delta"
    }
    by_symbol: dict[str, float] = {}
    for pos in portfolio.positions:
        for m in engine.calculate_position(
            pos, pricing, measures=("delta",), market=SAMPLE_MARKET
        ):
            by_symbol[m.factor.key] = by_symbol.get(m.factor.key, 0.0) + m.value
    for key, total in by_symbol.items():
        if key in port:
            _close(port[key], total, rel=1e-9, abs_tol=1e-4)
