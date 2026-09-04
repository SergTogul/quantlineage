"""R0.1.4 — one-trade FULL_REVALUATION golden.

Invariant (independent of Greeks):

    scenario P&L = shocked PV − base PV

Pinned on a unit equity so the identity is hand-computable:

    quantity=10, spot=100, shock −10% → shocked spot=90
    P&L = 10*90 − 10*100 = −100
"""
from __future__ import annotations
import numpy as np
import pytest
from app.domain.models import EquityPosition, EuropeanOptionPosition, MarketSnapshot, Portfolio, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine, full_revaluation_pnl_series
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.scenarios import historical_shocked_snapshots
from app.risk.var import VaRAnalytics

def _equity_book() -> tuple[Portfolio, MarketSnapshot]:
    pos = EquityPosition(type='equity', id='eq', symbol='UNIT', quantity=10.0)
    book = Portfolio(id='one', name='one', positions=[pos])
    market = MarketSnapshot(id='base', equity_spots={'UNIT': 100.0}, rates={'USD': 0.04})
    return (book, market)

def _dataset(equity_returns: np.ndarray) -> ArrayHistoricalDataset:
    z = np.zeros_like(equity_returns)
    return ArrayHistoricalDataset(FactorObservationSeries(equity_returns=np.asarray(equity_returns, dtype=float), vol_moves=z, rate_moves_bps=z, fx_returns=z))

def test_full_reval_pnl_equals_shocked_pv_minus_base_pv():
    book, market = _equity_book()
    pricing = BuiltinPricingEngine()
    dataset = _dataset(np.array([-0.1, 0.0, 0.05]))
    pnl = full_revaluation_pnl_series(book, pricing, market, dataset)
    base_pv = pricing.value(book.positions[0], market).market_value
    assert base_pv == pytest.approx(1000.0, abs=1e-12)
    shocked = historical_shocked_snapshots(market, dataset)
    expected = np.array([pricing.value(book.positions[0], snap).market_value - base_pv for snap in shocked], dtype=float)
    np.testing.assert_allclose(pnl, expected, atol=1e-12)
    np.testing.assert_allclose(pnl, np.array([-100.0, 0.0, 50.0]), atol=1e-12)

def test_full_reval_zero_shock_is_exact_zero():
    book, market = _equity_book()
    pricing = BuiltinPricingEngine()
    dataset = _dataset(np.zeros(4))
    pnl = full_revaluation_pnl_series(book, pricing, market, dataset)
    np.testing.assert_allclose(pnl, np.zeros(4), atol=1e-12)

def test_historical_engine_full_reval_is_not_the_linear_path():
    """ATM call: FULL P&L is shocked PV − base PV and diverges from LINEAR delta P&L."""
    pos = EuropeanOptionPosition(type='european_option', id='call', symbol='UNIT', quantity=10.0, strike=100.0, maturity_years=0.5, option_type='call')
    book = Portfolio(id='opt', name='opt', positions=[pos])
    market = MarketSnapshot(id='base', equity_spots={'UNIT': 100.0}, equity_vols={'UNIT': 0.25}, rates={'USD': 0.04}, dividend_yields={'UNIT': 0.0})
    pricing = BuiltinPricingEngine()
    dataset = _dataset(np.array([-0.2, 0.0, 0.15]))
    full_pnl = full_revaluation_pnl_series(book, pricing, market, dataset)
    base_pv = pricing.value(pos, market).market_value
    shocked = historical_shocked_snapshots(market, dataset)
    expected = np.array([pricing.value(pos, snap).market_value - base_pv for snap in shocked], dtype=float)
    np.testing.assert_allclose(full_pnl, expected, atol=1e-12)
    linear = HistoricalRiskEngine(dataset=dataset).calculate(book, pricing, methodology=VaRMethodology.LINEAR, market=market)
    full = HistoricalRiskEngine(dataset=dataset).calculate(book, pricing, methodology=VaRMethodology.FULL_REVALUATION, market=market)
    assert full['methodology'] == 'FULL_REVALUATION'
    assert abs(full['var_99'] - linear['var_99']) > 1e-06
    losses = -full_pnl
    assert full['var_99'] == pytest.approx(float(max(0.0, np.quantile(losses, 0.99))), abs=1e-12)

def test_var_analytics_full_reval_position_pnl_is_shocked_minus_base():
    book, market = _equity_book()
    pricing = BuiltinPricingEngine()
    dataset = _dataset(np.array([-0.1, 0.0, 0.05]))
    pos_pnl = VaRAnalytics(dataset=dataset)._full_reval_position_pnls(book, pricing, market)
    np.testing.assert_allclose(pos_pnl['eq'], np.array([-100.0, 0.0, 50.0]), atol=1e-12)
