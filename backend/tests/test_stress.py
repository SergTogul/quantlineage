"""Production StressEngine must receive an explicit MarketSnapshot."""

from __future__ import annotations

import pytest

from app.domain.models import EquityPosition, Portfolio
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.stress import DEFAULT_SCENARIOS, StressEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

PRICING = BuiltinPricingEngine()
ENGINE = StressEngine()
SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)
BOOK = Portfolio(
    id="stress-omit",
    name="stress-omit",
    positions=[
        EquityPosition(type="equity", id="unit", symbol="UNIT", quantity=1.0, )
    ],
)


def test_stress_run_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ENGINE.run(BOOK, PRICING, DEFAULT_SCENARIOS[:1])


def test_stress_run_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ENGINE.run(BOOK, PRICING, DEFAULT_SCENARIOS[:1], market=None)


def test_stress_evaluate_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ENGINE.evaluate(BOOK, PRICING, DEFAULT_SCENARIOS[:1])


def test_stress_evaluate_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ENGINE.evaluate(BOOK, PRICING, DEFAULT_SCENARIOS[:1], market=None)


def test_stress_contributions_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ENGINE.contributions(BOOK, PRICING, DEFAULT_SCENARIOS[0])


def test_stress_run_returns_position_breakdown() -> None:
    results = ENGINE.run(
        SAMPLE_PORTFOLIO, PRICING, DEFAULT_SCENARIOS[:1], market=SAMPLE_MARKET
    )
    assert len(results) == 1
    assert len(results[0].by_position) == len(SAMPLE_PORTFOLIO.positions)
    assert abs(results[0].pnl - sum(results[0].by_position.values())) < 1e-8


def test_stress_evaluate_with_explicit_market() -> None:
    report = ENGINE.evaluate(
        SAMPLE_PORTFOLIO, PRICING, DEFAULT_SCENARIOS[:2], market=SAMPLE_MARKET
    )
    assert report.portfolio_id == SAMPLE_PORTFOLIO.id
    assert len(report.evaluations) == 2
    assert report.base_market_value != 0.0
