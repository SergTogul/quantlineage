"""Correctness tests for scenario-result memo (M5.5).

Invariant: memoized ``apply_scenario`` matches uncached marks; bump → miss;
repeated apply with same base+scenario → hit; env flag disables memo.
"""

from __future__ import annotations

import pytest

from app.domain.models import MarketSnapshot, StressScenario
from app.risk.factor_types import EquitySpot
from app.risk.scenario_engine import _apply_scenario_uncached, apply_scenario
from app.risk.scenario_memo import (
    get_scenario_result_memo,
    reset_scenario_result_memo,
)
from app.risk.scenario_model import FactorShock, Scenario, ScenarioCategory


@pytest.fixture(autouse=True)
def _fresh_scenario_memo(monkeypatch):
    monkeypatch.setenv("QUANTLINEAGE_SCENARIO_CACHE", "1")
    monkeypatch.setenv("QUANTLINEAGE_SCENARIO_CACHE_SIZE", "64")
    reset_scenario_result_memo()
    yield
    reset_scenario_result_memo()


def _market(spot: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        id="m1",
        as_of="t0",
        equity_spots={"SPY": spot},
        equity_vols={"SPY": 0.20},
        rates={"USD": 0.04},
    )


def _stress() -> StressScenario:
    return StressScenario(
        id="eq_down",
        name="eq_down",
        equity_shock=-0.10,
        vol_shock=0.0,
        rates_shift_bps=0.0,
    )


def test_scenario_memo_hit_skips_rebuild():
    base = _market()
    scenario = _stress()
    memo = get_scenario_result_memo()

    a = apply_scenario(base, scenario)
    b = apply_scenario(base, scenario)

    assert a.content_hash() == b.content_hash()
    assert a.id == b.id
    assert a is not b  # defensive copies
    assert memo.stats.hits == 1
    assert memo.stats.misses == 1
    assert a.equity_spots["SPY"] == pytest.approx(90.0)


def test_scenario_memo_matches_uncached_marks():
    base = _market()
    scenario = _stress()

    cached = apply_scenario(base, scenario)
    plain = _apply_scenario_uncached(base, scenario)

    assert cached.content_hash() == plain.content_hash()
    assert cached.id == plain.id
    assert cached.equity_spots == plain.equity_spots


def test_scenario_memo_miss_on_base_bump():
    base = _market(100.0)
    bumped = base.bump(EquitySpot("SPY"), 0.05)
    scenario = _stress()
    memo = get_scenario_result_memo()

    apply_scenario(base, scenario)
    apply_scenario(bumped, scenario)

    assert memo.stats.misses == 2
    assert memo.stats.hits == 0


def test_scenario_memo_miss_on_different_shocks():
    base = _market()
    memo = get_scenario_result_memo()
    a = StressScenario(id="a", name="a", equity_shock=-0.05)
    b = StressScenario(id="b", name="b", equity_shock=-0.15)

    apply_scenario(base, a)
    apply_scenario(base, b)

    assert memo.stats.misses == 2
    assert memo.stats.hits == 0


def test_scenario_memo_formal_scenario():
    base = _market()
    formal = Scenario(
        id="formal_eq",
        name="formal",
        category=ScenarioCategory.HYPOTHETICAL,
        shocks=(FactorShock(EquitySpot("SPY"), -0.08),),
    )
    memo = get_scenario_result_memo()

    first = apply_scenario(base, formal)
    second = apply_scenario(base, formal)

    assert first.content_hash() == second.content_hash()
    assert first is not second
    assert memo.stats.hits == 1
    assert first.equity_spots["SPY"] == pytest.approx(92.0)


def test_scenario_memo_disabled(monkeypatch):
    monkeypatch.setenv("QUANTLINEAGE_SCENARIO_CACHE", "0")
    reset_scenario_result_memo()
    base = _market()
    scenario = _stress()

    a = apply_scenario(base, scenario)
    b = apply_scenario(base, scenario)

    assert a is not b
    assert a.content_hash() == b.content_hash()
    assert get_scenario_result_memo().stats.requests == 0
