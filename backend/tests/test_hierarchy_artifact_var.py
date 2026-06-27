"""R0.7.3 leftover: node VaR/ES from summed artifact historical P&L vectors.

When a complete artifact map carries historical P&L, HierarchyEngine sums
the node subset and computes var_95 / var_99 / expected_shortfall_99 with
the same convention as ``test_var_es_golden.py`` / ``HistoricalRiskEngine``:

- loss = -P&L
- ``numpy.quantile`` default linear interpolation
- VaR and ES floored at zero
- ES is the mean of losses greater than or equal to VaR

Omitted vectors stay zeros. Mixed present/absent fails closed (artifact
``add()``). Pricing is not invoked on the artifact path.

Conventions:
- Units: currency P&L / VaR / ES
- Sign: loss = -P&L
- Tolerance: exact on controlled vectors (abs 1e-12)
"""
from __future__ import annotations

import numpy as np
import pytest
from tests.market_fixtures import equity_spots_market

from app.domain.models import (
    EquityPosition,
    HierarchyLevel,
    HierarchyRef,
    MarketSnapshot,
    Portfolio,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.hierarchy import HierarchyEngine
from app.risk.historical import HistoricalRiskEngine
from app.sample import SAMPLE_PORTFOLIO
from app.services.risk_factories import build_portfolio_service
from app.risk.trade_artifacts import TradeCalculationArtifact

ABS_TOL = 1e-12

class _ForbiddenPricing:
    """Fails if any pricing entry point is used."""

    def value(self, position, market=None):
        raise AssertionError('pricing.value must not be called when artifacts are supplied')

    def value_portfolio(self, portfolio, market=None):
        raise AssertionError('pricing.value_portfolio must not be called when artifacts are supplied')

    def shocked_value(self, position, scenario, market=None):
        raise AssertionError('pricing.shocked_value must not be called when artifacts are supplied')

def _two_trade_market() -> MarketSnapshot:
    return equity_spots_market({"AAA": 100.0, "BBB": 80.0})

def _two_trade_book() -> Portfolio:
    return Portfolio(id='two-trade', name='Two Trade Book', firm='Acme Capital', desk='Equity Desk', strategy='Momentum', positions=[EquityPosition(type='equity', id='eq-a', symbol='AAA', quantity=100, book='Cash', desk='Equity Desk', strategy='Momentum'), EquityPosition(type='equity', id='eq-b', symbol='BBB', quantity=50, book='Cash', desk='Equity Desk', strategy='Momentum')])

def _artifact(trade_id: str, *, pv: float, historical_pnl: tuple[float, ...] | None=None) -> TradeCalculationArtifact:
    return TradeCalculationArtifact.from_parts(trade_id, pv=pv, delta=1.0, historical_pnl=historical_pnl)

def _var_es_from_pnl(pnl: np.ndarray) -> tuple[float, float, float]:
    """Independent golden-convention VaR 95/99 and ES 99 (not imported from production)."""
    losses = -np.asarray(pnl, dtype=float)
    var_95 = float(max(0.0, np.quantile(losses, 0.95)))
    var_99 = float(max(0.0, np.quantile(losses, 0.99)))
    tail = losses[losses >= var_99]
    es_99 = float(max(0.0, tail.mean() if len(tail) else var_99))
    return (var_95, var_99, es_99)

def _engine() -> HierarchyEngine:
    return HierarchyEngine(HistoricalRiskEngine(seed=1, observations=20))

def test_node_var_es_equals_var_es_of_summed_trade_vectors():
    vec_a = (-1.0, -2.0, -3.0, -4.0)
    vec_b = (-10.0, 0.0, 0.0, 0.0)
    summed = tuple((a + b for a, b in zip(vec_a, vec_b, strict=True)))
    expected_95, expected_99, expected_es = _var_es_from_pnl(np.array(summed))
    pf = _two_trade_book()
    artifacts = {'eq-a': _artifact('eq-a', pv=100.0, historical_pnl=vec_a), 'eq-b': _artifact('eq-b', pv=40.0, historical_pnl=vec_b)}
    root = _engine().build(pf, BuiltinPricingEngine(), market=_two_trade_market(), artifacts=artifacts)
    assert root.var_95 == pytest.approx(expected_95, rel=0, abs=ABS_TOL)
    assert root.var_99 == pytest.approx(expected_99, rel=0, abs=ABS_TOL)
    assert root.expected_shortfall_99 == pytest.approx(expected_es, rel=0, abs=ABS_TOL)
    assert root.limits
    assert {row.metric for row in root.limits} >= {"var_99", "expected_shortfall_99", "stress_loss"}
    child_var_99 = root.children[0].var_99
    assert child_var_99 == pytest.approx(expected_99, rel=0, abs=ABS_TOL)
    book = root.children[0].children[0].children[0].children[0]
    trades = {t.name: t for t in book.children}
    trade_a_95, trade_a_99, trade_a_es = _var_es_from_pnl(np.array(vec_a))
    trade_b_95, trade_b_99, trade_b_es = _var_es_from_pnl(np.array(vec_b))
    assert trades['eq-a'].var_99 == pytest.approx(trade_a_99, rel=0, abs=ABS_TOL)
    assert trades['eq-a'].expected_shortfall_99 == pytest.approx(trade_a_es, rel=0, abs=ABS_TOL)
    assert trades['eq-b'].var_99 == pytest.approx(trade_b_99, rel=0, abs=ABS_TOL)
    assert trades['eq-b'].expected_shortfall_99 == pytest.approx(trade_b_es, rel=0, abs=ABS_TOL)
    assert trades['eq-a'].var_95 == pytest.approx(trade_a_95, rel=0, abs=ABS_TOL)
    assert trades['eq-b'].var_95 == pytest.approx(trade_b_95, rel=0, abs=ABS_TOL)
    assert trades['eq-a'].var_99 + trades['eq-b'].var_99 != pytest.approx(root.var_99, rel=0, abs=ABS_TOL)

def test_risk_at_var_es_from_summed_vectors():
    vec_a = (-1.0, -2.0, -3.0, -4.0)
    vec_b = (-10.0, 0.0, 0.0, 0.0)
    summed = tuple((a + b for a, b in zip(vec_a, vec_b, strict=True)))
    _, expected_99, expected_es = _var_es_from_pnl(np.array(summed))
    pf = _two_trade_book()
    artifacts = {'eq-a': _artifact('eq-a', pv=100.0, historical_pnl=vec_a), 'eq-b': _artifact('eq-b', pv=40.0, historical_pnl=vec_b)}
    node = _engine().risk_at(pf, BuiltinPricingEngine(), HierarchyRef(level=HierarchyLevel.BOOK, firm='Acme Capital', portfolio_id='two-trade', desk='Equity Desk', strategy='Momentum', book='Cash'), market=_two_trade_market(), artifacts=artifacts)
    assert node.var_99 == pytest.approx(expected_99, rel=0, abs=ABS_TOL)
    assert node.expected_shortfall_99 == pytest.approx(expected_es, rel=0, abs=ABS_TOL)

def test_omitted_historical_vectors_stay_zero_var_es():
    pf = _two_trade_book()
    artifacts = {'eq-a': _artifact('eq-a', pv=100.0), 'eq-b': _artifact('eq-b', pv=40.0)}
    root = _engine().build(pf, BuiltinPricingEngine(), market=_two_trade_market(), artifacts=artifacts)
    assert root.var_95 == 0.0
    assert root.var_99 == 0.0
    assert root.expected_shortfall_99 == 0.0
    assert root.limits
    assert {row.metric for row in root.limits} >= {"var_99", "expected_shortfall_99", "stress_loss"}

def test_mixed_historical_vectors_fail_closed():
    pf = _two_trade_book()
    artifacts = {'eq-a': _artifact('eq-a', pv=100.0, historical_pnl=(-1.0, -2.0)), 'eq-b': _artifact('eq-b', pv=40.0, historical_pnl=None)}
    with pytest.raises(ValueError, match='historical_pnl is present on only one'):
        _engine().build(pf, _ForbiddenPricing(), market=_two_trade_market(), artifacts=artifacts)


def test_production_factory_hierarchy_var_es_matches_summary():
    """Review Test B: production factor-panel path must not zero hierarchy VaR/ES."""
    service = build_portfolio_service(observations=40, seed=7)
    summary = service.summary(SAMPLE_PORTFOLIO)
    root = service.hierarchy(SAMPLE_PORTFOLIO)
    assert summary.var_99 != 0.0
    assert root.var_99 == pytest.approx(summary.var_99, rel=1e-9, abs=1e-6)
    assert root.var_95 == pytest.approx(summary.var_95, rel=1e-9, abs=1e-6)
    assert root.expected_shortfall_99 == pytest.approx(
        summary.expected_shortfall_99, rel=1e-9, abs=1e-6
    )
    assert root.limits
    assert {row.metric for row in root.limits} >= {"var_99", "expected_shortfall_99", "stress_loss"}
