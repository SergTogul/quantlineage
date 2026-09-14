"""Production VaR / ES / hierarchy / stress / reverse-stress must not infer a market."""

from __future__ import annotations

import pytest

from app.domain.models import (
    EquityPosition,
    HierarchyLevel,
    HierarchyRef,
    MarketSnapshot,
    Portfolio,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.es import ESContributionAnalytics
from app.risk.hierarchy import HierarchyEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.reverse_stress import ReverseStressEngine
from app.risk.reverse_stress_multi import MultiFactorReverseStressEngine
from app.risk.scenario_attribution import ScenarioAttributionEngine
from app.risk.stress import DEFAULT_SCENARIOS, StressEngine
from app.risk.var import VaRAnalytics

PRICING = BuiltinPricingEngine()
BOOK = Portfolio(
    id="omit-market",
    name="omit-market",
    positions=[
        EquityPosition(type="equity", id="unit", symbol="UNIT", quantity=1.0)
    ],
)
UNIT_MARKET = MarketSnapshot(
    id="omit-unit",
    equity_spots={"UNIT": 1.0},
    rates={"USD": 0.04},
)
HIERARCHY = HierarchyEngine(HistoricalRiskEngine(seed=1, observations=8))
STRESS = StressEngine()
REVERSE = ReverseStressEngine()
REVERSE_MULTI = MultiFactorReverseStressEngine()
FIRM_REF = HierarchyRef(level=HierarchyLevel.FIRM, firm="QuantLineage")


def test_historical_engine_calculate_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        HistoricalRiskEngine(seed=1, observations=8).calculate(BOOK, PRICING)


def test_historical_engine_calculate_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        HistoricalRiskEngine(seed=1, observations=8).calculate(BOOK, PRICING, market=None)


def test_var_analytics_report_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        VaRAnalytics(seed=1, observations=8).report(BOOK, PRICING)


def test_es_report_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ESContributionAnalytics(seed=1, observations=8).report(BOOK, PRICING)


def test_es_empty_book_omitted_market_raises() -> None:
    empty = Portfolio(id="empty", name="Empty", positions=[])
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ESContributionAnalytics(seed=1, observations=8).report(empty, PRICING)


def test_explicit_market_still_values() -> None:
    market = UNIT_MARKET
    result = HistoricalRiskEngine(seed=1, observations=8).calculate(
        BOOK, PRICING, market=market
    )
    assert result.market_value == pytest.approx(1.0)
    report = VaRAnalytics(seed=1, observations=8).report(BOOK, PRICING, market=market)
    assert report.portfolio_id == BOOK.id
    es = ESContributionAnalytics(seed=1, observations=8).report(
        BOOK, PRICING, market=market
    )
    assert es.portfolio_id == BOOK.id


def test_explicit_empty_snapshot_is_accepted_as_market() -> None:
    market = MarketSnapshot(id="empty")
    empty = Portfolio(id="empty", name="Empty", positions=[])
    es = ESContributionAnalytics(seed=1, observations=8).report(
        empty, PRICING, market=market
    )
    assert es.portfolio_es == 0.0


def test_hierarchy_build_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        HIERARCHY.build(BOOK, PRICING)


def test_hierarchy_build_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        HIERARCHY.build(BOOK, PRICING, market=None)


def test_hierarchy_risk_at_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        HIERARCHY.risk_at(BOOK, PRICING, FIRM_REF)


def test_hierarchy_risk_at_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        HIERARCHY.risk_at(BOOK, PRICING, FIRM_REF, market=None)


def test_stress_run_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        STRESS.run(BOOK, PRICING, DEFAULT_SCENARIOS[:1])


def test_stress_run_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        STRESS.run(BOOK, PRICING, DEFAULT_SCENARIOS[:1], market=None)


def test_stress_evaluate_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        STRESS.evaluate(BOOK, PRICING, DEFAULT_SCENARIOS[:1])


def test_stress_contributions_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        STRESS.contributions(BOOK, PRICING, DEFAULT_SCENARIOS[0])


def test_reverse_stress_solve_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        REVERSE.solve(BOOK, PRICING, 0.01, "equity", 0.8)


def test_reverse_stress_solve_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        REVERSE.solve(BOOK, PRICING, 0.01, "equity", 0.8, market=None)


def test_reverse_stress_multi_solve_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        REVERSE_MULTI.solve(BOOK, PRICING, 0.01, factors=["equity"])


def test_scenario_attribution_decompose_omitted_market_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ScenarioAttributionEngine().decompose(BOOK, PRICING, DEFAULT_SCENARIOS[0])


def test_scenario_attribution_decompose_market_none_raises() -> None:
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ScenarioAttributionEngine().decompose(
            BOOK, PRICING, DEFAULT_SCENARIOS[0], market=None
        )


def test_scenario_attribution_decompose_empty_book_omitted_market_raises() -> None:
    empty = Portfolio(id="empty", name="Empty", positions=[])
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        ScenarioAttributionEngine().decompose(empty, PRICING, DEFAULT_SCENARIOS[0])


def test_hierarchy_stress_reverse_explicit_market_still_values() -> None:
    market = UNIT_MARKET
    root = HIERARCHY.build(BOOK, PRICING, market=market)
    assert root.market_value == pytest.approx(1.0)
    node = HIERARCHY.risk_at(BOOK, PRICING, FIRM_REF, market=market)
    assert node.market_value == pytest.approx(1.0)
    results = STRESS.run(BOOK, PRICING, DEFAULT_SCENARIOS[:1], market=market)
    assert len(results) == 1
    report = STRESS.evaluate(BOOK, PRICING, DEFAULT_SCENARIOS[:1], market=market)
    assert report.portfolio_id == BOOK.id
    solved = REVERSE.solve(BOOK, PRICING, 0.01, "equity", 0.8, market=market)
    assert solved.base_market_value == pytest.approx(1.0)
    multi = REVERSE_MULTI.solve(BOOK, PRICING, 0.01, factors=["equity"], market=market)
    assert multi.base_market_value == pytest.approx(1.0)
    breakdown = ScenarioAttributionEngine().decompose(
        BOOK, PRICING, DEFAULT_SCENARIOS[0], market=market
    )
    assert breakdown.scenario_id == DEFAULT_SCENARIOS[0].id
