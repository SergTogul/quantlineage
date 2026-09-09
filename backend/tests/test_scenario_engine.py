"""M3.2 multi-factor scenario engine tests.

Acceptance:
- Combined equity / rates / FX / vol shocks → shocked MarketSnapshot
- Accepts formal Scenario / FactorShock (M3.1), legacy StressScenario,
  MarketScenario / FactorChange, and (RiskFactor, amount) pairs
- Empty scenario → content_hash unchanged (zero P&L precondition)
- Deterministic results; independent scenarios (not cumulative)
- Canonical expansion order for StressScenario; caller order for explicit lists
- StressScenario APIs (shock_snapshot) remain equivalent to the engine

Units / tolerances (aligned with MarketSnapshot.bump):
- equity / FX: relative return; vol: relative vol level; rates: decimal in bump
  (StressScenario rates_shift_bps / rate_shocks_bps → bps_to_decimal_rate)
- Exact mark equality where discrete; abs 1e-12 for rate decimal shifts
"""

from __future__ import annotations

import pytest

from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.market.snapshot import shock_snapshot
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero
from app.risk.scenario_engine import (
    ScenarioEngine,
    apply_scenario,
    expand_scenario,
    shocked_snapshots,
)
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    ScenarioCategory,
    ScenarioThreshold,
    compose_shocks,
    scenario_from_stress,
    scenario_to_stress,
)
from app.risk.scenarios import FactorChange, MarketScenario
from app.risk.shock_units import bps_to_decimal_rate


def _base() -> MarketSnapshot:
    return MarketSnapshot(
        id="base",
        equity_spots={"SPY": 100.0, "NVDA": 200.0},
        equity_vols={"SPY": 0.20, "NVDA": 0.40},
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.12},
        rates={"USD": 0.04, "EUR": 0.03},
    )


def test_empty_stress_scenario_leaves_content_hash_unchanged():
    base = _base()
    shocked = apply_scenario(base, StressScenario(name="noop", id="noop"))
    assert shocked.content_hash() == base.content_hash()
    assert shocked.id == "base:noop"


def test_empty_formal_scenario_leaves_content_hash_unchanged():
    base = _base()
    scenario = Scenario(id="empty", name="Empty", category=ScenarioCategory.CUSTOM, shocks=())
    shocked = apply_scenario(base, scenario)
    assert shocked.content_hash() == base.content_hash()
    assert shocked.id == "base:empty"


def test_empty_factor_change_list_leaves_content_hash_unchanged():
    base = _base()
    shocked = apply_scenario(base, ())
    assert shocked.content_hash() == base.content_hash()
    assert shocked.id == base.id


def test_combined_multi_factor_formal_scenario():
    base = _base()
    scenario = Scenario(
        id="crisis",
        name="Combined",
        category=ScenarioCategory.MACRO,
        description="equity / vol / fx / rates together",
        shocks=compose_shocks(
            (
                FactorShock(EquitySpot("SPY"), -0.10),
                FactorShock(EquitySpot("NVDA"), -0.10),
            ),
            (
                FactorShock(EquityVol(underlying="SPY"), 0.25),
                FactorShock(EquityVol(underlying="NVDA"), 0.25),
            ),
            (FactorShock(FXSpot("EURUSD"), -0.05), FactorShock(FXVol(pair="EURUSD"), 0.25)),
            (
                FactorShock(RateZero(currency="USD", tenor="ALL"), 0.005),
                FactorShock(RateZero(currency="EUR", tenor="ALL"), 0.005),
            ),
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.10),
    )
    shocked = apply_scenario(base, scenario)
    assert shocked.equity_spots["SPY"] == pytest.approx(90.0)
    assert shocked.equity_spots["NVDA"] == pytest.approx(180.0)
    assert shocked.equity_vols["SPY"] == pytest.approx(0.25)
    assert shocked.fx_spots["EURUSD"] == pytest.approx(1.10 * 0.95)
    assert shocked.fx_vols["EURUSD"] == pytest.approx(0.12 * 1.25)
    assert shocked.rates["USD"] == pytest.approx(0.045)
    assert shocked.rates["EUR"] == pytest.approx(0.035)
    assert shocked.id == "base:crisis"


def test_combined_multi_factor_stress_scenario():
    base = _base()
    scenario = StressScenario(
        id="crisis",
        name="Combined",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.10,
        vol_shock=0.25,
        rates_shift_bps=50.0,
        fx_shock=-0.05,
    )
    shocked = apply_scenario(base, scenario)
    assert shocked.equity_spots["SPY"] == pytest.approx(90.0)
    assert shocked.equity_spots["NVDA"] == pytest.approx(180.0)
    assert shocked.equity_vols["SPY"] == pytest.approx(0.25)
    assert shocked.fx_spots["EURUSD"] == pytest.approx(1.10 * 0.95)
    assert shocked.fx_vols["EURUSD"] == pytest.approx(0.12 * 1.25)
    assert shocked.rates["USD"] == pytest.approx(0.045)
    assert shocked.rates["EUR"] == pytest.approx(0.035)
    assert shocked.id == "base:crisis"


def test_formal_stress_and_factor_lists_agree():
    base = _base()
    legacy = StressScenario(
        id="combo",
        name="combo",
        equity_shock=-0.10,
        vol_shock=0.25,
        rates_shift_bps=50.0,
        fx_shock=-0.05,
    )
    formal = scenario_from_stress(legacy, base)
    typed_changes = [
        FactorChange(EquitySpot("SPY"), -0.10),
        FactorChange(EquitySpot("NVDA"), -0.10),
        FactorChange(EquityVol(underlying="SPY"), 0.25),
        FactorChange(EquityVol(underlying="NVDA"), 0.25),
        FactorChange(FXSpot("EURUSD"), -0.05),
        FactorChange(FXVol(pair="EURUSD"), 0.25),
        FactorChange(RateZero(currency="USD", tenor="ALL"), 0.005),
        FactorChange(RateZero(currency="EUR", tenor="ALL"), 0.005),
    ]
    typed_shocks = [FactorShock(c.factor, c.amount) for c in typed_changes]
    hashes = {
        apply_scenario(base, legacy).content_hash(),
        apply_scenario(base, formal).content_hash(),
        apply_scenario(base, typed_changes, scenario_id="combo").content_hash(),
        apply_scenario(base, typed_shocks, scenario_id="combo").content_hash(),
        shock_snapshot(base, scenario_to_stress(formal)).content_hash(),
    }
    assert len(hashes) == 1


def test_r042a_stress_formal_parity_exact_marks_and_rate_units():
    """R0.4.2-A: legacy StressScenario and formal Scenario share one conversion story.

    Rate bp → decimal bump only via ``bps_to_decimal_rate`` at the adapter;
    shocked spots/vols/rates and ``content_hash`` match with exact float equality.
    """
    base = _base()
    legacy = StressScenario(
        id="parity",
        name="parity",
        equity_shock=-0.10,
        vol_shock=0.25,
        rates_shift_bps=50.0,
        rate_shocks_bps={"EUR": 25.0},
        fx_shock=-0.05,
    )
    formal = scenario_from_stress(legacy, base)
    rate_shocks = [s for s in formal.shocks if isinstance(s.factor, RateZero)]
    by_ccy = {s.factor.currency: s.amount for s in rate_shocks}
    assert by_ccy["USD"] == bps_to_decimal_rate(50.0)
    assert by_ccy["EUR"] == bps_to_decimal_rate(25.0)

    via_legacy = apply_scenario(base, legacy)
    via_formal = apply_scenario(base, formal)
    via_collapse = shock_snapshot(base, scenario_to_stress(formal))

    assert via_legacy.equity_spots == via_formal.equity_spots == via_collapse.equity_spots
    assert via_legacy.equity_vols == via_formal.equity_vols == via_collapse.equity_vols
    assert via_legacy.fx_spots == via_formal.fx_spots == via_collapse.fx_spots
    assert via_legacy.fx_vols == via_formal.fx_vols == via_collapse.fx_vols
    assert via_legacy.rates == via_formal.rates == via_collapse.rates
    assert via_legacy.content_hash() == via_formal.content_hash() == via_collapse.content_hash()
    assert via_legacy.rates["USD"] == 0.04 + bps_to_decimal_rate(50.0)
    assert via_legacy.rates["EUR"] == 0.03 + bps_to_decimal_rate(25.0)


def test_market_scenario_path():
    base = _base()
    scenario = MarketScenario(
        id="ms1",
        name="Equity + rates",
        kind=ScenarioKind.CUSTOM,
        shocks=(
            FactorChange(EquitySpot("SPY"), -0.05),
            FactorChange(RateZero(currency="USD", tenor="ALL"), 0.001),
        ),
    )
    shocked = apply_scenario(base, scenario)
    assert shocked.equity_spots["SPY"] == pytest.approx(95.0)
    assert shocked.equity_spots["NVDA"] == 200.0
    assert shocked.rates["USD"] == pytest.approx(0.041)
    assert shocked.rates["EUR"] == 0.03
    assert shocked.id == "base:ms1"


def test_expand_stress_scenario_canonical_order():
    base = _base()
    scenario = StressScenario(
        name="ordered",
        equity_shock=-0.1,
        vol_shock=0.2,
        fx_shock=-0.01,
        rates_shift_bps=10.0,
    )
    changes = expand_scenario(base, scenario)
    kinds = [type(c.factor).__name__ for c in changes]
    assert kinds == [
        "EquitySpot",
        "EquitySpot",
        "EquityVol",
        "EquityVol",
        "FXSpot",
        "FXVol",
        "RateZero",
        "RateZero",
    ]
    assert all(isinstance(c, FactorShock) for c in changes)


def test_explicit_list_preserves_caller_order():
    base = _base()
    shocks = [
        FactorShock(RateZero(currency="USD", tenor="ALL"), 0.01),
        FactorShock(EquitySpot("SPY"), -0.10),
    ]
    expanded = expand_scenario(base, shocks)
    assert [type(c.factor).__name__ for c in expanded] == ["RateZero", "EquitySpot"]
    shocked = apply_scenario(base, shocks, scenario_id="custom_order")
    assert shocked.rates["USD"] == pytest.approx(0.05)
    assert shocked.equity_spots["SPY"] == pytest.approx(90.0)


def test_per_name_dict_overrides_scalar():
    base = _base()
    scenario = StressScenario(
        id="override",
        name="override",
        equity_shock=-0.10,
        equity_shocks={"NVDA": -0.20},
        vol_shock=0.10,
        vol_shocks={"SPY": 0.50},
        rates_shift_bps=25.0,
        rate_shocks_bps={"EUR": 100.0},
        fx_shock=-0.02,
    )
    shocked = apply_scenario(base, scenario)
    assert shocked.equity_spots["SPY"] == pytest.approx(90.0)
    assert shocked.equity_spots["NVDA"] == pytest.approx(160.0)
    assert shocked.equity_vols["SPY"] == pytest.approx(0.30)
    assert shocked.equity_vols["NVDA"] == pytest.approx(0.44)
    assert shocked.rates["USD"] == pytest.approx(0.0425)
    assert shocked.rates["EUR"] == pytest.approx(0.04)
    assert shocked.fx_spots["EURUSD"] == pytest.approx(1.10 * 0.98)


def test_shocked_snapshots_are_independent_not_cumulative():
    base = _base()
    scenarios = [
        StressScenario(id="a", name="a", equity_shock=-0.10),
        Scenario(
            id="b",
            name="b",
            category=ScenarioCategory.FACTOR,
            shocks=(FactorShock(EquitySpot("SPY"), 0.05), FactorShock(EquitySpot("NVDA"), 0.05)),
        ),
    ]
    snaps = shocked_snapshots(base, scenarios)
    assert snaps[0].equity_spots["SPY"] == pytest.approx(90.0)
    assert snaps[1].equity_spots["SPY"] == pytest.approx(105.0)
    assert base.equity_spots["SPY"] == 100.0


def test_engine_is_deterministic():
    base = _base()
    engine = ScenarioEngine()
    scenario = Scenario(
        id="det",
        name="det",
        category=ScenarioCategory.MACRO,
        shocks=(
            FactorShock(EquitySpot("SPY"), -0.07),
            FactorShock(EquityVol(underlying="SPY"), 0.15),
            FactorShock(RateZero(currency="USD", tenor="ALL"), 0.0033),
            FactorShock(FXSpot("EURUSD"), -0.03),
        ),
    )
    a = engine.apply(base, scenario)
    b = engine.apply(base, scenario)
    assert a.content_hash() == b.content_hash()
    assert a.model_dump() == b.model_dump()


def test_engine_to_formal_lifts_stress_scenario():
    base = _base()
    engine = ScenarioEngine()
    legacy = StressScenario(id="lift", name="Lift", equity_shock=-0.05, rates_shift_bps=10.0)
    formal = engine.to_formal(base, legacy)
    assert isinstance(formal, Scenario)
    assert formal.id == "lift"
    assert apply_scenario(base, formal).content_hash() == apply_scenario(base, legacy).content_hash()


def test_duplicate_factor_compounds_via_successive_bump():
    base = _base()
    shocks = [
        FactorShock(EquitySpot("SPY"), -0.10),
        FactorShock(EquitySpot("SPY"), -0.10),
    ]
    shocked = apply_scenario(base, shocks, scenario_id="compound")
    assert shocked.equity_spots["SPY"] == pytest.approx(81.0)


def test_shock_snapshot_delegates_to_engine():
    base = _base()
    scenario = StressScenario(
        id="bridge",
        name="bridge",
        equity_shock=-0.05,
        vol_shock=0.10,
        rates_shift_bps=20.0,
        fx_shock=-0.02,
    )
    via_engine = apply_scenario(base, scenario)
    via_legacy = shock_snapshot(base, scenario)
    assert via_engine.content_hash() == via_legacy.content_hash()
    assert via_engine.id == via_legacy.id


def test_pair_tuples_accepted():
    base = _base()
    shocked = apply_scenario(
        base,
        [(EquitySpot("SPY"), -0.05), (RateZero(currency="USD", tenor="PARALLEL"), 0.002)],
        scenario_id="pairs",
    )
    assert shocked.equity_spots["SPY"] == pytest.approx(95.0)
    assert shocked.rates["USD"] == pytest.approx(0.042)
    assert shocked.id == "base:pairs"


def test_deep_freeze_preserved():
    base = _base()
    shocked = apply_scenario(
        base,
        Scenario(
            id="f",
            name="f",
            category=ScenarioCategory.FACTOR,
            shocks=(FactorShock(EquitySpot("SPY"), -0.01),),
        ),
    )
    with pytest.raises(TypeError):
        shocked.equity_spots["SPY"] = 1.0  # type: ignore[index]
