"""M2.6 Component VaR — Euler allocation of parametric VaR; reconciliation.

Methodology (documented in app.risk.var / app.risk.marginal_var):
- Position P&L series X_i from LINEAR | DELTA_GAMMA | FULL_REVALUATION
- Portfolio P&L X = Σ X_i; σ = sample std(X); VaR_param = z_α · σ (floored at 0)
- Component VaR_i = VaR_param · Cov(X_i, X) / Var(X)   (Euler / covariance allocation)
- Σ Component VaR_i = VaR_param (homogeneous degree-1 risk measure)

Conventions:
- Units: currency (same as PricingEngine market_value / P&L)
- Sign: Component VaR may be negative for hedges; abs used for ranking only
- contribution_pct = Component_i / VaR_param · 100; sums to 100 when VaR_param > 0
- Tolerances: abs 1e-6 currency or rel 1e-8 for reconciliation
"""

from __future__ import annotations

import math

import numpy as np

from app.domain.models import (
    EquityPosition,
    EuropeanOptionPosition,
    MarketSnapshot,
    Portfolio,
    VaRMethodology,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.var import VaRAnalytics
from app.sample import SAMPLE_PORTFOLIO


def _mixed_series(n: int = 100) -> FactorObservationSeries:
    rng = np.random.default_rng(7)
    return FactorObservationSeries(
        equity_returns=rng.normal(-0.001, 0.018, n),
        vol_moves=rng.normal(0.0, 0.07, n),
        rate_moves_bps=rng.normal(0.0, 3.5, n),
        fx_returns=rng.normal(0.0, 0.007, n),
    )


def _option_equity_book() -> Portfolio:
    return Portfolio(
        id="cvar_book",
        name="Component VaR Book",
        positions=[
            EquityPosition(
                type="equity",
                id="eq-long",
                symbol="SPY",
                quantity=500,
                price=100.0,
                sector="ETF",
            ),
            EuropeanOptionPosition(
                type="european_option",
                id="call-hedge",
                symbol="SPY",
                quantity=-200,
                spot=100.0,
                strike=100.0,
                maturity_years=0.5,
                volatility=0.25,
                risk_free_rate=0.04,
                option_type="call",
            ),
            EuropeanOptionPosition(
                type="european_option",
                id="put-long",
                symbol="SPY",
                quantity=300,
                spot=100.0,
                strike=95.0,
                maturity_years=0.5,
                volatility=0.28,
                risk_free_rate=0.04,
                option_type="put",
            ),
        ],
    )


def _option_market() -> MarketSnapshot:
    return MarketSnapshot(
        id="component-var",
        equity_spots={"SPY": 100.0},
        equity_vols={"SPY": 0.25},
        rates={"USD": 0.04},
    )


def _parametric_var(report) -> float:
    return next(m.var for m in report.methods if m.method == "parametric")


def test_component_var_reconciles_under_delta_gamma():
    pricing = BuiltinPricingEngine()
    analytics = VaRAnalytics(dataset=ArrayHistoricalDataset(_mixed_series()))
    report = analytics.report(
        _option_equity_book(),
        pricing,
        confidence=0.99,
        methodology=VaRMethodology.DELTA_GAMMA,
        market=_option_market(),
    )
    pvar = _parametric_var(report)
    assert pvar > 0
    total = sum(c.component_var for c in report.contributions)
    assert math.isclose(total, pvar, rel_tol=1e-8, abs_tol=1e-6)
    assert math.isclose(sum(c.contribution_pct for c in report.contributions), 100.0, abs_tol=1e-6)


def test_component_var_reconciles_under_full_revaluation():
    pricing = BuiltinPricingEngine()
    analytics = VaRAnalytics(dataset=ArrayHistoricalDataset(_mixed_series()))
    report = analytics.report(
        _option_equity_book(),
        pricing,
        confidence=0.95,
        methodology=VaRMethodology.FULL_REVALUATION,
        market=_option_market(),
    )
    pvar = _parametric_var(report)
    assert pvar > 0
    total = sum(c.component_var for c in report.contributions)
    assert math.isclose(total, pvar, rel_tol=1e-8, abs_tol=1e-6)
    assert report.methodology == VaRMethodology.FULL_REVALUATION


def test_component_var_reconciles_sample_portfolio_both_methodologies():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_mixed_series(120))
    for meth in (VaRMethodology.DELTA_GAMMA, VaRMethodology.FULL_REVALUATION):
        report = VaRAnalytics(dataset=dataset).report(
            SAMPLE_PORTFOLIO, pricing, confidence=0.99, methodology=meth
        )
        pvar = _parametric_var(report)
        assert len(report.contributions) == len(SAMPLE_PORTFOLIO.positions)
        assert math.isclose(
            sum(c.component_var for c in report.contributions),
            pvar,
            rel_tol=1e-8,
            abs_tol=1e-6,
        )


def test_single_position_component_equals_portfolio_parametric_var():
    pricing = BuiltinPricingEngine()
    book = Portfolio(
        id="solo",
        name="Solo",
        positions=[
            EquityPosition(
                type="equity",
                id="only",
                symbol="SPY",
                quantity=1000,
                price=100.0,
            )
        ],
    )
    report = VaRAnalytics(dataset=ArrayHistoricalDataset(_mixed_series())).report(
        book, pricing, methodology=VaRMethodology.DELTA_GAMMA
    )
    pvar = _parametric_var(report)
    assert len(report.contributions) == 1
    assert math.isclose(report.contributions[0].component_var, pvar, rel_tol=1e-8, abs_tol=1e-6)
    assert math.isclose(report.contributions[0].contribution_pct, 100.0, abs_tol=1e-9)


def test_zero_shock_series_yields_zero_component_var():
    z = np.zeros(40)
    series = FactorObservationSeries(
        equity_returns=z.copy(),
        vol_moves=z.copy(),
        rate_moves_bps=z.copy(),
        fx_returns=z.copy(),
    )
    report = VaRAnalytics(dataset=ArrayHistoricalDataset(series)).report(
        _option_equity_book(),
        BuiltinPricingEngine(),
        methodology=VaRMethodology.DELTA_GAMMA,
        market=_option_market(),
    )
    assert _parametric_var(report) == 0.0
    assert all(c.component_var == 0.0 for c in report.contributions)
    assert all(c.contribution_pct == 0.0 for c in report.contributions)
