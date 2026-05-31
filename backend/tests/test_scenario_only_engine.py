"""R0.4.2-E: engine-facing stress / attribution / threat are canonical Scenario.

Legacy ``StressScenario`` is adapted once at the HTTP or engine boundary.
Apply / evaluate / decompose internals must see typed ``Scenario`` only.
Shock units stay in ``shock_units`` (bp↔decimal at adapter).
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio, StressScenario
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk import scenario_attribution as attr_mod
from app.risk import stress as stress_mod
from app.risk.scenario_attribution import ScenarioAttributionEngine
from app.risk import scenario_model as scenario_model_mod
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    ScenarioCategory,
    ScenarioThreshold,
    scenario_from_stress,
)
from app.risk.stress import StressEngine, _evaluation_fields
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService

PRICING = BuiltinPricingEngine()
ENGINE = StressEngine()
SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)
client = TestClient(app)


def _legacy_equity_down() -> StressScenario:
    return StressScenario(
        id="eq_down_10",
        name="Equities -10%",
        description="Broad equity selloff with other factors unchanged.",
        equity_shock=-0.10,
        max_loss_pct=0.06,
    )


def _tiny_book() -> tuple[Portfolio, MarketSnapshot]:
    book = Portfolio(
        id="canon-book",
        name="canon-book",
        positions=[
            EquityPosition(type="equity", id="unit", symbol="UNIT", quantity=1.0),
        ],
    )
    market = MarketSnapshot(
        id="canon-mkt",
        as_of="2024-01-02",
        equity_spots={"UNIT": 100.0},
        rates={"USD": 0.04},
    )
    return book, market


def test_to_canonical_scenario_lifts_legacy_and_passes_formal_through():
    book, market = _tiny_book()
    legacy = _legacy_equity_down()
    assert hasattr(scenario_model_mod, "to_canonical_scenario")
    to_canonical_scenario = scenario_model_mod.to_canonical_scenario
    canonical = to_canonical_scenario(legacy, market)
    assert isinstance(canonical, Scenario)
    assert canonical.id == "eq_down_10"
    assert all(isinstance(s, FactorShock) for s in canonical.shocks)

    formal = Scenario(
        id="already",
        name="Already formal",
        category=ScenarioCategory.FACTOR,
        shocks=canonical.shocks,
        threshold=ScenarioThreshold(max_loss_pct=0.06),
    )
    assert to_canonical_scenario(formal, market) is formal
    del book


def test_stress_engine_run_applies_canonical_scenario_not_legacy(monkeypatch):
    """Engine run may accept StressScenario at the door; apply sees Scenario only."""
    book, market = _tiny_book()
    legacy = StressScenario(id="eq_down_10", name="Equities -10%", equity_shock=-0.10)
    seen: list[object] = []
    real_apply = stress_mod.apply_scenario

    def tracking_apply(base, scen, **kwargs):
        seen.append(scen)
        return real_apply(base, scen, **kwargs)

    monkeypatch.setattr(stress_mod, "apply_scenario", tracking_apply)
    results = ENGINE.run(book, PRICING, [legacy], market=market)
    assert len(results) == 1
    assert len(seen) == 1
    assert isinstance(seen[0], Scenario)
    assert not isinstance(seen[0], StressScenario)
    assert seen[0].id == "eq_down_10"


def test_stress_engine_evaluate_applies_canonical_scenario_not_legacy(monkeypatch):
    book, market = _tiny_book()
    legacy = StressScenario(
        id="eq_down_10",
        name="Equities -10%",
        equity_shock=-0.10,
        max_loss_pct=0.06,
    )
    seen: list[object] = []
    real_apply = stress_mod.apply_scenario

    def tracking_apply(base, scen, **kwargs):
        seen.append(scen)
        return real_apply(base, scen, **kwargs)

    monkeypatch.setattr(stress_mod, "apply_scenario", tracking_apply)
    report = ENGINE.evaluate(book, PRICING, [legacy], market=market)
    assert len(report.evaluations) == 1
    full = [s for s in seen if getattr(s, "id", None) == "eq_down_10"]
    assert full
    assert all(isinstance(s, Scenario) for s in full)
    assert all(not isinstance(s, StressScenario) for s in seen)
    assert report.evaluations[0].scenario == "Equities -10%"
    assert report.evaluations[0].max_loss_pct == pytest.approx(0.06)


def test_attribution_decompose_applies_canonical_scenario_not_legacy(monkeypatch):
    book, market = _tiny_book()
    legacy = StressScenario(id="eq_down_10", name="Equities -10%", equity_shock=-0.10)
    seen: list[object] = []
    real_apply = attr_mod.apply_scenario

    def tracking_apply(base, scen, **kwargs):
        seen.append(scen)
        return real_apply(base, scen, **kwargs)

    monkeypatch.setattr(attr_mod, "apply_scenario", tracking_apply)
    breakdown = ScenarioAttributionEngine().decompose(book, PRICING, legacy, market=market)
    assert breakdown.scenario_id == "eq_down_10"
    assert seen
    assert all(isinstance(s, Scenario) for s in seen)
    assert all(not isinstance(s, StressScenario) for s in seen)


def test_evaluation_fields_is_scenario_only():
    src = inspect.getsource(_evaluation_fields)
    assert "StressScenario" not in src
    formal = Scenario(
        id="eval-only",
        name="Eval only",
        category=ScenarioCategory.FACTOR,
        shocks=(),
        threshold=ScenarioThreshold(max_loss_pct=0.04),
        description="canonical",
    )
    scenario_id, name, kind, description, threshold = _evaluation_fields(formal, 0)
    assert scenario_id == "eval-only"
    assert name == "Eval only"
    assert description == "canonical"
    assert threshold == pytest.approx(0.04)
    assert kind.value == "factor"


def test_legacy_and_canonical_run_share_pnl_and_content_hash():
    book, market = _tiny_book()
    legacy = StressScenario(id="eq_down_10", name="Equities -10%", equity_shock=-0.10)
    canonical = scenario_from_stress(legacy, market)
    legacy_results = ENGINE.run(book, PRICING, [legacy], market=market)
    formal_results = ENGINE.run(book, PRICING, [canonical], market=market)
    assert legacy_results[0].pnl == pytest.approx(formal_results[0].pnl, rel=0, abs=1e-12)
    from app.risk.scenario_engine import apply_scenario

    assert apply_scenario(market, legacy).content_hash() == apply_scenario(
        market, canonical
    ).content_hash()


def test_deprecated_custom_http_adapts_legacy_before_service(monkeypatch):
    """Prefer convert-once at HTTP: service.stresses receives Scenario, not StressScenario."""
    seen: list[object] = []
    original = PortfolioService.stresses

    def tracking_stresses(self, portfolio, scenarios=None):
        if scenarios is not None:
            seen.extend(list(scenarios))
        return original(self, portfolio, scenarios)

    monkeypatch.setattr(PortfolioService, "stresses", tracking_stresses)
    portfolio = client.get("/api/v1/portfolio").json()
    response = client.post(
        "/api/v1/risk/stress/custom",
        json={
            "portfolio": portfolio,
            "scenarios": [
                {
                    "name": "Custom",
                    "id": "custom-legacy",
                    "equity_shocks": {"SPY": -0.10},
                    "max_loss_pct": 0.05,
                }
            ],
        },
    )
    assert response.status_code == 200
    assert seen
    assert all(isinstance(s, Scenario) for s in seen)
    assert all(not isinstance(s, StressScenario) for s in seen)


def test_deprecated_evaluate_custom_http_adapts_legacy_before_service(monkeypatch):
    seen: list[object] = []
    original = PortfolioService.threat_evaluation

    def tracking_eval(self, portfolio, scenarios=None):
        if scenarios is not None:
            seen.extend(list(scenarios))
        return original(self, portfolio, scenarios)

    monkeypatch.setattr(PortfolioService, "threat_evaluation", tracking_eval)
    portfolio = client.get("/api/v1/portfolio").json()
    response = client.post(
        "/api/v1/risk/stress/evaluate/custom",
        json={
            "portfolio": portfolio,
            "scenarios": [
                {
                    "name": "Custom threat",
                    "id": "custom-threat",
                    "equity_shocks": {"SPY": -0.10},
                    "max_loss_pct": 0.05,
                }
            ],
        },
    )
    assert response.status_code == 200
    assert seen
    assert all(isinstance(s, Scenario) for s in seen)
    assert all(not isinstance(s, StressScenario) for s in seen)
