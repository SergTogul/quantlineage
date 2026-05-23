"""M2.5 Expected Shortfall contributions and reconciliation.

Conventions:
- Loss = -P&L (currency units); ES/VaR are non-negative loss measures
- Historical ES contribution = mean(entity loss | portfolio loss >= VaR)
- Linearity of conditional expectation ⇒ position/book/desk/strategy
  contributions sum to portfolio ES (within float tolerance)
- Risk-factor contributions under LINEAR / DELTA_GAMMA use additive Greek
  P&L terms; under FULL_REVALUATION reuse that split vs joint full-reval P&L
  plus an interaction residual
- Tolerances: abs 1e-6 (currency) or rel 1e-8 for reconciliation
"""
from __future__ import annotations

import math

import numpy as np
from tests.market_fixtures import equity_spots_market

from app.domain.models import (
    EquityPosition,
    EuropeanOptionPosition,
    MarketSnapshot,
    Portfolio,
    VaRMethodology,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.es import ESContributionAnalytics
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)

def _es_market():
    return equity_spots_market({'SPY': 100.0, 'NVDA': 100.0}, vols={'SPY': 0.25, 'NVDA': 0.4})

def _mixed_series(n: int=80) -> FactorObservationSeries:
    rng = np.random.default_rng(42)
    return FactorObservationSeries(equity_returns=rng.normal(-0.002, 0.02, n), vol_moves=rng.normal(0.0, 0.08, n), rate_moves_bps=rng.normal(0.0, 4.0, n), fx_returns=rng.normal(0.0, 0.008, n))

def _two_book_portfolio() -> Portfolio:
    return Portfolio(id='es-books', name='ES Books', desk='Macro Desk', strategy='Directional', positions=[EquityPosition(type='equity', id='eq-a', symbol='SPY', quantity=1000, book='Equity Cash'), EuropeanOptionPosition(type='european_option', id='opt-a', symbol='SPY', quantity=200, strike=100.0, maturity_years=0.5, option_type='call', book='Equity Derivatives'), EquityPosition(type='equity', id='eq-b', symbol='NVDA', quantity=500, book='Equity Cash')])

def _assert_reconciles(contributions, portfolio_es: float, *, abs_tol: float=1e-06) -> None:
    total = sum(c.component_es for c in contributions)
    assert math.isclose(total, portfolio_es, rel_tol=1e-08, abs_tol=abs_tol), f'contribution sum {total} vs portfolio ES {portfolio_es}'
    if portfolio_es > abs_tol:
        assert math.isclose(sum(c.contribution_pct for c in contributions), 100.0, abs_tol=1e-06)

def test_es_contributions_importable():
    assert ESContributionAnalytics is not None

def test_position_es_contributions_reconcile_delta_gamma():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_mixed_series())
    report = ESContributionAnalytics(dataset=dataset).report(SAMPLE_PORTFOLIO, pricing, confidence=0.95, methodology=VaRMethodology.DELTA_GAMMA, market=SAMPLE_MARKET)
    assert report.methodology == VaRMethodology.DELTA_GAMMA
    assert report.portfolio_es >= report.portfolio_var >= 0.0
    assert len(report.by_position) == len(SAMPLE_PORTFOLIO.positions)
    _assert_reconciles(report.by_position, report.portfolio_es)
    assert abs(report.reconciliation_error_position) < 1e-06

def test_book_desk_strategy_es_contributions_reconcile():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_mixed_series())
    book = _two_book_portfolio()
    report = ESContributionAnalytics(dataset=dataset).report(book, pricing, confidence=0.9, methodology=VaRMethodology.DELTA_GAMMA, market=_es_market())
    books = {c.key for c in report.by_book}
    assert books == {'Equity Cash', 'Equity Derivatives'}
    _assert_reconciles(report.by_book, report.portfolio_es)
    _assert_reconciles(report.by_desk, report.portfolio_es)
    _assert_reconciles(report.by_strategy, report.portfolio_es)
    assert report.by_desk[0].key == 'Macro Desk'
    assert report.by_strategy[0].key == 'Directional'
    cash_pos = sum(c.component_es for c in report.by_position if c.key in {'eq-a', 'eq-b'})
    cash_book = next(c.component_es for c in report.by_book if c.key == 'Equity Cash')
    assert math.isclose(cash_pos, cash_book, abs_tol=1e-09)

def test_risk_factor_es_contributions_reconcile_delta_gamma():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_mixed_series())
    report = ESContributionAnalytics(dataset=dataset).report(SAMPLE_PORTFOLIO, pricing, confidence=0.95, methodology=VaRMethodology.DELTA_GAMMA, market=SAMPLE_MARKET)
    keys = {c.key for c in report.by_risk_factor}
    assert {'equity', 'vol', 'rate', 'fx'} <= keys
    _assert_reconciles(report.by_risk_factor, report.portfolio_es)
    assert abs(report.reconciliation_error_risk_factor) < 1e-06

def test_full_revaluation_position_and_factor_es_reconcile():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_mixed_series(60))
    report = ESContributionAnalytics(dataset=dataset).report(SAMPLE_PORTFOLIO, pricing, confidence=0.9, methodology=VaRMethodology.FULL_REVALUATION, market=SAMPLE_MARKET)
    assert report.methodology == VaRMethodology.FULL_REVALUATION
    assert report.portfolio_es >= report.portfolio_var >= 0.0
    _assert_reconciles(report.by_position, report.portfolio_es)
    _assert_reconciles(report.by_book, report.portfolio_es)
    _assert_reconciles(report.by_risk_factor, report.portfolio_es)
    assert abs(report.reconciliation_error_risk_factor) < 1e-06

def test_zero_positions_yield_zero_es_contributions():
    pricing = BuiltinPricingEngine()
    empty = Portfolio(id='empty', name='Empty', positions=[])
    report = ESContributionAnalytics(dataset=ArrayHistoricalDataset(_mixed_series(20))).report(empty, pricing, confidence=0.99, methodology=VaRMethodology.DELTA_GAMMA, market=MarketSnapshot(id='empty'))
    assert report.portfolio_es == 0.0
    assert report.by_position == []
    assert report.by_book == []
    assert report.by_risk_factor == []

def test_tail_empty_when_flat_pnl_uses_var_as_es():
    """All-zero shocks → VaR=ES=0; contributions empty/zero."""
    z = np.zeros(25)
    series = FactorObservationSeries(equity_returns=z.copy(), vol_moves=z.copy(), rate_moves_bps=z.copy(), fx_returns=z.copy())
    pricing = BuiltinPricingEngine()
    report = ESContributionAnalytics(dataset=ArrayHistoricalDataset(series)).report(SAMPLE_PORTFOLIO, pricing, confidence=0.99, methodology=VaRMethodology.DELTA_GAMMA, market=SAMPLE_MARKET)
    assert report.portfolio_var == 0.0
    assert report.portfolio_es == 0.0
    assert all(c.component_es == 0.0 for c in report.by_position)

def test_var_report_includes_position_es_contributions():
    pricing = BuiltinPricingEngine()
    dataset = ArrayHistoricalDataset(_mixed_series())
    from app.risk.var import VaRAnalytics
    report = VaRAnalytics(dataset=dataset).report(SAMPLE_PORTFOLIO, pricing, confidence=0.95, methodology=VaRMethodology.DELTA_GAMMA, market=SAMPLE_MARKET)
    hist = next(m for m in report.methods if m.method == 'historical')
    es_sum = sum(c.component_es or 0.0 for c in report.contributions)
    assert math.isclose(es_sum, hist.expected_shortfall, rel_tol=1e-08, abs_tol=1e-06)

def test_service_exposes_es_contributions():
    from app.risk.historical import HistoricalRiskEngine
    from app.services.portfolio_service import PortfolioService
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine(seed=3, observations=80))
    report = svc.es_contributions(SAMPLE_PORTFOLIO, methodology=VaRMethodology.DELTA_GAMMA)
    assert report.portfolio_es >= 0.0
    _assert_reconciles(report.by_position, report.portfolio_es)

def test_es_api_endpoint_default_methodology():
    from fastapi.testclient import TestClient

    from app.main import app
    client = TestClient(app)
    portfolio = client.get('/portfolio').json()
    response = client.post('/risk/es', json=portfolio)
    assert response.status_code == 200
    payload = response.json()
    assert payload['methodology'] == 'DELTA_GAMMA'
    assert payload['portfolio_es'] >= 0.0
    assert payload['by_position']
    assert math.isclose(sum(c['component_es'] for c in payload['by_position']), payload['portfolio_es'], rel_tol=1e-08, abs_tol=1e-06)

def test_es_api_methodology_query_param():
    from fastapi.testclient import TestClient

    from app.main import app
    client = TestClient(app)
    portfolio = client.get('/portfolio').json()
    response = client.post('/risk/es?methodology=LINEAR', json=portfolio)
    assert response.status_code == 200
    assert response.json()['methodology'] == 'LINEAR'
