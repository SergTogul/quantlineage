"""M4.3 P&L Explain v2 — Greek / trade-flow attribution between two states.

Conventions (currency units; positive = gain):
- actual P&L = PV(current, current_mkt) − PV(previous, previous_mkt)
- Market bridge on previous book: Taylor (delta/gamma/vega/rates/FX/theta)
- Trade flow: new trades / closed trades (incl. size changes on continuing IDs)
- explained = sum(items); residual = actual − explained
- Identical state → zero actual / residual / drivers
- Tolerances: abs 1e-6 (exact paths); Taylor residual abs 1% of |market move| or 1.0
"""
from __future__ import annotations
import math
from app.domain.models import AttributionRequest, EquityPosition, EuropeanOptionPosition, MarketSnapshot, Portfolio
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.attribution import DRIVER_CLOSED, DRIVER_DELTA, DRIVER_FX, DRIVER_GAMMA, DRIVER_NEW, DRIVER_RATES, DRIVER_THETA, DRIVER_VEGA, AttributionEngine
from app.risk.historical import HistoricalRiskEngine
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService
pricing = BuiltinPricingEngine()
engine = AttributionEngine()

def _pv(portfolio: Portfolio, market: MarketSnapshot) -> float:
    return sum((v.market_value for v in pricing.value_portfolio(portfolio, market)))

def _by_driver(report) -> dict[str, float]:
    return {i.driver: i.pnl for i in report.items}

def _assert_reconciles(report, *, abs_tol: float=1e-06) -> None:
    explained = sum((i.pnl for i in report.items))
    assert math.isclose(explained, report.explained_change, abs_tol=abs_tol, rel_tol=1e-08)
    assert math.isclose(report.explained_change + report.residual, report.total_change, abs_tol=abs_tol, rel_tol=1e-08)
    assert math.isclose(report.total_change, report.current_market_value - report.base_market_value, abs_tol=abs_tol, rel_tol=1e-08)

def test_identical_state_zero_attribution():
    pm = MarketSnapshot(id='t0', equity_spots={'SPY': 100.0}, equity_vols={}, fx_spots={}, fx_vols={}, rates={'USD': 0.04})
    book = Portfolio(id='p', name='p', positions=[EquityPosition(type='equity', id='e', symbol='SPY', quantity=10)])
    report = engine.explain(AttributionRequest(previous_portfolio=book, current_portfolio=book, previous_market=pm, current_market=pm), pricing)
    assert abs(report.total_change) < 1e-12
    assert abs(report.residual) < 1e-12
    assert abs(report.explained_change) < 1e-12
    for item in report.items:
        assert abs(item.pnl) < 1e-12
    _assert_reconciles(report)

def test_equity_spot_move_explained_by_delta():
    prev = MarketSnapshot(id='t0', equity_spots={'ABC': 100.0}, rates={'USD': 0.04})
    curr = prev.model_copy(update={'id': 't1', 'equity_spots': {'ABC': 101.0}})
    book = Portfolio(id='p', name='p', positions=[EquityPosition(type='equity', id='e', symbol='ABC', quantity=100)])
    report = engine.explain(AttributionRequest(previous_portfolio=book, current_portfolio=book, previous_market=prev, current_market=curr), pricing)
    drivers = _by_driver(report)
    assert math.isclose(drivers[DRIVER_DELTA], 100.0, abs_tol=1e-09)
    assert abs(drivers.get(DRIVER_GAMMA, 0.0)) < 1e-12
    assert abs(report.residual) < 1e-09
    assert math.isclose(report.total_change, 100.0, abs_tol=1e-09)
    _assert_reconciles(report)

def test_option_spot_move_has_delta_and_gamma():
    prev = MarketSnapshot(id='t0', equity_spots={'XYZ': 100.0}, equity_vols={'XYZ': 0.2}, rates={'USD': 0.03}, dividend_yields={'XYZ': 0.0})
    curr = prev.model_copy(update={'id': 't1', 'equity_spots': {'XYZ': 105.0}})
    book = Portfolio(id='p', name='p', positions=[EuropeanOptionPosition(type='european_option', id='o', symbol='XYZ', quantity=10, strike=100.0, maturity_years=1.0, option_type='call')])
    report = engine.explain(AttributionRequest(previous_portfolio=book, current_portfolio=book, previous_market=prev, current_market=curr), pricing)
    drivers = _by_driver(report)
    assert drivers[DRIVER_DELTA] != 0.0
    assert drivers[DRIVER_GAMMA] > 0.0
    market_move = _pv(book, curr) - _pv(book, prev)
    assert math.isclose(report.total_change, market_move, abs_tol=1e-09)
    assert abs(report.residual) <= max(1.0, 0.05 * abs(market_move))
    _assert_reconciles(report)

def test_vol_move_explained_by_vega():
    prev = MarketSnapshot(id='t0', equity_spots={'XYZ': 100.0}, equity_vols={'XYZ': 0.2}, rates={'USD': 0.03}, dividend_yields={'XYZ': 0.0})
    curr = prev.model_copy(update={'id': 't1', 'equity_vols': {'XYZ': 0.22}})
    book = Portfolio(id='p', name='p', positions=[EuropeanOptionPosition(type='european_option', id='o', symbol='XYZ', quantity=10, strike=100.0, maturity_years=1.0, option_type='call')])
    report = engine.explain(AttributionRequest(previous_portfolio=book, current_portfolio=book, previous_market=prev, current_market=curr), pricing)
    drivers = _by_driver(report)
    assert drivers[DRIVER_VEGA] > 0.0
    assert abs(drivers.get(DRIVER_DELTA, 0.0)) < 1e-09
    assert abs(report.residual) <= max(0.5, 0.02 * abs(report.total_change))
    _assert_reconciles(report)

def test_rate_move_explained_by_rates_bucket():
    from app.domain.models import BondPosition
    prev = MarketSnapshot(id='t0', rates={'USD': 0.04})
    curr = prev.model_copy(update={'id': 't1', 'rates': {'USD': 0.041}})
    book = Portfolio(id='p', name='p', positions=[BondPosition(type='bond', id='b', issuer='UST', face_value=1000000, quantity=1, maturity_years=10.0, duration=8.0)])
    report = engine.explain(AttributionRequest(previous_portfolio=book, current_portfolio=book, previous_market=prev, current_market=curr), pricing)
    drivers = _by_driver(report)
    assert drivers[DRIVER_RATES] < 0.0
    assert abs(drivers[DRIVER_RATES]) > 0.5 * abs(report.total_change)
    _assert_reconciles(report)

def test_fx_move_explained_by_fx_bucket():
    from app.domain.models import FXForwardPosition
    prev = MarketSnapshot(id='t0', fx_spots={'EURUSD': 1.1}, rates={'USD': 0.04, 'EUR': 0.03})
    curr = prev.model_copy(update={'id': 't1', 'fx_spots': {'EURUSD': 1.111}})
    book = Portfolio(id='p', name='p', positions=[FXForwardPosition(type='fx_forward', id='f', pair='EURUSD', notional_base=1000000, strike=1.1, maturity_years=0.5)])
    report = engine.explain(AttributionRequest(previous_portfolio=book, current_portfolio=book, previous_market=prev, current_market=curr), pricing)
    drivers = _by_driver(report)
    assert drivers[DRIVER_FX] != 0.0
    _assert_reconciles(report)

def test_theta_from_dt_years():
    prev = MarketSnapshot(id='t0', as_of='2026-01-01', equity_spots={'XYZ': 100.0}, equity_vols={'XYZ': 0.2}, rates={'USD': 0.03}, dividend_yields={'XYZ': 0.0})
    curr = prev.model_copy(update={'id': 't1', 'as_of': '2026-01-02'})
    book = Portfolio(id='p', name='p', positions=[EuropeanOptionPosition(type='european_option', id='o', symbol='XYZ', quantity=10, strike=100.0, maturity_years=1.0, option_type='call')])
    report = engine.explain(AttributionRequest(previous_portfolio=book, current_portfolio=book, previous_market=prev, current_market=curr, dt_years=1.0 / 365.0), pricing)
    drivers = _by_driver(report)
    assert drivers[DRIVER_THETA] != 0.0
    _assert_reconciles(report)

def test_new_and_closed_trades():
    mkt = MarketSnapshot(id='m', equity_spots={'A': 50.0, 'B': 80.0}, rates={'USD': 0.04})
    prev = Portfolio(id='p', name='p', positions=[EquityPosition(type='equity', id='keep', symbol='A', quantity=10), EquityPosition(type='equity', id='gone', symbol='B', quantity=5)])
    curr = Portfolio(id='p', name='p', positions=[EquityPosition(type='equity', id='keep', symbol='A', quantity=10), EquityPosition(type='equity', id='fresh', symbol='B', quantity=2)])
    report = engine.explain(AttributionRequest(previous_portfolio=prev, current_portfolio=curr, previous_market=mkt, current_market=mkt), pricing)
    drivers = _by_driver(report)
    assert math.isclose(drivers[DRIVER_CLOSED], -5 * 80.0, abs_tol=1e-09)
    assert math.isclose(drivers[DRIVER_NEW], 2 * 80.0, abs_tol=1e-09)
    assert abs(report.residual) < 1e-09
    _assert_reconciles(report)

def test_quantity_increase_is_new_trades():
    mkt = MarketSnapshot(id='m', equity_spots={'A': 40.0}, rates={'USD': 0.04})
    prev = Portfolio(id='p', name='p', positions=[EquityPosition(type='equity', id='e', symbol='A', quantity=10)])
    curr = Portfolio(id='p', name='p', positions=[EquityPosition(type='equity', id='e', symbol='A', quantity=15)])
    report = engine.explain(AttributionRequest(previous_portfolio=prev, current_portfolio=curr, previous_market=mkt, current_market=mkt), pricing)
    drivers = _by_driver(report)
    assert math.isclose(drivers[DRIVER_NEW], 5 * 40.0, abs_tol=1e-09)
    assert abs(drivers.get(DRIVER_CLOSED, 0.0)) < 1e-12
    assert abs(report.residual) < 1e-09
    _assert_reconciles(report)

def test_sample_demo_reconciles():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    report = svc.demo_attribution(SAMPLE_PORTFOLIO)
    assert report.total_change != 0.0
    assert DRIVER_DELTA in _by_driver(report)
    _assert_reconciles(report, abs_tol=1e-06)
    assert abs(report.residual) <= max(50.0, 0.15 * abs(report.total_change))

def test_required_drivers_present():
    report = engine.explain(AttributionRequest(previous_portfolio=SAMPLE_PORTFOLIO, current_portfolio=SAMPLE_PORTFOLIO), pricing)
    names = {i.driver for i in report.items}
    for required in (DRIVER_DELTA, DRIVER_GAMMA, DRIVER_VEGA, DRIVER_RATES, DRIVER_FX, DRIVER_THETA, DRIVER_NEW, DRIVER_CLOSED):
        assert required in names
