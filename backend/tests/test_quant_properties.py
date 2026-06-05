"""Hypothesis property-based quant correctness tests (M1.8).

Convention notes (BuiltinPricingEngine / Valuation):
- Equity option ``Valuation.delta`` is *cash delta*: quantity * unit_delta * spot.
  Unit delta is recovered as ``cash_delta / (quantity * spot)``.
  With dividends, call unit delta is in [0, exp(-qT)] ⊆ [0, 1];
  put unit delta is in [-exp(-qT), 0] ⊆ [-1, 0].
- European option premium is compared to discounted intrinsic (Black–Scholes bounds).
- ``pay_fixed=True`` is standard payer economics on both Builtin and QuantLib
  (PV rises when the market swap rate rises).
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from tests.market_fixtures import equity_spot_market, usd_rate_market

from app.domain.models import (
    BondPosition,
    EquityPosition,
    EuropeanOptionPosition,
    MarketSnapshot,
    Portfolio,
    StressScenario,
    SwapPosition,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.stress import StressEngine

engine = BuiltinPricingEngine()

# Keep examples modest for CI speed while still covering the property space.
_PROP = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


def _unit_delta(cash_delta: float, quantity: float, spot: float) -> float:
    return cash_delta / (quantity * spot)


def _discounted_intrinsic(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    option_type: str,
) -> float:
    forward_spot = spot * math.exp(-q * t)
    forward_strike = strike * math.exp(-r * t)
    if option_type == "call":
        return max(forward_spot - forward_strike, 0.0)
    return max(forward_strike - forward_spot, 0.0)


def _opt_market(spot: float, r: float, q: float, vol: float, symbol: str = "XYZ") -> MarketSnapshot:
    return equity_spot_market(symbol, spot, rate=r, dividend_yield=q, vol=vol)


positive_qty = st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False)
nonzero_qty = st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False).filter(
    lambda q: abs(q) >= 1.0
)
spot_s = st.floats(min_value=20.0, max_value=500.0, allow_nan=False, allow_infinity=False)
strike_s = st.floats(min_value=20.0, max_value=500.0, allow_nan=False, allow_infinity=False)
maturity_s = st.floats(min_value=0.05, max_value=3.0, allow_nan=False, allow_infinity=False)
vol_s = st.floats(min_value=0.05, max_value=0.80, allow_nan=False, allow_infinity=False)
rate_s = st.floats(min_value=-0.01, max_value=0.12, allow_nan=False, allow_infinity=False)
div_s = st.floats(min_value=0.0, max_value=0.08, allow_nan=False, allow_infinity=False)


@given(
    quantity=positive_qty,
    spot=spot_s,
    strike=strike_s,
    maturity=maturity_s,
    vol=vol_s,
    r=rate_s,
    q=div_s,
)
@_PROP
def test_call_unit_delta_in_0_1(quantity, spot, strike, maturity, vol, r, q):
    opt = EuropeanOptionPosition(
        type="european_option",
        id="call",
        symbol="XYZ",
        quantity=quantity,
        strike=strike,
        maturity_years=maturity,
        option_type="call",
    )
    v = engine.value(opt, _opt_market(spot, r, q, vol))
    unit = _unit_delta(v.delta, quantity, spot)
    assert 0.0 <= unit <= 1.0 + 1e-12


@given(
    quantity=positive_qty,
    spot=spot_s,
    strike=strike_s,
    maturity=maturity_s,
    vol=vol_s,
    r=rate_s,
    q=div_s,
)
@_PROP
def test_put_unit_delta_in_neg1_0(quantity, spot, strike, maturity, vol, r, q):
    opt = EuropeanOptionPosition(
        type="european_option",
        id="put",
        symbol="XYZ",
        quantity=quantity,
        strike=strike,
        maturity_years=maturity,
        option_type="put",
    )
    v = engine.value(opt, _opt_market(spot, r, q, vol))
    unit = _unit_delta(v.delta, quantity, spot)
    assert -1.0 - 1e-12 <= unit <= 0.0


@given(
    quantity=nonzero_qty,
    spot=spot_s,
    strike=strike_s,
    maturity=maturity_s,
    vol=vol_s,
    r=rate_s,
    q=div_s,
    option_type=st.sampled_from(["call", "put"]),
)
@_PROP
def test_european_option_price_ge_discounted_intrinsic(
    quantity, spot, strike, maturity, vol, r, q, option_type
):
    opt = EuropeanOptionPosition(
        type="european_option",
        id="opt",
        symbol="XYZ",
        quantity=quantity,
        strike=strike,
        maturity_years=maturity,
        option_type=option_type,
    )
    v = engine.value(opt, _opt_market(spot, r, q, vol))
    unit_price = v.market_value / quantity
    intrinsic = _discounted_intrinsic(spot, strike, maturity, r, q, option_type)
    # Small absolute slack for floating-point BS evaluation near deep OTM.
    assert unit_price + 1e-8 >= intrinsic


@given(
    face=st.floats(min_value=1_000.0, max_value=5_000_000.0, allow_nan=False, allow_infinity=False),
    qty=st.floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False),
    maturity=st.floats(min_value=0.5, max_value=30.0, allow_nan=False, allow_infinity=False),
    y_low=st.floats(min_value=-0.005, max_value=0.12, allow_nan=False, allow_infinity=False),
    y_bump=st.floats(min_value=1e-4, max_value=0.05, allow_nan=False, allow_infinity=False),
    duration=st.floats(min_value=0.25, max_value=25.0, allow_nan=False, allow_infinity=False),
)
@_PROP
def test_bond_price_decreases_when_yield_increases(face, qty, maturity, y_low, y_bump, duration):
    assume(1.0 + y_low > 0.0)
    assume(1.0 + y_low + y_bump > 0.0)
    bond = BondPosition(
        type="bond",
        id="b",
        issuer="UST",
        face_value=face,
        quantity=qty,
        maturity_years=maturity,
        duration=duration,
    )
    base_m = usd_rate_market(y_low)
    higher_m = usd_rate_market(y_low + y_bump)
    assert engine.value(bond, higher_m).market_value < engine.value(bond, base_m).market_value


@given(
    notional=st.floats(min_value=100_000.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False),
    maturity=st.floats(min_value=1.0, max_value=30.0, allow_nan=False, allow_infinity=False),
    fixed=st.floats(min_value=0.0, max_value=0.12, allow_nan=False, allow_infinity=False),
    m_low=st.floats(min_value=0.0, max_value=0.12, allow_nan=False, allow_infinity=False),
    m_bump=st.floats(min_value=1e-4, max_value=0.03, allow_nan=False, allow_infinity=False),
    duration=st.floats(min_value=0.5, max_value=20.0, allow_nan=False, allow_infinity=False),
)
@_PROP
def test_payer_economics_swap_pv_increases_when_rates_rise(
    notional, maturity, fixed, m_low, m_bump, duration
):
    """Payer economics: pay_fixed=True → PV rises when the market swap rate rises."""
    swap = SwapPosition(
        type="swap",
        id="s",
        notional=notional,
        maturity_years=maturity,
        fixed_rate=fixed,
        pay_fixed=True,
        duration=duration,
    )
    base_m = usd_rate_market(m_low)
    higher_m = usd_rate_market(m_low + m_bump)
    assert engine.value(swap, higher_m).market_value > engine.value(swap, base_m).market_value


@given(
    n_equities=st.integers(min_value=1, max_value=5),
    data=st.data(),
)
@_PROP
def test_portfolio_pv_equals_sum_of_trade_pvs(n_equities, data):
    positions = []
    equity_spots: dict[str, float] = {}
    for i in range(n_equities):
        qty = data.draw(st.floats(min_value=-200.0, max_value=200.0).filter(lambda q: abs(q) >= 1.0))
        price = data.draw(st.floats(min_value=5.0, max_value=800.0, allow_nan=False, allow_infinity=False))
        symbol = f"S{i}"
        equity_spots[symbol] = price
        positions.append(
            EquityPosition(type="equity", id=f"eq-{i}", symbol=symbol, quantity=qty)
        )
    y = data.draw(st.floats(min_value=0.01, max_value=0.08))
    positions.append(
        BondPosition(
            type="bond",
            id="bond-0",
            issuer="UST",
            face_value=data.draw(st.floats(min_value=10_000.0, max_value=1_000_000.0)),
            quantity=1.0,
            maturity_years=data.draw(st.floats(min_value=1.0, max_value=10.0)),
            duration=data.draw(st.floats(min_value=0.5, max_value=9.0)),
        )
    )
    portfolio = Portfolio(id="prop", name="prop", positions=positions)
    market = MarketSnapshot(
        id="prop-mkt",
        equity_spots=equity_spots,
        rates={"USD": y},
    )
    vals = engine.value_portfolio(portfolio, market)
    assert len(vals) == len(positions)
    assert sum(v.market_value for v in vals) == pytest.approx(
        sum(engine.value(p, market).market_value for p in positions), abs=1e-9, rel=0
    )


@given(
    quantity=st.floats(min_value=10.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    price=st.floats(min_value=20.0, max_value=400.0, allow_nan=False, allow_infinity=False),
)
@_PROP
def test_zero_shock_produces_zero_stress_pnl(quantity, price):
    portfolio = Portfolio(
        id="zero-shock",
        name="zero-shock",
        positions=[
            EquityPosition(type="equity", id="eq", symbol="ABC", quantity=quantity),
            EuropeanOptionPosition(
                type="european_option",
                id="opt",
                symbol="ABC",
                quantity=quantity,
                strike=price,
                maturity_years=1.0,
                option_type="call",
            ),
        ],
    )
    market = MarketSnapshot(
        id="zero-mkt",
        equity_spots={"ABC": price},
        equity_vols={"ABC": 0.2},
        rates={"USD": 0.03},
        dividend_yields={"ABC": 0.0},
    )
    zero = StressScenario(
        id="zero",
        name="Zero Shock",
        equity_shock=0.0,
        vol_shock=0.0,
        rates_shift_bps=0.0,
        fx_shock=0.0,
    )
    results = StressEngine().run(portfolio, engine, [zero], market=market)
    assert len(results) == 1
    assert results[0].pnl == pytest.approx(0.0, abs=1e-9)
    assert all(pnl == pytest.approx(0.0, abs=1e-9) for pnl in results[0].by_position.values())


def test_empty_portfolio_has_zero_aggregate_risk():
    empty = Portfolio(id="empty", name="empty", positions=[])
    r = HistoricalRiskEngine(seed=1).calculate(
        empty, engine, market=MarketSnapshot(id="empty")
    )
    for key in (
        "market_value",
        "delta",
        "gamma",
        "vega",
        "dv01",
        "fx_delta",
        "var_95",
        "var_99",
        "expected_shortfall_99",
    ):
        assert getattr(r, key) == 0.0


# FD-stable domain: near-ATM, not-too-short T, not-too-low vol.
# Encode bounds in strategies (not assume()) so Hypothesis does not filter_too_much.
_fd_moneyness = st.floats(min_value=0.75, max_value=1.35, allow_nan=False, allow_infinity=False)
_fd_maturity = st.floats(min_value=0.25, max_value=3.0, allow_nan=False, allow_infinity=False)
_fd_vol = st.floats(min_value=0.12, max_value=0.80, allow_nan=False, allow_infinity=False)


@given(
    quantity=nonzero_qty,
    strike=strike_s,
    moneyness=_fd_moneyness,
    maturity=_fd_maturity,
    vol=_fd_vol,
    r=rate_s,
    q=div_s,
    option_type=st.sampled_from(["call", "put"]),
)
@_PROP
def test_option_cash_greeks_match_finite_difference(
    quantity, strike, moneyness, maturity, vol, r, q, option_type
):
    """Cash delta/gamma/vega reconcile to central finite differences.

    cash_delta ≈ S * ∂PV/∂S; cash_gamma ≈ S² * ∂²PV/∂S²;
    vega is PV change for +1 absolute vol point (0.01), matching Valuation.vega.

    Domain is restricted to moneyness ∈ [0.75, 1.35], T ≥ 0.25, σ ≥ 0.12 so
    central FD with relative spot bump 1e-4 and vol bump 1e-4 stays numerically
    stable; deep OTM / short-dated / low-vol cases are covered by sign/bound
    properties elsewhere, not by second-difference reconciliation.
    """
    spot = strike * moneyness
    opt = EuropeanOptionPosition(
        type="european_option",
        id="fd",
        symbol="XYZ",
        quantity=quantity,
        strike=strike,
        maturity_years=maturity,
        option_type=option_type,
    )
    market = _opt_market(spot, r, q, vol)
    v = engine.value(opt, market)
    h = spot * 1e-4
    pv0 = v.market_value
    pv_up = engine.value(opt, _opt_market(spot + h, r, q, vol)).market_value
    pv_dn = engine.value(opt, _opt_market(spot - h, r, q, vol)).market_value
    cash_delta_fd = spot * (pv_up - pv_dn) / (2.0 * h)
    cash_gamma_fd = (spot * spot) * (pv_up - 2.0 * pv0 + pv_dn) / (h * h)
    assert cash_delta_fd == pytest.approx(v.delta, rel=5e-3, abs=1e-2)
    assert cash_gamma_fd == pytest.approx(v.gamma, rel=2e-2, abs=1e-1)

    # Central FD on vol, scaled to one absolute vol point (matches Valuation.vega).
    vol_h = 1e-4
    pv_vol_up = engine.value(opt, _opt_market(spot, r, q, vol + vol_h)).market_value
    pv_vol_dn = engine.value(opt, _opt_market(spot, r, q, vol - vol_h)).market_value
    vega_fd = (pv_vol_up - pv_vol_dn) / (2.0 * vol_h) * 0.01
    assert vega_fd == pytest.approx(v.vega, rel=5e-3, abs=1e-2)
