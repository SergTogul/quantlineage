"""M3.8 / R0.4.2-C formal Scenario HTTP wire — adapters + API contracts.

Formal wire → domain ``Scenario`` → StressEngine (native apply). Parity:
formal custom stress P&L must match legacy ``StressScenario`` custom endpoints
for the same shocks. ``wire_to_stress`` remains an adapter for tests/migration.

R0.4.2-C: ``GET /risk/stress/scenarios`` returns formal wire by default;
``/scenarios/formal`` is an identical alias.
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
    wires_to_scenarios,
)
from app.domain.models import MarketSnapshot, StressScenario
from app.main import app
from app.market.snapshot import shock_snapshot
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import EquitySpot, EquityVol, RateZero
from app.risk.scenario_engine import apply_scenario
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    ScenarioCategory,
    ScenarioThreshold,
    scenario_from_stress,
    scenario_to_stress,
)
from app.risk.stress import StressEngine
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


PRICING = BuiltinPricingEngine()
ENGINE = StressEngine()
SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)


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


def test_formal_custom_stress_api_matches_legacy_pnl(client):
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


def test_formal_evaluate_custom_api_contract(client):
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


def test_get_scenarios_default_is_formal_wire(client):
    """R0.4.2-C: GET /scenarios returns formal ScenarioWire, not StressScenario dicts."""
    response = client.get("/api/v1/risk/stress/scenarios")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 5
    row = body[0]
    assert "category" in row
    assert "shocks" in row
    assert isinstance(row["shocks"], list)
    assert "id" in row and "name" in row
    # Legacy StressScenario scalar fields must not be the list wire.
    assert "equity_shock" not in row
    assert "rates_shift_bps" not in row
    assert "vol_shock" not in row


def test_get_scenarios_formal_alias_matches_default(client):
    """R0.4.2-C: /scenarios/formal is an identical JSON alias of the default list."""
    default = client.get("/api/v1/risk/stress/scenarios")
    formal = client.get("/api/v1/risk/stress/scenarios/formal")
    assert default.status_code == 200
    assert formal.status_code == 200
    assert formal.json() == default.json()


def test_legacy_custom_stress_unchanged(client):
    """Regression: M3.8 must not break StressScenario custom evaluate."""
    portfolio = SAMPLE_PORTFOLIO.model_dump(mode="json")
    payload = {
        "portfolio": portfolio,
        "scenarios": [{"name": "Custom", "equity_shock": -0.1, "max_loss_pct": 0.02}],
    }
    response = client.post("/api/v1/risk/stress/evaluate/custom", json=payload)
    assert response.status_code == 200
    assert response.json()["evaluations"][0]["scenario"] == "Custom"


def test_formal_ui_style_evaluate_matches_legacy_scalar_pnl(client):
    """R0.4.2-D: UI-style formal expansion (all market factors) matches legacy scalars."""
    portfolio = client.get("/api/v1/portfolio").json()
    legacy_payload = {
        "portfolio": portfolio,
        "scenarios": [
            {
                "id": "ui_custom",
                "name": "Custom Crash",
                "kind": "custom",
                "equity_shock": -0.2,
                "vol_shock": 0.5,
                "rates_shift_bps": 100,
                "fx_shock": -0.05,
                "max_loss_pct": 0.1,
            }
        ],
    }
    from app.api.scenario_wire import stress_to_wire
    from app.domain.models import Portfolio, ScenarioKind, StressScenario
    from app.sample import demo_market_snapshot

    port = Portfolio.model_validate(portfolio)
    market = demo_market_snapshot(port)
    wire = stress_to_wire(
        StressScenario(
            id="ui_custom",
            name="Custom Crash",
            kind=ScenarioKind.CUSTOM,
            equity_shock=-0.2,
            vol_shock=0.5,
            rates_shift_bps=100,
            fx_shock=-0.05,
            max_loss_pct=0.1,
        ),
        market,
    )
    formal_payload = {
        "portfolio": portfolio,
        "scenarios": [wire.model_dump(mode="json")],
    }
    legacy = client.post("/api/v1/risk/stress/evaluate/custom", json=legacy_payload)
    formal = client.post(
        "/api/v1/risk/stress/formal/evaluate/custom", json=formal_payload
    )
    assert legacy.status_code == 200
    assert formal.status_code == 200
    le = legacy.json()["evaluations"][0]
    fe = formal.json()["evaluations"][0]
    assert fe["scenario"] == "Custom Crash"
    assert fe["pnl"] == pytest.approx(le["pnl"], rel=0, abs=1e-9)
    assert fe["loss"] == pytest.approx(le["loss"], rel=0, abs=1e-9)
    assert fe["threat_level"] == le["threat_level"]


def test_formal_compare_api_matches_legacy_pnl(client):
    """R0.4.2-D: POST /stress/formal/compare accepts ScenarioWire and matches legacy."""
    portfolio = client.get("/api/v1/portfolio").json()
    hedged = client.get("/api/v1/portfolio").json()
    for p in hedged["positions"]:
        if p.get("symbol") == "SPY" and p.get("type") == "equity":
            p["quantity"] = 0
            break
    legacy_body = {
        "portfolio": portfolio,
        "hedged_portfolio": hedged,
        "scenarios": [{"name": "Crash", "equity_shock": -0.2}],
        "methodology": "DELTA_GAMMA",
    }
    from app.api.scenario_wire import stress_to_wire
    from app.domain.models import Portfolio, StressScenario
    from app.sample import demo_market_snapshot

    market = demo_market_snapshot(Portfolio.model_validate(portfolio))
    wire = stress_to_wire(StressScenario(name="Crash", equity_shock=-0.2), market)
    formal_body = {
        "portfolio": portfolio,
        "hedged_portfolio": hedged,
        "scenarios": [wire.model_dump(mode="json")],
        "methodology": "DELTA_GAMMA",
    }
    legacy = client.post("/api/v1/risk/stress/compare", json=legacy_body)
    formal = client.post("/api/v1/risk/stress/formal/compare", json=formal_body)
    assert legacy.status_code == 200, legacy.text
    assert formal.status_code == 200, formal.text
    assert formal.json()["scenarios"][0]["scenario"] == "Crash"
    assert formal.json()["scenarios"][0]["base_pnl"] == pytest.approx(
        legacy.json()["scenarios"][0]["base_pnl"], rel=0, abs=1e-9
    )
    assert formal.json()["var_improvement"] == pytest.approx(
        legacy.json()["var_improvement"], rel=0, abs=1e-9
    )


def test_wires_to_scenarios_preserves_formal_type():
    wire = ScenarioWire(
        id="native",
        name="Native formal",
        category=ScenarioCategory.FACTOR,
        shocks=[
            FactorShockWire(factor_type="equity", key="SPY", amount=-0.10, bucket="SPY"),
        ],
        max_loss_pct=0.05,
    )
    scenarios = wires_to_scenarios([wire])
    assert len(scenarios) == 1
    assert isinstance(scenarios[0], Scenario)
    assert scenarios[0].id == "native"


def test_stress_engine_runs_formal_scenario_without_scenario_to_stress(monkeypatch):
    """R0.4.2-B: StressEngine.run accepts formal Scenario; no collapse adapter."""
    formal = Scenario(
        id="formal-run",
        name="Formal run",
        category=ScenarioCategory.FACTOR,
        shocks=(FactorShock(EquitySpot("SPY"), -0.10),),
        threshold=ScenarioThreshold(max_loss_pct=0.05),
    )
    legacy = scenario_to_stress(formal)

    def boom(*_args, **_kwargs):
        raise AssertionError("scenario_to_stress must not be called on StressEngine.run path")

    monkeypatch.setattr("app.risk.scenario_model.scenario_to_stress", boom)
    monkeypatch.setattr("app.risk.scenario_attribution.scenario_to_stress", boom, raising=False)

    formal_results = ENGINE.run(
        SAMPLE_PORTFOLIO, PRICING, [formal], market=SAMPLE_MARKET
    )
    legacy_results = ENGINE.run(
        SAMPLE_PORTFOLIO, PRICING, [legacy], market=SAMPLE_MARKET
    )
    assert formal_results[0].scenario == "Formal run"
    assert formal_results[0].pnl == pytest.approx(legacy_results[0].pnl, rel=0, abs=1e-9)
    assert formal_results[0].by_position.keys() == legacy_results[0].by_position.keys()
    for pid in formal_results[0].by_position:
        assert formal_results[0].by_position[pid] == pytest.approx(
            legacy_results[0].by_position[pid], rel=0, abs=1e-9
        )


def test_stress_engine_evaluate_formal_matches_legacy_content_path():
    """Formal evaluate vs collapsed StressScenario: identical P&L / threat fields."""
    formal = Scenario(
        id="formal-eval",
        name="Formal eval",
        category=ScenarioCategory.HYPOTHETICAL,
        description="native formal evaluate",
        shocks=(
            FactorShock(EquitySpot("SPY"), -0.15),
            FactorShock(EquityVol(underlying="SPY"), 0.25),
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.02),
    )
    legacy = scenario_to_stress(formal)
    formal_report = ENGINE.evaluate(
        SAMPLE_PORTFOLIO, PRICING, [formal], market=SAMPLE_MARKET
    )
    legacy_report = ENGINE.evaluate(
        SAMPLE_PORTFOLIO, PRICING, [legacy], market=SAMPLE_MARKET
    )
    fe = formal_report.evaluations[0]
    le = legacy_report.evaluations[0]
    assert fe.scenario == "Formal eval"
    assert fe.pnl == pytest.approx(le.pnl, rel=0, abs=1e-9)
    assert fe.loss == pytest.approx(le.loss, rel=0, abs=1e-9)
    assert fe.loss_pct_nav == pytest.approx(le.loss_pct_nav, rel=0, abs=1e-12)
    assert fe.threat_level == le.threat_level
    assert fe.breached == le.breached
    assert fe.kind == le.kind
    shocked_formal = apply_scenario(SAMPLE_MARKET, formal)
    shocked_legacy = apply_scenario(SAMPLE_MARKET, legacy)
    assert shocked_formal.content_hash() == shocked_legacy.content_hash()
