"""M5.9: stress HTTP loads scenario definitions via DI (fallback THREAT / DEFAULT)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.models import ScenarioKind, StressScenario
from app.persistence.memory_repos import InMemoryScenarioDefinitionRepository
from app.persistence.wiring import default_seed_scenarios
from app.risk.stress import DEFAULT_SCENARIOS, THREAT_SCENARIOS
from app.sample import SAMPLE_PORTFOLIO


@pytest.fixture
def clear_db_url(monkeypatch):
    monkeypatch.delenv("RISKFORGE_DATABASE_URL", raising=False)


def test_get_stress_scenarios_from_memory_repo(clear_db_url):
    """Unset DATABASE_URL → GET serves seeded in-memory scenario_definition_repo."""
    from app.main import app

    expected_ids = {s.id for s in default_seed_scenarios()}
    with TestClient(app) as client:
        resp = client.get("/risk/stress/scenarios")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == len(expected_ids)
        assert {row["id"] for row in body} == expected_ids
        # Seeded set is DEFAULT + THREAT (larger than legacy in-code threat list alone).
        assert len(body) > len(THREAT_SCENARIOS)


def test_get_stress_scenarios_from_sqlalchemy(monkeypatch, tmp_path):
    """DATABASE_URL set → GET serves SQLAlchemy scenario_definitions."""
    monkeypatch.setenv("RISKFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'm59_scenarios.db'}")
    from app.main import app

    expected_ids = {s.id for s in default_seed_scenarios()}
    with TestClient(app) as client:
        assert client.app.state.persistence_enabled is True
        resp = client.get("/risk/stress/scenarios")
        assert resp.status_code == 200
        body = resp.json()
        assert {row["id"] for row in body} == expected_ids


def test_get_stress_scenarios_reflects_repo_save(clear_db_url):
    """Saving into DI repo is visible on GET /risk/stress/scenarios."""
    from app.main import app

    custom = StressScenario(
        id="m59_custom_shock",
        name="M59 Custom",
        description="Injected via scenario_definition_repo",
        kind=ScenarioKind.CUSTOM,
        equity_shock=-0.33,
        max_loss_pct=0.2,
    )
    with TestClient(app) as client:
        repo = client.app.state.scenario_definition_repo
        assert repo is not None
        repo.save(custom)
        resp = client.get("/risk/stress/scenarios")
        assert resp.status_code == 200
        ids = {row["id"] for row in resp.json()}
        assert "m59_custom_shock" in ids


def test_get_stress_scenarios_falls_back_to_threat_when_repo_empty(clear_db_url):
    """Empty scenario repo → in-code THREAT_SCENARIOS fallback."""
    from app.api.deps import get_stress_scenario_definition_repository
    from app.main import app

    empty = InMemoryScenarioDefinitionRepository()

    def _empty_repo():
        return empty

    app.dependency_overrides[get_stress_scenario_definition_repository] = _empty_repo
    try:
        with TestClient(app) as client:
            resp = client.get("/risk/stress/scenarios")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == len(THREAT_SCENARIOS)
            assert {row["id"] for row in body} == {s.id for s in THREAT_SCENARIOS}
    finally:
        app.dependency_overrides.pop(get_stress_scenario_definition_repository, None)


def test_evaluate_defaults_use_di_scenarios(clear_db_url):
    """POST /risk/stress/evaluate uses DI scenario list (not hard-coded THREAT only)."""
    from app.main import app

    custom = StressScenario(
        id="m59_eval_only",
        name="M59 Eval Only",
        description="Must appear in default evaluate when DI-backed",
        kind=ScenarioKind.CUSTOM,
        equity_shock=-0.99,
        max_loss_pct=0.5,
    )
    with TestClient(app) as client:
        client.app.state.scenario_definition_repo.save(custom)
        resp = client.post(
            "/risk/stress/evaluate",
            json=SAMPLE_PORTFOLIO.model_dump(mode="json"),
        )
        assert resp.status_code == 200
        names = {ev["scenario"] for ev in resp.json()["evaluations"]}
        assert "M59 Eval Only" in names


def test_post_stress_uses_di_default_subset(clear_db_url):
    """POST /risk/stress uses DI DEFAULT subset (not in-code-only; not full THREAT set)."""
    from app.main import app

    # Persist an override for a DEFAULT id — stress endpoint must pick it up.
    overridden = DEFAULT_SCENARIOS[0].model_copy(
        update={
            "name": "M59 DI Equities Override",
            "equity_shock": -0.42,
        }
    )
    with TestClient(app) as client:
        client.app.state.scenario_definition_repo.save(overridden)
        resp = client.post(
            "/risk/stress",
            json=SAMPLE_PORTFOLIO.model_dump(mode="json"),
        )
        assert resp.status_code == 200
        names = [row["scenario"] for row in resp.json()]
        assert "M59 DI Equities Override" in names
        # Baseline set size stays DEFAULT (threat/crisis rows excluded).
        assert len(names) == len(DEFAULT_SCENARIOS)
        threat_names = {s.name for s in THREAT_SCENARIOS}
        assert not threat_names.intersection(names)


def test_post_stress_falls_back_to_default_when_repo_empty(clear_db_url):
    """Empty repo → GET/evaluate fall back to THREAT; POST /risk/stress → DEFAULT."""
    from app.api.deps import get_stress_scenario_definition_repository
    from app.main import app

    empty = InMemoryScenarioDefinitionRepository()

    def _empty_repo():
        return empty

    app.dependency_overrides[get_stress_scenario_definition_repository] = _empty_repo
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/risk/stress",
                json=SAMPLE_PORTFOLIO.model_dump(mode="json"),
            )
            assert resp.status_code == 200
            names = [row["scenario"] for row in resp.json()]
            assert names == [s.name for s in DEFAULT_SCENARIOS]
    finally:
        app.dependency_overrides.pop(get_stress_scenario_definition_repository, None)


def test_stress_endpoints_fallback_without_lifespan(clear_db_url):
    """Legacy TestClient without lifespan: no 503; honest in-code fallbacks."""
    from app.main import app

    # Prior tests may leave lifespan state on the shared app; clear for this case.
    for attr in (
        "scenario_definition_repo",
        "market_snapshot_repo",
        "limit_definition_repo",
        "session_factory",
        "persistence_enabled",
        "risk_run_worker",
    ):
        if hasattr(app.state, attr):
            delattr(app.state, attr)

    client = TestClient(app)
    assert getattr(client.app.state, "scenario_definition_repo", None) is None

    scenarios = client.get("/risk/stress/scenarios")
    assert scenarios.status_code == 200
    assert {row["id"] for row in scenarios.json()} == {s.id for s in THREAT_SCENARIOS}

    stress = client.post(
        "/risk/stress",
        json=SAMPLE_PORTFOLIO.model_dump(mode="json"),
    )
    assert stress.status_code == 200
    assert [row["scenario"] for row in stress.json()] == [s.name for s in DEFAULT_SCENARIOS]
