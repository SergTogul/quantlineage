"""Serialize canonical ``Scenario`` as ScenarioWire JSON for persistence."""

from __future__ import annotations

from typing import Any

from app.api.scenario_wire import ScenarioWire, scenario_to_wire, wire_to_scenario
from app.risk.scenario_model import Scenario


def scenario_to_definition(scenario: Scenario) -> dict[str, Any]:
    """Persist as formal ``ScenarioWire`` JSON (typed shocks, not StressScenario)."""
    return scenario_to_wire(scenario).model_dump(mode="json")


def definition_to_scenario(payload: dict[str, Any]) -> Scenario:
    """Load canonical ``Scenario`` from stored ScenarioWire JSON."""
    return wire_to_scenario(ScenarioWire.model_validate(payload))
