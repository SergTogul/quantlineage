"""R0.4.2-F: DEFAULT/THREAT libraries and persistence store canonical Scenario.

In-code libraries are broadcast templates (not StressScenario) expanded at
apply time against the live MarketSnapshot — same pattern as
``crisis_scenarios(base)``. Persistence save/get/list_all round-trip
``Scenario`` (ScenarioWire JSON). HTTP DI returns ``Scenario``.
"""

from __future__ import annotations

from typing import get_type_hints

import pytest
from fastapi.testclient import TestClient

from app.api.scenario_wire import scenario_to_wire, wire_to_scenario
from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.persistence.memory_repos import InMemoryScenarioDefinitionRepository
from app.persistence.models import ScenarioDefinitionRow
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import SqlAlchemyScenarioDefinitionRepository
from app.persistence.testing import make_sqlite_session_factory
from app.persistence.wiring import default_seed_scenarios
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.crisis_library import CRISIS_LIBRARY, crisis_scenarios
from app.risk.factor_types import EquitySpot
from app.risk.scenario_model import (
    Scenario,
    apply_scenario,
    scenario_from_stress,
    to_canonical_scenario,
)
from app.risk.stress import (
    DEFAULT_SCENARIOS,
    HYPOTHETICAL_THREAT_SCENARIOS,
    THREAT_SCENARIOS,
    StressEngine,
)
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

PRICING = BuiltinPricingEngine()
ENGINE = StressEngine()

REQUIRED_DEFAULT_IDS = (
    "eq_down_10",
    "rates_up_100",
    "vol_up_25",
    "eq_down_vol_up",
    "combined_crisis",
)


def _live_market() -> MarketSnapshot:
    """Snapshot whose names are not the demo book — must still receive macros."""
    return MarketSnapshot(
        id="live-broadcast",
        as_of="2024-01-02",
        equity_spots={"NEWEQ": 50.0, "SPY": 100.0},
        equity_vols={"NEWEQ": 0.25},
        rates={"USD": 0.04},
    )


def _legacy_eq_down() -> StressScenario:
    """Today's eq_down_10 StressScenario shape (identity reference, not the library)."""
    return StressScenario(
        id="eq_down_10",
        name="Equities -10%",
        description="Broad equity selloff with other factors unchanged.",
        kind=ScenarioKind.FACTOR,
        equity_shock=-0.10,
        max_loss_pct=0.06,
    )


def test_default_library_ids_unchanged():
    assert tuple(s.id for s in DEFAULT_SCENARIOS) == REQUIRED_DEFAULT_IDS


def test_default_and_threat_libraries_are_not_stress_scenario():
    for item in list(DEFAULT_SCENARIOS) + list(THREAT_SCENARIOS) + list(
        HYPOTHETICAL_THREAT_SCENARIOS
    ):
        assert not isinstance(item, StressScenario), type(item)


def test_eq_down_broadcast_expands_onto_live_snapshot_names():
    """Macros must not freeze demo equity names at import."""
    market = _live_market()
    formal = to_canonical_scenario(DEFAULT_SCENARIOS[0], market)
    assert isinstance(formal, Scenario)
    symbols = {
        shock.factor.symbol
        for shock in formal.shocks
        if isinstance(shock.factor, EquitySpot)
    }
    assert "NEWEQ" in symbols
    assert "SPY" in symbols


def test_default_expansion_matches_legacy_stress_content_hash_and_pnl():
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    legacy = _legacy_eq_down()
    from_library = to_canonical_scenario(DEFAULT_SCENARIOS[0], market)
    from_legacy = scenario_from_stress(legacy, market)
    assert apply_scenario(market, from_library).content_hash() == apply_scenario(
        market, from_legacy
    ).content_hash()
    lib_pnl = ENGINE.run(SAMPLE_PORTFOLIO, PRICING, [DEFAULT_SCENARIOS[0]], market=market)
    leg_pnl = ENGINE.run(SAMPLE_PORTFOLIO, PRICING, [legacy], market=market)
    assert lib_pnl[0].pnl == pytest.approx(leg_pnl[0].pnl, abs=1e-12)


def test_threat_templates_expand_like_crisis_scenarios():
    market = _live_market()
    crisis = crisis_scenarios(market)
    threat = [to_canonical_scenario(item, market) for item in THREAT_SCENARIOS]
    crisis_ids = [c.id for c in CRISIS_LIBRARY]
    assert [s.id for s in threat[: len(crisis_ids)]] == crisis_ids
    for formal, expected in zip(threat[: len(crisis)], crisis, strict=True):
        assert apply_scenario(market, formal).content_hash() == apply_scenario(
            market, expected
        ).content_hash()


def test_memory_repo_round_trips_scenario():
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    original = to_canonical_scenario(DEFAULT_SCENARIOS[0], market)
    repo = InMemoryScenarioDefinitionRepository()
    saved = repo.save(original)
    assert isinstance(saved, Scenario)
    loaded = repo.get(original.id)
    assert isinstance(loaded, Scenario)
    assert loaded.id == original.id
    assert loaded.name == original.name
    assert loaded.shocks == original.shocks
    listed = repo.list_all()
    assert len(listed) == 1
    assert isinstance(listed[0], Scenario)
    wire = scenario_to_wire(loaded)
    assert wire_to_scenario(wire).shocks == original.shocks


def test_sqlalchemy_repo_round_trips_scenario_wire_payload():
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    original = to_canonical_scenario(DEFAULT_SCENARIOS[1], market)
    factory = make_sqlite_session_factory()
    with session_scope(factory) as session:
        repo = SqlAlchemyScenarioDefinitionRepository(session)
        saved = repo.save(original)
        assert isinstance(saved, Scenario)
        assert saved.id == original.id
        loaded = repo.get(original.id)
        assert isinstance(loaded, Scenario)
        assert loaded.shocks == original.shocks
        listed = repo.list_all()
        assert len(listed) == 1
        assert isinstance(listed[0], Scenario)
        row = session.get(ScenarioDefinitionRow, original.id)
        assert row is not None
        assert "shocks" in row.definition
        assert "category" in row.definition
        assert "equity_shock" not in row.definition


def test_default_seed_scenarios_are_canonical_scenario():
    seeded = default_seed_scenarios()
    assert seeded
    assert all(isinstance(s, Scenario) for s in seeded)
    assert {s.id for s in seeded} >= set(REQUIRED_DEFAULT_IDS)
    assert "lehman_2008" in {s.id for s in seeded}
    assert "stagflation" in {s.id for s in seeded}


def test_http_di_returns_scenario_not_stress_scenario():
    from app.api.deps import get_baseline_stress_scenarios, get_default_stress_scenarios

    hints = get_type_hints(get_default_stress_scenarios)
    assert hints["return"] == list[Scenario]
    baseline = get_type_hints(get_baseline_stress_scenarios)
    assert baseline["return"] == list[Scenario]


def test_http_list_and_stress_identity_with_lifespan():
    from app.main import app

    with TestClient(app) as client:
        listed = client.get("/risk/stress/scenarios")
        assert listed.status_code == 200
        body = listed.json()
        ids = {row["id"] for row in body}
        assert set(REQUIRED_DEFAULT_IDS) <= ids
        assert "equity_shock" not in body[0]
        assert "shocks" in body[0]
        resp = client.post(
            "/risk/stress",
            json=SAMPLE_PORTFOLIO.model_dump(mode="json"),
        )
        assert resp.status_code == 200
        names = [row["scenario"] for row in resp.json()]
        assert names == [s.name for s in DEFAULT_SCENARIOS]
