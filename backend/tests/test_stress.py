"""Production StressEngine must receive an explicit MarketSnapshot."""

from __future__ import annotations

import pytest

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio, StressScenario
from app.pricing.builtin import BuiltinPricingEngine
from app.risk import stress as stress_mod
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


def test_stress_run_applies_scenario_once_not_per_position(monkeypatch) -> None:
    """R0.4.5: N positions × 1 scenario → apply_scenario once (not N)."""
    n_positions = 5
    book = Portfolio(
        id="once-per-scenario",
        name="once-per-scenario",
        positions=[
            EquityPosition(
                type="equity",
                id=f"eq-{i}",
                symbol="UNIT",
                quantity=float(i + 1),
            )
            for i in range(n_positions)
        ],
    )
    market = MarketSnapshot(
        id="once-mkt",
        as_of="2024-01-02",
        equity_spots={"UNIT": 100.0},
    )
    scenario = StressScenario(
        id="eq_down_10",
        name="Equities -10%",
        equity_shock=-0.10,
    )

    real_apply = stress_mod.apply_scenario
    calls: list[object] = []

    def counting_apply(base, scen, **kwargs):
        calls.append(scen)
        return real_apply(base, scen, **kwargs)

    monkeypatch.setattr(stress_mod, "apply_scenario", counting_apply)

    results = ENGINE.run(book, PRICING, [scenario], market=market)
    assert len(results) == 1
    assert len(calls) == 1, f"expected 1 apply_scenario call, got {len(calls)}"
    assert len(results[0].by_position) == n_positions

    # Numerical parity with per-position shocked_value (same base + scenario).
    base = {p.id: PRICING.value(p, market).market_value for p in book.positions}
    expected = {
        p.id: PRICING.shocked_value(p, scenario, market) - base[p.id]
        for p in book.positions
    }
    for pid, pnl in results[0].by_position.items():
        assert abs(pnl - expected[pid]) < 1e-10
    assert abs(results[0].pnl - sum(expected.values())) < 1e-10


def test_stress_evaluate_applies_scenario_once_not_per_position(monkeypatch) -> None:
    """R0.4.5: evaluate also shocks once per scenario for position P&L."""
    n_positions = 4
    book = Portfolio(
        id="once-eval",
        name="once-eval",
        positions=[
            EquityPosition(
                type="equity",
                id=f"eq-{i}",
                symbol="UNIT",
                quantity=float(i + 1),
            )
            for i in range(n_positions)
        ],
    )
    market = MarketSnapshot(
        id="once-eval-mkt",
        as_of="2024-01-02",
        equity_spots={"UNIT": 100.0},
    )
    scenario = StressScenario(
        id="eq_down_10",
        name="Equities -10%",
        equity_shock=-0.10,
    )

    real_apply = stress_mod.apply_scenario
    calls: list[object] = []

    def counting_apply(base, scen, **kwargs):
        calls.append(scen)
        return real_apply(base, scen, **kwargs)

    monkeypatch.setattr(stress_mod, "apply_scenario", counting_apply)

    # contributions() is passed by_trade_pnl, so it must not re-apply the full
    # scenario; factor isolation may apply additional isolated scenarios.
    report = ENGINE.evaluate(book, PRICING, [scenario], market=market)
    assert len(report.evaluations) == 1
    # Full-scenario apply for position P&L must be exactly once; factor-isolated
    # applies (if any) are separate Scenario objects, not N× full rebuilds.
    full_scenario_applies = sum(1 for s in calls if getattr(s, "id", None) == scenario.id)
    assert full_scenario_applies == 1, (
        f"expected 1 full-scenario apply, got {full_scenario_applies} "
        f"(total apply calls={len(calls)})"
    )
    assert len(report.evaluations[0].by_position) == n_positions


def test_stress_run_apply_count_equals_scenario_count_not_pxs(monkeypatch) -> None:
    """RF-006: P positions × S scenarios → apply_scenario == S (not P×S)."""
    n_positions = 5
    n_scenarios = 3
    book = Portfolio(
        id="pxs-run",
        name="pxs-run",
        positions=[
            EquityPosition(
                type="equity",
                id=f"eq-{i}",
                symbol="UNIT",
                quantity=float(i + 1),
            )
            for i in range(n_positions)
        ],
    )
    market = MarketSnapshot(
        id="pxs-run-mkt",
        as_of="2024-01-02",
        equity_spots={"UNIT": 100.0},
    )
    scenarios = [
        StressScenario(id=f"eq_shock_{i}", name=f"Equities {pct:.0%}", equity_shock=pct)
        for i, pct in enumerate((-0.05, -0.10, 0.08))
    ]
    assert len(scenarios) == n_scenarios

    real_apply = stress_mod.apply_scenario
    calls: list[object] = []

    def counting_apply(base, scen, **kwargs):
        calls.append(scen)
        return real_apply(base, scen, **kwargs)

    monkeypatch.setattr(stress_mod, "apply_scenario", counting_apply)

    results = ENGINE.run(book, PRICING, scenarios, market=market)
    assert len(results) == n_scenarios
    assert len(calls) == n_scenarios, (
        f"expected {n_scenarios} apply_scenario calls for {n_scenarios} scenarios, "
        f"got {len(calls)} (would be {n_positions * n_scenarios} if per-position)"
    )
    assert len(calls) != n_positions * n_scenarios
    for result in results:
        assert len(result.by_position) == n_positions


def test_stress_evaluate_apply_count_scales_with_scenarios_not_positions(
    monkeypatch,
) -> None:
    """RF-006: evaluate full-scenario applies == S for P×S (not P×S)."""
    n_positions = 4
    n_scenarios = 3
    book = Portfolio(
        id="pxs-eval",
        name="pxs-eval",
        positions=[
            EquityPosition(
                type="equity",
                id=f"eq-{i}",
                symbol="UNIT",
                quantity=float(i + 1),
            )
            for i in range(n_positions)
        ],
    )
    market = MarketSnapshot(
        id="pxs-eval-mkt",
        as_of="2024-01-02",
        equity_spots={"UNIT": 100.0},
    )
    scenarios = [
        StressScenario(id=f"eq_eval_{i}", name=f"Equities {pct:.0%}", equity_shock=pct)
        for i, pct in enumerate((-0.05, -0.10, 0.08))
    ]
    assert len(scenarios) == n_scenarios
    scenario_ids = {s.id for s in scenarios}

    real_apply = stress_mod.apply_scenario
    calls: list[object] = []

    def counting_apply(base, scen, **kwargs):
        calls.append(scen)
        return real_apply(base, scen, **kwargs)

    monkeypatch.setattr(stress_mod, "apply_scenario", counting_apply)

    report = ENGINE.evaluate(book, PRICING, scenarios, market=market)
    assert len(report.evaluations) == n_scenarios
    # Position P&L path: one full-scenario apply per scenario. Factor-isolated
    # applies (if any) use different Scenario ids — not P×S full rebuilds.
    full_scenario_applies = sum(
        1 for s in calls if getattr(s, "id", None) in scenario_ids
    )
    assert full_scenario_applies == n_scenarios, (
        f"expected {n_scenarios} full-scenario applies, got {full_scenario_applies} "
        f"(total apply calls={len(calls)}; P×S would be {n_positions * n_scenarios})"
    )
    assert full_scenario_applies != n_positions * n_scenarios
    for ev in report.evaluations:
        assert len(ev.by_position) == n_positions
