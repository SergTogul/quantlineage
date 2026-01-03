"""M3.1 formal Scenario domain model tests.

Conventions:
- Shock units match ``MarketSnapshot.bump`` (relative spots/vols; decimal rates).
- Severity bands match StressEngine threat levels (3% / 8% / 15% of |NAV|).
- Empty / zero shocks leave ``content_hash`` unchanged.
- Adapters preserve marks vs ``shock_snapshot`` / ``apply_market_scenario``.
"""

from __future__ import annotations

import pytest

from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.market.snapshot import shock_snapshot
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero
from app.risk.scenario_model import (
    SEVERITY_HIGH_MIN,
    SEVERITY_MODERATE_MIN,
    SEVERITY_SEVERE_MIN,
    FactorShock,
    Scenario,
    ScenarioCategory,
    ScenarioSeverity,
    ScenarioThreshold,
    apply_scenario,
    category_to_kind,
    classify_severity,
    compose_shocks,
    kind_to_category,
    scenario_from_market_scenario,
    scenario_from_stress,
    scenario_to_market_scenario,
    scenario_to_stress,
    threshold_breached,
)
from app.risk.scenarios import FactorChange, MarketScenario, apply_market_scenario


def _base() -> MarketSnapshot:
    return MarketSnapshot(
        id="base",
        equity_spots={"SPY": 100.0, "NVDA": 200.0},
        equity_vols={"SPY": 0.20},
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.12},
        rates={"USD": 0.04, "EUR": 0.03},
    )


def test_empty_scenario_zero_effect_on_marks():
    base = _base()
    scenario = Scenario(
        id="empty",
        name="Empty",
        category=ScenarioCategory.CUSTOM,
        shocks=(),
    )
    assert scenario.is_empty
    shocked = apply_scenario(base, scenario)
    assert shocked.content_hash() == base.content_hash()
    assert shocked.id == "base:empty"


def test_zero_amount_shocks_are_empty_and_noop():
    base = _base()
    scenario = Scenario(
        id="zeros",
        name="Zeros",
        category=ScenarioCategory.FACTOR,
        shocks=(FactorShock(EquitySpot("SPY"), 0.0),),
    )
    assert scenario.is_empty
    assert apply_scenario(base, scenario).content_hash() == base.content_hash()


def test_factor_shocks_reference_typed_risk_factors():
    shock = FactorShock(EquitySpot("NVDA"), -0.10)
    assert isinstance(shock.factor, EquitySpot)
    assert shock.factor.key == "NVDA"
    assert shock.factor.factor_type == "equity"
    assert shock.as_pair() == (EquitySpot("NVDA"), -0.10)
    assert shock.as_factor_change() == FactorChange(EquitySpot("NVDA"), -0.10)


def test_apply_scenario_order_is_deterministic():
    base = _base()
    scenario = Scenario(
        id="multi",
        name="Multi",
        category=ScenarioCategory.MACRO,
        description="equity then vol then rates",
        shocks=(
            FactorShock(EquitySpot("SPY"), -0.10),
            FactorShock(EquityVol(underlying="SPY"), 0.25),
            FactorShock(RateZero("USD", "ALL"), 0.01),
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.05),
        severity=ScenarioSeverity.HIGH,
        metadata={"source": "unit_test"},
    )
    a = apply_scenario(base, scenario)
    b = apply_scenario(base, scenario)
    assert a.content_hash() == b.content_hash()
    assert a.equity_spots["SPY"] == pytest.approx(90.0)
    assert a.equity_vols["SPY"] == pytest.approx(0.25)
    assert a.rates["USD"] == pytest.approx(0.05)
    assert a.equity_spots["NVDA"] == 200.0  # untouched
    assert scenario.metadata["source"] == "unit_test"
    with pytest.raises(TypeError):
        scenario.metadata["source"] = "mutated"  # type: ignore[index]


def test_compose_shocks_preserves_call_order():
    first = (FactorShock(EquitySpot("SPY"), -0.05),)
    second = (FactorShock(EquitySpot("SPY"), -0.05),)  # sequential relative shocks
    composed = compose_shocks(first, second)
    assert [s.amount for s in composed] == [-0.05, -0.05]
    base = _base()
    out = apply_scenario(
        base,
        Scenario(id="seq", name="Seq", category=ScenarioCategory.FACTOR, shocks=composed),
    )
    # 100 * 0.95 * 0.95
    assert out.equity_spots["SPY"] == pytest.approx(90.25)


def test_severity_classification_boundaries():
    assert classify_severity(0.0) == ScenarioSeverity.LOW
    assert classify_severity(SEVERITY_MODERATE_MIN - 1e-12) == ScenarioSeverity.LOW
    assert classify_severity(SEVERITY_MODERATE_MIN) == ScenarioSeverity.MODERATE
    assert classify_severity(SEVERITY_HIGH_MIN - 1e-12) == ScenarioSeverity.MODERATE
    assert classify_severity(SEVERITY_HIGH_MIN) == ScenarioSeverity.HIGH
    assert classify_severity(SEVERITY_SEVERE_MIN - 1e-12) == ScenarioSeverity.HIGH
    assert classify_severity(SEVERITY_SEVERE_MIN) == ScenarioSeverity.SEVERE
    assert classify_severity(1.0) == ScenarioSeverity.SEVERE


def test_threshold_breach_boundaries():
    thr = ScenarioThreshold(max_loss_pct=0.05)
    assert not threshold_breached(0.05, thr)  # must exceed, not equal
    assert threshold_breached(0.0500001, thr)
    assert not threshold_breached(0.99, None)
    assert not threshold_breached(0.99, ScenarioThreshold())
    with pytest.raises(ValueError):
        ScenarioThreshold(max_loss_pct=0.0)


def test_scenario_requires_id_and_name():
    with pytest.raises(ValueError):
        Scenario(id="", name="x", category=ScenarioCategory.CUSTOM)
    with pytest.raises(ValueError):
        Scenario(id="x", name="", category=ScenarioCategory.CUSTOM)


def test_category_kind_round_trip_mapping():
    assert category_to_kind(ScenarioCategory.FACTOR) == ScenarioKind.FACTOR
    assert category_to_kind(ScenarioCategory.HYPOTHETICAL) == ScenarioKind.MACRO
    assert category_to_kind(ScenarioCategory.HISTORICAL_REPLAY) == ScenarioKind.HISTORICAL_STYLE
    assert kind_to_category(ScenarioKind.HISTORICAL_STYLE) == ScenarioCategory.HISTORICAL_APPROXIMATION
    assert (
        kind_to_category(
            ScenarioKind.HISTORICAL_STYLE,
            historical_as=ScenarioCategory.HISTORICAL_REPLAY,
        )
        == ScenarioCategory.HISTORICAL_REPLAY
    )


def test_adapter_stress_round_trip_matches_shock_snapshot():
    base = _base()
    legacy = StressScenario(
        id="eq_vol",
        name="Equities -10% / Vol +25%",
        description="risk-off",
        kind=ScenarioKind.MACRO,
        equity_shock=-0.10,
        vol_shock=0.25,
        rates_shift_bps=50,
        max_loss_pct=0.08,
    )
    formal = scenario_from_stress(legacy, base)
    assert formal.id == "eq_vol"
    assert formal.category == ScenarioCategory.MACRO
    assert formal.threshold.max_loss_pct == pytest.approx(0.08)
    assert formal.shocks
    assert all(
        isinstance(s.factor, (EquitySpot, EquityVol, FXSpot, FXVol, RateZero)) for s in formal.shocks
    )
    types = {type(s.factor).__name__ for s in formal.shocks}
    assert "EquitySpot" in types
    assert "EquityVol" in types
    assert "FXVol" in types  # vol_shock broadcasts to FX vols present in base
    assert "RateZero" in types

    via_formal = apply_scenario(base, formal)
    via_legacy = shock_snapshot(base, scenario_to_stress(formal))
    assert via_formal.equity_spots == via_legacy.equity_spots
    assert via_formal.equity_vols == via_legacy.equity_vols
    assert via_formal.fx_spots == via_legacy.fx_spots
    assert via_formal.fx_vols == via_legacy.fx_vols
    assert via_formal.rates == via_legacy.rates
    # Also matches applying the original StressScenario
    via_original = shock_snapshot(base, legacy)
    assert via_formal.content_hash() == via_original.content_hash()


def test_adapter_named_dict_shocks_not_broadcast():
    base = _base()
    legacy = StressScenario(
        id="nvda_only",
        name="NVDA only",
        equity_shocks={"NVDA": -0.20},
        max_loss_pct=0.02,
    )
    formal = scenario_from_stress(legacy, base)
    assert len([s for s in formal.shocks if isinstance(s.factor, EquitySpot)]) == 1
    shocked = apply_scenario(base, formal)
    assert shocked.equity_spots["NVDA"] == pytest.approx(160.0)
    assert shocked.equity_spots["SPY"] == 100.0


def test_adapter_market_scenario_round_trip():
    base = _base()
    market = MarketScenario(
        id="hist_1",
        name="Historical observation 1",
        shocks=(
            FactorChange(EquitySpot("SPY"), -0.10),
            FactorChange(RateZero("USD", "ALL"), 0.005),
        ),
        kind=ScenarioKind.HISTORICAL_STYLE,
        description="replay",
        observation_index=1,
    )
    formal = scenario_from_market_scenario(market)
    assert formal.category == ScenarioCategory.HISTORICAL_REPLAY
    assert formal.metadata["observation_index"] == 1
    back = scenario_to_market_scenario(formal)
    assert back.id == market.id
    assert back.observation_index == 1
    assert apply_scenario(base, formal).content_hash() == apply_market_scenario(base, market).content_hash()


def test_legacy_stress_api_shape_unchanged_for_minimal_payload():
    """Existing API clients can still construct StressScenario with only name + scalars."""
    s = StressScenario(name="Custom", equity_shock=-0.1, max_loss_pct=0.02)
    assert s.id is None
    assert s.kind == ScenarioKind.FACTOR
    formal = scenario_from_stress(s, _base())
    assert formal.id == "Custom"
    assert formal.threshold.max_loss_pct == pytest.approx(0.02)
