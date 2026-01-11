"""M3.3 historical crisis library tests.

Conventions:
- Crisis presets are HISTORICAL_APPROXIMATION only (never exact replay claims).
- Observation-derived scenarios are HISTORICAL_REPLAY with observation_index.
- Shock units match StressScenario / MarketSnapshot.bump.
- Empty / zero template → content_hash unchanged when expanded against base.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.models import MarketSnapshot, ScenarioKind
from app.market.snapshot import shock_snapshot
from app.risk.crisis_library import (
    APPROXIMATION_DISCLAIMER,
    CRISIS_BY_ID,
    CRISIS_LIBRARY,
    CRISIS_STRESS_SCENARIOS,
    REPLAY_DISCLAIMER,
    CrisisDefinition,
    CrisisShockTemplate,
    apply_crisis,
    assert_honest_historical_labeling,
    crisis_as_stress,
    crisis_scenario,
    crisis_scenarios,
    get_crisis,
    is_historical_approximation,
    is_historical_replay,
    replay_scenarios_from_observations,
)
from app.risk.historical_data import FactorObservationSeries
from app.risk.scenario_model import (
    Scenario,
    ScenarioCategory,
    ScenarioSeverity,
    ScenarioThreshold,
    apply_scenario,
)
from app.risk.stress import HYPOTHETICAL_THREAT_SCENARIOS, THREAT_SCENARIOS

REQUIRED_CRISIS_IDS = {
    "lehman_2008",
    "covid_2020_03",
    "rates_shock_2022",
    "euro_crisis_2011",
    "volmageddon_2018",
    "china_shock_2015",
    "dotcom_equity_crash",
}


def _base() -> MarketSnapshot:
    return MarketSnapshot(
        id="base",
        equity_spots={"SPY": 100.0, "NVDA": 200.0},
        equity_vols={"SPY": 0.20},
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.12},
        rates={"USD": 0.04, "EUR": 0.03},
    )


def test_library_contains_required_named_crises():
    assert {c.id for c in CRISIS_LIBRARY} == REQUIRED_CRISIS_IDS
    assert set(CRISIS_BY_ID) == REQUIRED_CRISIS_IDS


def test_every_crisis_is_historical_approximation_not_replay():
    base = _base()
    for defn in CRISIS_LIBRARY:
        formal = crisis_scenario(defn, base)
        assert formal.category == ScenarioCategory.HISTORICAL_APPROXIMATION
        assert is_historical_approximation(formal)
        assert not is_historical_replay(formal)
        assert formal.metadata["exact_replay"] is False
        assert formal.metadata["labeling"] == "historical_approximation"
        assert APPROXIMATION_DISCLAIMER in formal.description
        assert "not an exact replay" in formal.description.lower() or "not a" in formal.description.lower()
        assert_honest_historical_labeling(formal)


def test_crisis_descriptions_never_claim_exact_replay():
    """Approximations may *deny* exact replay; they must not affirm it."""
    for defn in CRISIS_LIBRARY:
        lower = defn.description.lower()
        # Affirmative (bad): "exact replay of …" without a preceding "not"/"never"
        assert "tick-for-tick" not in lower
        if "exact replay" in lower:
            assert "not an exact replay" in lower or ("not a" in lower and "replay" in lower)
        assert "approx" in defn.name.lower() or "approximation" in defn.description.lower()
        assert_honest_historical_labeling(crisis_scenario(defn, _base()))


def test_crisis_as_stress_preserves_aggregate_moves():
    defn = get_crisis("lehman_2008")
    stress = crisis_as_stress(defn)
    assert stress.id == "lehman_2008"
    assert stress.kind == ScenarioKind.HISTORICAL_STYLE
    assert stress.equity_shock == pytest.approx(-0.35)
    assert stress.vol_shock == pytest.approx(1.00)
    assert stress.rates_shift_bps == pytest.approx(-100.0)
    assert stress.fx_shock == pytest.approx(-0.05)
    assert stress.max_loss_pct == pytest.approx(0.15)


def test_formal_crisis_matches_legacy_shock_snapshot():
    base = _base()
    defn = get_crisis("covid_2020_03")
    formal = crisis_scenario(defn, base)
    via_formal = apply_scenario(base, formal)
    via_legacy = shock_snapshot(base, crisis_as_stress(defn))
    assert via_formal.content_hash() == via_legacy.content_hash()
    assert via_formal.equity_spots["SPY"] == pytest.approx(70.0)
    assert via_formal.equity_vols["SPY"] == pytest.approx(0.50)  # 0.20 * (1+1.5)


def test_apply_crisis_is_deterministic():
    base = _base()
    a = apply_crisis(base, "volmageddon_2018")
    b = apply_crisis(base, "volmageddon_2018")
    assert a.content_hash() == b.content_hash()
    assert a.equity_spots["SPY"] == pytest.approx(90.0)
    assert a.equity_vols["SPY"] == pytest.approx(0.60)  # 0.20 * (1+2.0)
    # Independent of other crises (not cumulative)
    assert base.equity_spots["SPY"] == 100.0


def test_zero_shock_crisis_is_noop_on_marks():
    base = _base()
    empty = CrisisDefinition(
        id="empty_crisis",
        name="Empty (approx)",
        episode="n/a",
        description=f"{APPROXIMATION_DISCLAIMER} Zero-move control.",
        shocks=CrisisShockTemplate(),
        threshold=ScenarioThreshold(max_loss_pct=0.01),
        severity=ScenarioSeverity.LOW,
    )
    formal = crisis_scenario(empty, base)
    assert formal.is_empty or all(s.amount == 0.0 for s in formal.shocks)
    shocked = apply_scenario(base, formal)
    assert shocked.content_hash() == base.content_hash()


def test_observation_replays_are_not_crisis_approximations():
    base = _base()
    series = FactorObservationSeries(
        equity_returns=np.array([-0.10, 0.05]),
        vol_moves=np.array([0.25, 0.0]),
        rate_moves_bps=np.array([50.0, -25.0]),
        fx_returns=np.array([-0.05, 0.01]),
    )
    replays = replay_scenarios_from_observations(base, series)
    assert len(replays) == 2
    for s in replays:
        assert s.category == ScenarioCategory.HISTORICAL_REPLAY
        assert is_historical_replay(s)
        assert not is_historical_approximation(s)
        assert s.metadata["exact_replay"] is True
        assert "observation_index" in s.metadata
        assert REPLAY_DISCLAIMER in s.metadata["disclaimer"]
        assert_honest_historical_labeling(s)


def test_assert_honest_labeling_rejects_approximation_claiming_exact_replay():
    bad = Scenario(
        id="fake",
        name="Fake",
        category=ScenarioCategory.HISTORICAL_APPROXIMATION,
        description="stylized approx",
        metadata={"exact_replay": True},
    )
    with pytest.raises(ValueError, match="exact_replay"):
        assert_honest_historical_labeling(bad)


def test_threat_scenarios_include_crisis_library_then_hypotheticals():
    crisis_ids = [s.id for s in CRISIS_STRESS_SCENARIOS]
    threat_ids = [s.id for s in THREAT_SCENARIOS]
    assert threat_ids[: len(crisis_ids)] == crisis_ids
    assert "stagflation" in threat_ids
    assert all(s.id in threat_ids for s in HYPOTHETICAL_THREAT_SCENARIOS)
    # Named historical proxies no longer use ambiguous MACRO for crises
    for s in CRISIS_STRESS_SCENARIOS:
        assert s.kind == ScenarioKind.HISTORICAL_STYLE
        assert APPROXIMATION_DISCLAIMER.split("—")[0].strip() in s.description or "APPROXIMATION" in s.description


def test_crisis_scenarios_expand_all_against_base():
    base = _base()
    scenarios = crisis_scenarios(base)
    assert len(scenarios) == len(CRISIS_LIBRARY)
    hashes = [apply_scenario(base, s).content_hash() for s in scenarios]
    # Distinct episodes should generally produce distinct shocked markets
    assert len(set(hashes)) == len(hashes)


def test_get_crisis_unknown_raises():
    with pytest.raises(KeyError, match="unknown crisis"):
        get_crisis("not_a_real_crisis")


def test_rates_shock_2022_moves_rates_up_not_equity_crash_only():
    base = _base()
    shocked = apply_crisis(base, "rates_shock_2022")
    assert shocked.rates["USD"] == pytest.approx(0.04 + 0.025)
    assert shocked.equity_spots["SPY"] == pytest.approx(82.0)


def test_euro_crisis_applies_fx_weakness():
    base = _base()
    shocked = apply_crisis(base, "euro_crisis_2011")
    assert shocked.fx_spots["EURUSD"] == pytest.approx(1.10 * (1.0 - 0.12))
