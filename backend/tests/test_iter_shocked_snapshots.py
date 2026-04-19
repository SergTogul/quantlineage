"""R0.6.2 — stream shocked MarketSnapshot objects one at a time.

Invariant: iterator P&L equals list-materialized P&L. Existing
``shocked_snapshots`` / ``historical_shocked_snapshots`` remain list wrappers.
``require_explicit_market`` is unchanged. VaR/ES statistical semantics are
not altered.

Tolerances: exact snapshot hashes; P&L atol 1e-12 (same as R0.1.4 goldens).
"""
from __future__ import annotations
import inspect
import re
from collections.abc import Iterator
import numpy as np
import pytest
from app.domain.models import EquityPosition, MarketSnapshot, Portfolio, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine, full_revaluation_pnl_series
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.scenarios import historical_market_scenarios, historical_shocked_snapshots, iter_historical_shocked_snapshots, iter_shocked_snapshots, shocked_snapshots
from app.risk.var import VaRAnalytics

def _base_snapshot() -> MarketSnapshot:
    return MarketSnapshot(id='base', equity_spots={'SPY': 100.0, 'NVDA': 200.0}, equity_vols={'SPY': 0.2}, fx_spots={'EURUSD': 1.1}, fx_vols={'EURUSD': 0.12}, rates={'USD': 0.04, 'EUR': 0.03})

def _series() -> FactorObservationSeries:
    return FactorObservationSeries(equity_returns=np.array([0.0, -0.1, 0.05]), vol_moves=np.array([0.0, 0.25, 0.0]), rate_moves_bps=np.array([0.0, 50.0, -25.0]), fx_returns=np.array([0.0, -0.05, 0.01]))

def _equity_book() -> tuple[Portfolio, MarketSnapshot]:
    pos = EquityPosition(type='equity', id='eq', symbol='UNIT', quantity=10.0)
    book = Portfolio(id='one', name='one', positions=[pos])
    market = MarketSnapshot(id='base', equity_spots={'UNIT': 100.0}, rates={'USD': 0.04})
    return (book, market)

def _dataset(equity_returns: np.ndarray) -> ArrayHistoricalDataset:
    z = np.zeros_like(equity_returns)
    return ArrayHistoricalDataset(FactorObservationSeries(equity_returns=np.asarray(equity_returns, dtype=float), vol_moves=z, rate_moves_bps=z, fx_returns=z))

def _snapshot_keys(snaps: list[MarketSnapshot]) -> list[tuple[str, str]]:
    return [(s.id, s.content_hash()) for s in snaps]

def test_iter_shocked_snapshots_is_iterator_not_list():
    base = _base_snapshot()
    scenarios = historical_market_scenarios(base, _series())
    it = iter_shocked_snapshots(base, scenarios)
    assert not isinstance(it, list)
    assert isinstance(it, Iterator)
    assert inspect.isgenerator(it)

def test_iter_historical_shocked_snapshots_is_iterator_not_list():
    base = _base_snapshot()
    it = iter_historical_shocked_snapshots(base, ArrayHistoricalDataset(_series()))
    assert not isinstance(it, list)
    assert isinstance(it, Iterator)
    assert inspect.isgenerator(it)

def test_shocked_snapshots_still_returns_list_matching_iterator():
    base = _base_snapshot()
    scenarios = historical_market_scenarios(base, _series())
    listed = shocked_snapshots(base, scenarios)
    streamed = list(iter_shocked_snapshots(base, scenarios))
    assert isinstance(listed, list)
    assert len(listed) == 3
    assert _snapshot_keys(listed) == _snapshot_keys(streamed)
    assert listed[0].content_hash() == base.content_hash()
    assert listed[1].equity_spots['SPY'] == pytest.approx(90.0)
    assert listed[2].equity_spots['SPY'] == pytest.approx(105.0)

def test_historical_shocked_snapshots_still_returns_list_matching_iterator():
    base = _base_snapshot()
    dataset = ArrayHistoricalDataset(_series())
    listed = historical_shocked_snapshots(base, dataset)
    streamed = list(iter_historical_shocked_snapshots(base, dataset))
    assert isinstance(listed, list)
    assert len(listed) == 3
    assert _snapshot_keys(listed) == _snapshot_keys(streamed)
    assert listed[1].rates['USD'] == pytest.approx(0.045)

def test_streaming_pnl_series_equals_list_materialized_series():
    book, market = _equity_book()
    pricing = BuiltinPricingEngine()
    dataset = _dataset(np.array([-0.1, 0.0, 0.05]))
    base_pv = pricing.value(book.positions[0], market).market_value
    list_pnl = np.array([pricing.value(book.positions[0], snap).market_value - base_pv for snap in historical_shocked_snapshots(market, dataset)], dtype=float)
    stream_pnl = np.array([pricing.value(book.positions[0], snap).market_value - base_pv for snap in iter_historical_shocked_snapshots(market, dataset)], dtype=float)
    engine_pnl = full_revaluation_pnl_series(book, pricing, market, dataset)
    np.testing.assert_allclose(stream_pnl, list_pnl, atol=1e-12)
    np.testing.assert_allclose(engine_pnl, list_pnl, atol=1e-12)
    np.testing.assert_allclose(engine_pnl, np.array([-100.0, 0.0, 50.0]), atol=1e-12)
    pos_pnl = VaRAnalytics(dataset=dataset)._full_reval_position_pnls(book, pricing, market)
    np.testing.assert_allclose(pos_pnl['eq'], list_pnl, atol=1e-12)

def test_full_reval_production_loops_use_iterator_not_list():
    hist_src = inspect.getsource(full_revaluation_pnl_series)
    assert 'iter_historical_shocked_snapshots' in hist_src
    assert re.search('(?<![\\w.])historical_shocked_snapshots\\b', hist_src) is None
    var_src = inspect.getsource(VaRAnalytics._full_reval_position_pnls)
    assert 'iter_historical_shocked_snapshots' in var_src
    assert re.search('(?<![\\w.])historical_shocked_snapshots\\b', var_src) is None

def test_require_explicit_market_unchanged_on_full_reval_paths():
    book, _market = _equity_book()
    pricing = BuiltinPricingEngine()
    dataset = _dataset(np.array([-0.1, 0.0]))
    with pytest.raises(ValueError, match='explicit MarketSnapshot'):
        HistoricalRiskEngine(dataset=dataset).calculate(book, pricing, methodology=VaRMethodology.FULL_REVALUATION)
    with pytest.raises(ValueError, match='explicit MarketSnapshot'):
        HistoricalRiskEngine(dataset=dataset).calculate(book, pricing, methodology=VaRMethodology.FULL_REVALUATION, market=None)
    with pytest.raises(ValueError, match='explicit MarketSnapshot'):
        VaRAnalytics(dataset=dataset).report(book, pricing, methodology=VaRMethodology.FULL_REVALUATION)
    with pytest.raises(ValueError, match='explicit MarketSnapshot'):
        VaRAnalytics(dataset=dataset).report(book, pricing, methodology=VaRMethodology.FULL_REVALUATION, market=None)
