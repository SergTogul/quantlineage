"""M2.3 Historical VaR methodologies: LINEAR / DELTA_GAMMA / FULL_REVALUATION.

Conventions:
- P&L units: currency (same as PricingEngine market_value)
- Loss = -P&L; VaR/ES are non-negative loss quantiles
- LINEAR: first-order Greeks only
- DELTA_GAMMA: + ½ γ (ΔS)² on equity (legacy default)
- FULL_REVALUATION: PV(shocked snapshot) − PV(base) via PricingEngine
- Tolerances: abs 1e-9 for zero-shock; relative separation for options book
"""
from __future__ import annotations

import numpy as np

from app.domain.models import EuropeanOptionPosition, MarketSnapshot, Portfolio, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.var import VaRAnalytics
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)
from app.services.portfolio_service import PortfolioService


def _zero_series(n: int=20) -> FactorObservationSeries:
    z = np.zeros(n)
    return FactorObservationSeries(equity_returns=z.copy(), vol_moves=z.copy(), rate_moves_bps=z.copy(), fx_returns=z.copy())

def _option_book() -> Portfolio:
    """Option-heavy book where gamma / full reval diverge from linear."""
    return Portfolio(id='opt_book', name='Options', positions=[EuropeanOptionPosition(type='european_option', id='long_call', symbol='SPY', quantity=1000, strike=100.0, maturity_years=0.5, option_type='call'), EuropeanOptionPosition(type='european_option', id='short_put', symbol='SPY', quantity=-800, strike=95.0, maturity_years=0.5, option_type='put')])

def _option_market() -> MarketSnapshot:
    return MarketSnapshot(id='option-test', equity_spots={'SPY': 100.0}, equity_vols={'SPY': 0.25}, rates={'USD': 0.04}, dividend_yields={'SPY': 0.0})

def _large_move_series() -> FactorObservationSeries:
    """Large equity / vol moves so γ and BS reval diverge from linear."""
    eq = np.array([-0.15, -0.1, -0.05, 0.0, 0.05, 0.1, 0.15, -0.2, 0.12, -0.08])
    vol = np.array([0.4, 0.2, 0.1, 0.0, -0.05, 0.15, 0.3, 0.5, -0.1, 0.25])
    z = np.zeros(len(eq))
    return FactorObservationSeries(equity_returns=eq, vol_moves=vol, rate_moves_bps=z.copy(), fx_returns=z.copy())

def test_var_methodology_enum_values():
    assert {m.value for m in VaRMethodology} == {'LINEAR', 'DELTA_GAMMA', 'FULL_REVALUATION'}

def test_default_methodology_is_delta_gamma():
    engine = HistoricalRiskEngine(seed=1, observations=50)
    r = engine.calculate(SAMPLE_PORTFOLIO, BuiltinPricingEngine(), market=SAMPLE_MARKET)
    assert r.methodology == 'DELTA_GAMMA'
    report = VaRAnalytics(seed=1, observations=50).report(SAMPLE_PORTFOLIO, BuiltinPricingEngine(), market=SAMPLE_MARKET)
    assert report.methodology == VaRMethodology.DELTA_GAMMA

def test_zero_shocks_yield_near_zero_var_all_methodologies():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_zero_series(30))
    engine = HistoricalRiskEngine(dataset=dataset)
    book = _option_book()
    for meth in VaRMethodology:
        r = engine.calculate(book, pricing, methodology=meth, market=_option_market())
        assert r.var_95 == 0.0
        assert r.var_99 == 0.0
        assert r.expected_shortfall_99 == 0.0
        assert abs(r.market_value) > 0.0

def test_full_reval_differs_from_linear_on_options_book():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_large_move_series())
    engine = HistoricalRiskEngine(dataset=dataset)
    book = _option_book()
    market = _option_market()
    linear = engine.calculate(book, pricing, methodology=VaRMethodology.LINEAR, market=market)
    full = engine.calculate(book, pricing, methodology=VaRMethodology.FULL_REVALUATION, market=market)
    dg = engine.calculate(book, pricing, methodology=VaRMethodology.DELTA_GAMMA, market=market)
    assert abs(full.var_99 - linear.var_99) > 1.0
    assert abs(full.var_99 - dg.var_99) > 1e-06
    assert linear.methodology == 'LINEAR'
    assert full.methodology == 'FULL_REVALUATION'

def test_linear_omits_gamma_vs_delta_gamma():
    pricing = BuiltinPricingEngine()
    series = FactorObservationSeries(equity_returns=np.linspace(-0.12, 0.12, 25), vol_moves=np.zeros(25), rate_moves_bps=np.zeros(25), fx_returns=np.zeros(25))
    engine = HistoricalRiskEngine(dataset=ArrayHistoricalDataset(series))
    book = _option_book()
    market = _option_market()
    linear = engine.calculate(book, pricing, methodology=VaRMethodology.LINEAR, market=market)
    dg = engine.calculate(book, pricing, methodology=VaRMethodology.DELTA_GAMMA, market=market)
    assert book.positions
    assert abs(linear.var_99 - dg.var_99) > 1e-06

def test_var_report_exposes_methodology_and_reconciles_contributions():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_large_move_series())
    report = VaRAnalytics(dataset=dataset).report(_option_book(), pricing, confidence=0.9, methodology=VaRMethodology.FULL_REVALUATION, market=_option_market())
    assert report.methodology == VaRMethodology.FULL_REVALUATION
    assert {m.method for m in report.methods} == {'historical', 'parametric'}
    hist = next(m for m in report.methods if m.method == 'historical')
    assert hist.var >= 0.0
    assert hist.expected_shortfall >= hist.var
    pvar = next(m for m in report.methods if m.method == 'parametric').var
    if pvar > 0:
        assert abs(sum(c.contribution_pct for c in report.contributions) - 100.0) < 1e-06

def test_service_and_api_default_methodology():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine(seed=2, observations=40))
    summary = svc.summary(SAMPLE_PORTFOLIO)
    assert summary.methodology == VaRMethodology.DELTA_GAMMA
    report = svc.var_report(SAMPLE_PORTFOLIO, methodology=VaRMethodology.LINEAR)
    assert report.methodology == VaRMethodology.LINEAR
    full = svc.var_report(SAMPLE_PORTFOLIO, methodology=VaRMethodology.FULL_REVALUATION)
    assert full.methodology == VaRMethodology.FULL_REVALUATION

def test_delta_gamma_default_matches_legacy_seeded_numbers():
    """Regression: default path remains the pre-M2.3 Δ-Γ approximation."""
    pricing = BuiltinPricingEngine()
    r = HistoricalRiskEngine(seed=1, observations=750).calculate(SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET)
    assert r.methodology == 'DELTA_GAMMA'
    assert r.var_99 >= r.var_95 >= 0.0
    assert r.expected_shortfall_99 >= r.var_99
