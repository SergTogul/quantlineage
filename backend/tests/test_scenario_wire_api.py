"""M3.8 formal Scenario HTTP wire — adapters + API contracts.

Numerical equivalence: formal wire → ``scenario_to_stress`` → StressEngine
must match legacy ``StressScenario`` custom endpoints for the same shocks.
No PricingEngine / VaR math changes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.scenario_wire import (
    FactorShockWire,
    ScenarioWire,
    scenario_to_wire,
    stress_to_wire,
    wire_to_scenario,
    wire_to_stress,
)
from app.domain.models import MarketSnapshot, StressScenario
from app.main import app
from app.market.snapshot import shock_snapshot
from app.risk.factor_types import EquitySpot, EquityVol, RateZero
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    ScenarioCategory,
    ScenarioThreshold,
    apply_scenario,
    scenario_from_stress,
)
from app.sample import SAMPLE_PORTFOLIO

client = TestClient(app)


def _base() -> MarketSnapshot:
    return MarketSnapshot(
        id="base",
        equity_spots={"SPY": 100.0},
        equity_vols={"SPY": 0.20},
        fx_spots={},
        fx_vols={},
        rates={"USD": 0.04},
    )


def test_wire_round_trip_preserves_shocks():
    formal = Scenario(
        id="rt",
        name="Round trip",
        category=ScenarioCategory.FACTOR,
        shocks=(
            FactorShock(EquitySpot("SPY"), -0.10),
            FactorShock(EquityVol(underlying="SPY"), 0.25),
            FactorShock(RateZero("USD", "ALL"), 0.005),
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.05),
    )
    wire = scenario_to_wire(formal)
    back = wire_to_scenario(wire)
    assert back.id == formal.id
    assert back.category == formal.category
    assert back.threshold.max_loss_pct == pytest.approx(0.05)
    assert len(back.shocks) == 3
    assert apply_scenario(_base(), back).content_hash() == apply_scenario(
        _base(), formal
    ).content_hash()


def test_wire_to_stress_matches_legacy_named_dicts():
    wire = ScenarioWire(
        id="eq-vol",
        name="Equity vol",
        category=ScenarioCategory.FACTOR,
        shocks=[
            FactorShockWire(factor_type="equity", key="SPY", amount=-0.10, bucket="SPY"),
            FactorShockWire(
                factor_type="vol", key="SPY:VOL", amount=0.25, bucket="SPY"
            ),
        ],
        max_loss_pct=0.02,
    )
    stress = wire_to_stress(wire)
    assert stress.equity_shocks["SPY"] == pytest.approx(-0.10)
    assert stress.vol_shocks["SPY"] == pytest.approx(0.25)
    assert stress.max_loss_pct == pytest.approx(0.02)
    base = _base()
    formal_hash = apply_scenario(base, wire_to_scenario(wire)).content_hash()
    legacy_hash = shock_snapshot(base, stress).content_hash()
    assert formal_hash == legacy_hash


def test_stress_to_wire_via_base_expansion():
    legacy = StressScenario(
        id="crash",
        name="Crash",
        equity_shock=-0.20,
        vol_shock=0.40,
        max_loss_pct=0.08,
    )
    wire = stress_to_wire(legacy, _base())
    assert wire.id == "crash"
    assert wire.category == ScenarioCategory.FACTOR
    assert any(s.factor_type == "equity" and s.amount == pytest.approx(-0.20) for s in wire.shocks)
    formal = scenario_from_stress(legacy, _base())
    assert apply_scenario(_base(), wire_to_scenario(wire)).content_hash() == apply_scenario(
        _base(), formal
    ).content_hash()


def test_formal_custom_stress_api_matches_legacy_pnl():
    portfolio = client.get("/api/v1/portfolio").json()
    legacy_payload = {
        "portfolio": portfolio,
        "scenarios": [
            {
                "name": "Custom",
                "id": "custom-legacy",
                "equity_shocks": {"SPY": -0.10},
                "vol_shocks": {"SPY": 0.25},
                "max_loss_pct": 0.05,
            }
        ],
    }
    formal_payload = {
        "portfolio": portfolio,
        "scenarios": [
            {
                "id": "custom-legacy",
                "name": "Custom",
                "category": "factor",
                "shocks": [
                    {
                        "factor_type": "equity",
                        "key": "SPY",
                        "amount": -0.10,
                        "bucket": "SPY",
                    },
                    {
                        "factor_type": "vol",
                        "key": "SPY:VOL",
                        "amount": 0.25,
                        "bucket": "SPY",
                    },
                ],
                "max_loss_pct": 0.05,
            }
        ],
    }
    legacy = client.post("/api/v1/risk/stress/custom", json=legacy_payload)
    formal = client.post("/api/v1/risk/stress/formal/custom", json=formal_payload)
    assert legacy.status_code == 200
    assert formal.status_code == 200
    assert formal.json()[0]["scenario"] == "Custom"
    assert formal.json()[0]["pnl"] == pytest.approx(legacy.json()[0]["pnl"], rel=0, abs=1e-9)


def test_formal_evaluate_custom_api_contract():
    portfolio = client.get("/api/v1/portfolio").json()
    payload = {
        "portfolio": portfolio,
        "scenarios": [
            {
                "id": "threat-formal",
                "name": "Formal threat",
                "category": "hypothetical",
                "shocks": [
                    {
                        "factor_type": "equity",
                        "key": "SPY",
                        "amount": -0.15,
                        "bucket": "SPY",
                    }
                ],
                "max_loss_pct": 0.02,
            }
        ],
    }
    response = client.post("/api/v1/risk/stress/formal/evaluate/custom", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_id"] == portfolio["id"]
    assert body["evaluations"][0]["scenario"] == "Formal threat"


def test_get_scenarios_formal_returns_wire_shape():
    legacy = client.get("/api/v1/risk/stress/scenarios")
    formal = client.get("/api/v1/risk/stress/scenarios/formal")
    assert legacy.status_code == 200
    assert formal.status_code == 200
    assert len(formal.json()) == len(legacy.json())
    row = formal.json()[0]
    assert "category" in row
    assert "shocks" in row
    assert isinstance(row["shocks"], list)
    assert "id" in row and "name" in row


def test_legacy_custom_stress_unchanged():
    """Regression: M3.8 must not break StressScenario custom evaluate."""
    portfolio = SAMPLE_PORTFOLIO.model_dump(mode="json")
    payload = {
        "portfolio": portfolio,
        "scenarios": [{"name": "Custom", "equity_shock": -0.1, "max_loss_pct": 0.02}],
    }
    response = client.post("/api/v1/risk/stress/evaluate/custom", json=payload)
    assert response.status_code == 200
    assert response.json()["evaluations"][0]["scenario"] == "Custom"
