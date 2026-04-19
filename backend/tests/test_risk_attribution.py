"""M4.4 risk-change attribution invariants and driver tests."""
from __future__ import annotations
from app.domain.models import EquityPosition, Portfolio, RiskChangeAttributionRequest, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.risk_attribution import RiskChangeAttributionEngine
from app.sample import SAMPLE_PORTFOLIO, DemoPortfolioMarketDataProvider, demo_market_snapshot
from app.services.portfolio_service import PortfolioService
_ABS_TOL = 1e-06
_REL_TOL = 1e-08

def _engine(seed: int=1, observations: int=80) -> RiskChangeAttributionEngine:
    return RiskChangeAttributionEngine(risk_engine=HistoricalRiskEngine(seed=seed, observations=observations), market_data=DemoPortfolioMarketDataProvider())

def test_identical_state_zero_change():
    """Invariant: identical portfolio + market → zero Δ risk and ~zero drivers."""
    pricing = BuiltinPricingEngine()
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    report = _engine().explain(RiskChangeAttributionRequest(previous_portfolio=SAMPLE_PORTFOLIO, current_portfolio=SAMPLE_PORTFOLIO, previous_market=market, current_market=market), pricing)
    assert report.metric == 'var_99'
    assert abs(report.total_change) < _ABS_TOL
    assert abs(report.previous_risk - report.current_risk) < _ABS_TOL
    assert abs(report.residual) < _ABS_TOL
    for item in report.items:
        assert abs(item.delta_risk) < _ABS_TOL, item.driver

def test_drivers_reconcile_to_total_change():
    pricing = BuiltinPricingEngine()
    previous = demo_market_snapshot(SAMPLE_PORTFOLIO)
    current = previous.model_copy(update={'id': 'shocked', 'equity_spots': {k: v * 0.92 for k, v in previous.equity_spots.items()}, 'equity_vols': {k: v * 1.15 for k, v in previous.equity_vols.items()}, 'rates': {k: v + 0.0025 for k, v in previous.rates.items()}, 'fx_spots': {k: v * 0.98 for k, v in previous.fx_spots.items()}})
    report = _engine().explain(RiskChangeAttributionRequest(previous_portfolio=SAMPLE_PORTFOLIO, current_portfolio=SAMPLE_PORTFOLIO, previous_market=previous, current_market=current), pricing)
    explained = sum((i.delta_risk for i in report.items))
    assert abs(explained - report.total_change) <= max(_ABS_TOL, _REL_TOL * abs(report.total_change))
    assert abs(report.residual) < _ABS_TOL
    drivers = {i.driver for i in report.items}
    assert 'Equity moves' in drivers
    assert 'Volatility moves' in drivers
    assert 'Rates moves' in drivers
    assert 'FX moves' in drivers
    assert 'Correlation / residual' in drivers

def test_new_and_closed_trades_attributed():
    pricing = BuiltinPricingEngine()
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    closed_id = SAMPLE_PORTFOLIO.positions[0].id
    remaining = [p for p in SAMPLE_PORTFOLIO.positions if p.id != closed_id]
    new_pos = EquityPosition(type='equity', id='eq-new-test', symbol='AAPL', quantity=500, sector='Technology')
    current = Portfolio(id=SAMPLE_PORTFOLIO.id, name=SAMPLE_PORTFOLIO.name, positions=remaining + [new_pos], firm=SAMPLE_PORTFOLIO.firm, desk=SAMPLE_PORTFOLIO.desk, strategy=SAMPLE_PORTFOLIO.strategy)
    market_curr = market.model_copy(update={'id': 'current-with-aapl', 'equity_spots': {**dict(market.equity_spots), 'AAPL': 190.0}})
    shared = market.model_copy(update={'equity_spots': {**dict(market.equity_spots), **{k: market_curr.equity_spots[k] for k in market_curr.equity_spots}}, 'equity_vols': {**dict(market.equity_vols), **{k: market_curr.equity_vols.get(k, 0.25) for k in market_curr.equity_vols}}})
    report = _engine().explain(RiskChangeAttributionRequest(previous_portfolio=SAMPLE_PORTFOLIO, current_portfolio=current, previous_market=shared, current_market=shared), pricing)
    by_driver = {i.driver: i.delta_risk for i in report.items}
    assert 'Closed trades' in by_driver
    assert 'New trades' in by_driver
    assert abs(by_driver['Closed trades']) > 1.0 or abs(by_driver['New trades']) > 1.0
    explained = sum(by_driver.values())
    assert abs(explained - report.total_change) <= max(_ABS_TOL, _REL_TOL * abs(report.total_change))

def test_position_resize_attributed():
    pricing = BuiltinPricingEngine()
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    current_positions = []
    for p in SAMPLE_PORTFOLIO.positions:
        if p.id == 'eq-spy':
            current_positions.append(p.model_copy(update={'quantity': p.quantity * 2}))
        else:
            current_positions.append(p)
    current = SAMPLE_PORTFOLIO.model_copy(update={'positions': current_positions})
    report = _engine().explain(RiskChangeAttributionRequest(previous_portfolio=SAMPLE_PORTFOLIO, current_portfolio=current, previous_market=market, current_market=market), pricing)
    by_driver = {i.driver: i.delta_risk for i in report.items}
    assert abs(by_driver['Position changes']) > 1.0
    assert abs(by_driver['Closed trades']) < _ABS_TOL
    assert abs(by_driver['New trades']) < _ABS_TOL

def test_service_risk_change_attribution():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine(seed=2, observations=60))
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    report = svc.risk_change_attribution(RiskChangeAttributionRequest(previous_portfolio=SAMPLE_PORTFOLIO, current_portfolio=SAMPLE_PORTFOLIO, previous_market=market, current_market=market, metric='expected_shortfall_99', methodology=VaRMethodology.DELTA_GAMMA))
    assert report.metric == 'expected_shortfall_99'
    assert abs(report.total_change) < _ABS_TOL

def test_change_attribution_api():
    """POST /risk/change-attribution wires RiskChangeAttributionRequest → service."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        portfolio = client.get('/portfolio').json()
        market = client.post('/market/snapshot', json=portfolio).json()
        response = client.post('/risk/change-attribution', json={'previous_portfolio': portfolio, 'current_portfolio': portfolio, 'previous_market': market, 'current_market': market, 'metric': 'var_99', 'methodology': 'DELTA_GAMMA'})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload['metric'] == 'var_99'
        assert 'previous_risk' in payload and 'current_risk' in payload
        assert 'total_change' in payload and 'explained_change' in payload
        assert 'residual' in payload and 'items' in payload
        assert abs(payload['total_change']) < 0.0001
        drivers = [i['driver'] for i in payload['items']]
        assert 'Closed trades' in drivers
        assert 'Correlation / residual' in drivers

def test_separate_from_pnl_attribution():
    """Risk-change module must not be the P&L AttributionEngine."""
    from app.risk.attribution import AttributionEngine
    assert RiskChangeAttributionEngine is not AttributionEngine
    assert RiskChangeAttributionEngine.__module__ == 'app.risk.risk_attribution'
