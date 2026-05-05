"""Formal ``Scenario`` HTTP wire DTOs and adapters (M3.8 / R0.4.2-C).

Canonical list wire is ``ScenarioWire`` on ``GET /risk/stress/scenarios``
(and the ``/scenarios/formal`` alias). Formal POST twins under
``/risk/stress/formal/*`` lift wire → domain ``Scenario`` for ``StressEngine``
without ``scenario_to_stress``. Legacy ``StressScenario`` POST bodies remain
on ``/stress/custom``, ``/evaluate/custom``, ``/compare`` for existing clients.
``wire_to_stress`` remains for adapters / tests that still need the legacy
StressScenario projection.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.models import (
    FiniteFloat,
    FiniteInputMixin,
    MarketSnapshot,
    Portfolio,
    StressScenario,
)
from app.risk.factor_types import FactorType, parse_risk_factor
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    ScenarioCategory,
    ScenarioSeverity,
    ScenarioThreshold,
    scenario_from_stress,
    scenario_to_stress,
)


class FactorShockWire(FiniteInputMixin):
    """One typed factor shock on the HTTP wire."""

    factor_type: FactorType
    key: str = Field(description="Stable factor key (e.g. SPY, SPY:VOL, USD:RATE, EURUSD).")
    amount: FiniteFloat = Field(
        description=(
            "Shock in MarketSnapshot.bump units: relative for equity/FX/vol; "
            "absolute decimal rate for RateZero (0.0001 = +1bp)."
        )
    )
    bucket: str = Field(
        default="ALL",
        description="Rate tenor or vol underlying bucket; unused for equity/FX spot.",
    )
    expiry: str = "GENERIC"
    moneyness: str = "ATM"


class ScenarioWire(FiniteInputMixin):
    """Formal Scenario HTTP wire type (M3.8)."""

    id: str
    name: str
    category: ScenarioCategory
    shocks: list[FactorShockWire] = Field(default_factory=list)
    description: str = ""
    max_loss_pct: FiniteFloat | None = Field(default=None, gt=0)
    severity: ScenarioSeverity | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FormalCustomStressRequest(FiniteInputMixin):
    """Custom stress / threat evaluate using formal Scenario wire payloads."""

    portfolio: Portfolio
    scenarios: list[ScenarioWire]


def wire_to_scenario(wire: ScenarioWire) -> Scenario:
    """Lift HTTP wire → formal domain ``Scenario``."""
    shocks: list[FactorShock] = []
    for item in wire.shocks:
        factor = parse_risk_factor(
            item.key,
            item.factor_type,
            item.bucket,
            expiry=item.expiry,
            moneyness=item.moneyness,
        )
        shocks.append(FactorShock(factor, float(item.amount)))
    return Scenario(
        id=wire.id,
        name=wire.name,
        category=wire.category,
        description=wire.description,
        shocks=tuple(shocks),
        threshold=ScenarioThreshold(max_loss_pct=wire.max_loss_pct),
        severity=wire.severity,
        metadata=dict(wire.metadata),
    )


def scenario_to_wire(scenario: Scenario) -> ScenarioWire:
    """Project formal domain ``Scenario`` → HTTP wire."""
    shocks: list[FactorShockWire] = []
    for item in scenario.shocks:
        factor = item.factor
        shocks.append(
            FactorShockWire(
                factor_type=factor.factor_type,
                key=factor.key,
                amount=float(item.amount),
                bucket=factor.bucket,
                expiry=getattr(factor, "expiry", "GENERIC"),
                moneyness=getattr(factor, "moneyness", "ATM"),
            )
        )
    return ScenarioWire(
        id=scenario.id,
        name=scenario.name,
        category=scenario.category,
        shocks=shocks,
        description=scenario.description,
        max_loss_pct=scenario.threshold.max_loss_pct,
        severity=scenario.severity,
        metadata=dict(scenario.metadata),
    )


def wire_to_stress(wire: ScenarioWire) -> StressScenario:
    """Project formal wire onto legacy ``StressScenario`` (adapter / tests only).

    Engine-facing formal HTTP paths use :func:`wire_to_scenario` instead.
    """
    return scenario_to_stress(wire_to_scenario(wire))


def stress_to_wire(stress: StressScenario, base: MarketSnapshot) -> ScenarioWire:
    """Lift legacy ``StressScenario`` → formal wire (needs ``base`` for scalar expansion)."""
    return scenario_to_wire(scenario_from_stress(stress, base))


def wires_to_scenarios(scenarios: list[ScenarioWire]) -> list[Scenario]:
    """Lift formal wire list → domain ``Scenario`` for StressEngine."""
    return [wire_to_scenario(s) for s in scenarios]


def wires_to_stress(scenarios: list[ScenarioWire]) -> list[StressScenario]:
    """Legacy adapter: formal wire → StressScenario (parity / migration helpers)."""
    return [wire_to_stress(s) for s in scenarios]


__all__ = [
    "FactorShockWire",
    "FormalCustomStressRequest",
    "ScenarioWire",
    "scenario_to_wire",
    "stress_to_wire",
    "wire_to_scenario",
    "wire_to_stress",
    "wires_to_scenarios",
    "wires_to_stress",
]
