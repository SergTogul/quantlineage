"""M9.3 / M9.5 — Hypothesis portfolio-risk and stress invariants (beyond pricing Greeks).

Properties (deterministic engines; no invented risk math in assertions beyond
engine output comparisons):

M9.3 portfolio / VaR
- HistoricalRiskEngine: ES99 ≥ VaR99 ≥ VaR95 ≥ 0
- market_value aggregates to sum of position valuations
- Component VaR (Euler) reconciles to parametric VaR under DELTA_GAMMA

M9.5 stress
- StressEngine.run: portfolio pnl == sum(by_position)
- empty scenario list → empty results
- long equity book: more negative equity shock ⇒ weakly more negative (or equal) pnl

Tolerances: abs 1e-9 currency for exact aggregations; abs 1e-6 / rel 1e-8 for
component VaR (same as test_component_var.py).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.domain.models import (
    EquityPosition,
    EuropeanOptionPosition,
    Portfolio,
    StressScenario,
    VaRMethodology,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.stress import StressEngine
from app.risk.var import VaRAnalytics

pricing = BuiltinPricingEngine()
stress = StressEngine()

_PROP = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

_qty = st.floats(min_value=10.0, max_value=400.0, allow_nan=False, allow_infinity=False)
_price = st.floats(min_value=20.0, max_value=400.0, allow_nan=False, allow_infinity=False)
_eq_shock = st.floats(min_value=-0.40, max_value=-0.01, allow_nan=False, allow_infinity=False)


def _equity_book(n: int, data: st.DataObject) -> Portfolio:
    positions = []
    for i in range(n):
        positions.append(
            EquityPosition(
                type="equity",
                id=f"eq-{i}",
                symbol=f"S{i}",
                quantity=data.draw(_qty),
                price=data.draw(_price),
            )
        )
    return Portfolio(id="m9-prop", name="m9-prop", positions=positions)


def _mixed_series(n: int = 80, seed: int = 11) -> FactorObservationSeries:
    rng = np.random.default_rng(seed)
    return FactorObservationSeries(
        equity_returns=rng.normal(-0.001, 0.02, n),
        vol_moves=rng.normal(0.0, 0.06, n),
        rate_moves_bps=rng.normal(0.0, 4.0, n),
        fx_returns=rng.normal(0.0, 0.008, n),
    )


def _parametric_var(report) -> float:
    return next(m.var for m in report.methods if m.method == "parametric")


@given(n=st.integers(min_value=1, max_value=4), data=st.data(), seed=st.integers(1, 50))
@_PROP
def test_var_es_ordering_nonnegative(n, data, seed):
    """M9.3: ES99 ≥ VaR99 ≥ VaR95 ≥ 0 for random long-equity books."""
    book = _equity_book(n, data)
    r = HistoricalRiskEngine(seed=seed, observations=60).calculate(book, pricing)
    assert r["var_95"] >= 0.0
    assert r["var_99"] >= r["var_95"]
    assert r["expected_shortfall_99"] >= r["var_99"]


@given(n=st.integers(min_value=1, max_value=5), data=st.data())
@_PROP
def test_risk_market_value_equals_sum_of_position_mvs(n, data):
    """M9.3: HistoricalRiskEngine market_value == Σ position valuations."""
    book = _equity_book(n, data)
    r = HistoricalRiskEngine(seed=3, observations=40).calculate(book, pricing)
    expected = sum(v.market_value for v in pricing.value_portfolio(book))
    assert r["market_value"] == pytest.approx(expected, abs=1e-9)


@given(
    qty_eq=_qty,
    price=_price,
    qty_opt=st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False).filter(
        lambda q: abs(q) >= 5.0
    ),
    strike_mult=st.floats(min_value=0.85, max_value=1.15, allow_nan=False, allow_infinity=False),
    vol=st.floats(min_value=0.15, max_value=0.45, allow_nan=False, allow_infinity=False),
)
@_PROP
def test_component_var_reconciles_random_equity_option_book(qty_eq, price, qty_opt, strike_mult, vol):
    """M9.3: Σ component VaR == parametric VaR (DELTA_GAMMA Euler allocation)."""
    book = Portfolio(
        id="cvar-prop",
        name="cvar-prop",
        positions=[
            EquityPosition(type="equity", id="eq", symbol="SPY", quantity=qty_eq, price=price),
            EuropeanOptionPosition(
                type="european_option",
                id="opt",
                symbol="SPY",
                quantity=qty_opt,
                spot=price,
                strike=price * strike_mult,
                maturity_years=0.5,
                volatility=vol,
                risk_free_rate=0.03,
                option_type="call",
            ),
        ],
    )
    report = VaRAnalytics(dataset=ArrayHistoricalDataset(_mixed_series())).report(
        book, pricing, confidence=0.99, methodology=VaRMethodology.DELTA_GAMMA
    )
    pvar = _parametric_var(report)
    total = sum(c.component_var for c in report.contributions)
    assert math.isclose(total, pvar, rel_tol=1e-8, abs_tol=1e-6)
    if pvar > 1e-9:
        assert math.isclose(sum(c.contribution_pct for c in report.contributions), 100.0, abs_tol=1e-6)


@given(n=st.integers(min_value=1, max_value=4), data=st.data(), equity_shock=_eq_shock)
@_PROP
def test_stress_pnl_equals_sum_of_position_pnls(n, data, equity_shock):
    """M9.5: StressResult.pnl == sum(by_position.values())."""
    book = _equity_book(n, data)
    scenario = StressScenario(
        id="eq-shock",
        name="Equity shock",
        equity_shock=equity_shock,
        vol_shock=0.0,
        rates_shift_bps=0.0,
        fx_shock=0.0,
    )
    results = stress.run(book, pricing, [scenario])
    assert len(results) == 1
    assert results[0].pnl == pytest.approx(sum(results[0].by_position.values()), abs=1e-9)


@given(n=st.integers(min_value=0, max_value=3), data=st.data())
@_PROP
def test_empty_stress_scenario_list_returns_empty(n, data):
    """M9.5: no scenarios → no stress results (empty portfolio allowed)."""
    book = _equity_book(n, data) if n else Portfolio(id="empty", name="empty", positions=[])
    assert stress.run(book, pricing, []) == []


@given(
    qty=_qty,
    price=_price,
    shock_a=_eq_shock,
    shock_b=_eq_shock,
)
@_PROP
def test_long_equity_stress_pnl_monotone_in_equity_shock(qty, price, shock_a, shock_b):
    """M9.5: for long equity, more negative equity_shock ⇒ weakly worse (≤) pnl."""
    book = Portfolio(
        id="long-eq",
        name="long-eq",
        positions=[EquityPosition(type="equity", id="eq", symbol="ABC", quantity=qty, price=price)],
    )
    sa = StressScenario(id="a", name="a", equity_shock=shock_a)
    sb = StressScenario(id="b", name="b", equity_shock=shock_b)
    ra = stress.run(book, pricing, [sa])[0].pnl
    rb = stress.run(book, pricing, [sb])[0].pnl
    if shock_a <= shock_b:
        assert ra <= rb + 1e-9
    else:
        assert rb <= ra + 1e-9
