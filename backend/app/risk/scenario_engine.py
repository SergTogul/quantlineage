"""Multi-factor scenario engine (M3.2).

Transforms a base ``MarketSnapshot`` into a shocked snapshot by applying
combined equity / rates / FX / vol factor moves via ``MarketSnapshot.apply`` /
``bump``. No instrument pricing lives here.

Builds on the M3.1 formal model (``Scenario`` / ``FactorShock``). Also accepts
legacy and intermediate shapes so existing StressScenario APIs keep working:

- formal ``Scenario`` / ``FactorShock`` sequences (``scenario_model``)
- legacy ``StressScenario`` (scalar fields + per-name dict overrides)
- M2.2 ``MarketScenario`` / ``FactorChange`` sequences
- raw ``(RiskFactor, amount)`` pairs

Composition rules
-----------------
1. **Independent scenarios**: each scenario is applied to the original base
   snapshot (not stacked on prior scenario results).
2. **Canonical expansion order** for ``StressScenario`` (via
   ``scenario_from_stress``): equity spots → equity vols → FX spots → FX vols
   → parallel rates.
3. **Caller order** is preserved for formal ``Scenario``, ``FactorShock`` /
   ``FactorChange`` lists, and pair sequences.
4. **Zero amounts** are omitted at apply time (marks / ``content_hash`` unchanged).
5. **Per-name dicts** on ``StressScenario`` override the corresponding scalar
   default for that name; other names still use the scalar.
6. **Duplicate factors** in an explicit sequence compound via successive
   ``bump`` (multiplicative for spots/vols, additive for rates).
7. **Empty / all-zero** scenarios leave ``content_hash`` unchanged.

Units (``MarketSnapshot.bump``):
- equity / FX: relative return (``0.01`` = +1%)
- vol: relative change of vol level
- rates: decimal zero shift (``StressScenario`` bp fields ÷ 10000)
"""

from __future__ import annotations

from typing import Sequence, Union

from app.domain.models import MarketSnapshot, StressScenario
from app.risk.factor_types import RiskFactor
from app.risk.scenario_model import (
    FactorShock,
    Scenario,
    ScenarioCategory,
    scenario_from_market_scenario,
    scenario_from_stress,
)
from app.risk.scenario_model import (
    apply_scenario as apply_formal_scenario,
)
from app.risk.scenarios import FactorChange, MarketScenario

ScenarioInput = Union[
    Scenario,
    StressScenario,
    MarketScenario,
    Sequence[FactorShock],
    Sequence[FactorChange],
    Sequence[tuple[RiskFactor, float]],
]

_NAMED_TYPES = (Scenario, StressScenario, MarketScenario)


def _is_shock_sequence(value: object) -> bool:
    if isinstance(value, _NAMED_TYPES) or not isinstance(value, Sequence):
        return False
    if isinstance(value, (str, bytes)):
        return False
    return True


def expand_scenario(base: MarketSnapshot, scenario: ScenarioInput) -> tuple[FactorShock, ...]:
    """Normalize any supported input to an ordered ``FactorShock`` tuple."""
    if isinstance(scenario, Scenario):
        return scenario.shocks
    if isinstance(scenario, StressScenario):
        return scenario_from_stress(scenario, base).shocks
    if isinstance(scenario, MarketScenario):
        return tuple(FactorShock(c.factor, c.amount) for c in scenario.shocks)
    if not _is_shock_sequence(scenario):
        raise TypeError(f"unsupported scenario input: {type(scenario)!r}")
    out: list[FactorShock] = []
    for item in scenario:  # type: ignore[union-attr]
        if isinstance(item, FactorShock):
            out.append(item)
        elif isinstance(item, FactorChange):
            out.append(FactorShock(item.factor, item.amount))
        elif isinstance(item, tuple) and len(item) == 2:
            factor, amount = item
            out.append(FactorShock(factor, float(amount)))
        else:
            raise TypeError(f"unsupported shock element: {type(item)!r}")
    return tuple(out)


def expand_stress_scenario(base: MarketSnapshot, scenario: StressScenario) -> tuple[FactorShock, ...]:
    """Expand legacy ``StressScenario`` via M3.1 ``scenario_from_stress``."""
    return scenario_from_stress(scenario, base).shocks


def _scenario_tag(scenario: ScenarioInput, scenario_id: str | None) -> str | None:
    if scenario_id is not None:
        return scenario_id
    if isinstance(scenario, Scenario):
        return scenario.id
    if isinstance(scenario, StressScenario):
        return scenario.id or scenario.name
    if isinstance(scenario, MarketScenario):
        return scenario.id
    return None


def _apply_scenario_uncached(
    base: MarketSnapshot,
    scenario: ScenarioInput,
    *,
    scenario_id: str | None = None,
) -> MarketSnapshot:
    """Apply one multi-factor scenario without memoization."""
    if isinstance(scenario, Scenario):
        out = apply_formal_scenario(base, scenario)
        if scenario_id is None or scenario_id == scenario.id:
            return out
        return out.model_copy(update={"id": f"{base.id}:{scenario_id}"})

    if isinstance(scenario, StressScenario):
        formal = scenario_from_stress(scenario, base)
        if scenario_id is not None and scenario_id != formal.id:
            formal = Scenario(
                id=scenario_id,
                name=formal.name,
                category=formal.category,
                description=formal.description,
                shocks=formal.shocks,
                threshold=formal.threshold,
                severity=formal.severity,
                metadata=dict(formal.metadata),
            )
        return apply_formal_scenario(base, formal)

    if isinstance(scenario, MarketScenario):
        formal = scenario_from_market_scenario(scenario)
        if scenario_id is not None and scenario_id != formal.id:
            formal = Scenario(
                id=scenario_id,
                name=formal.name,
                category=formal.category,
                description=formal.description,
                shocks=formal.shocks,
                threshold=formal.threshold,
                severity=formal.severity,
                metadata=dict(formal.metadata),
            )
        return apply_formal_scenario(base, formal)

    shocks = expand_scenario(base, scenario)
    pairs = [(s.factor, s.amount) for s in shocks if s.amount]
    out = base.apply(pairs) if pairs else base
    tag = _scenario_tag(scenario, scenario_id)
    if tag is None:
        return out
    new_id = f"{base.id}:{tag}"
    if out.id == new_id:
        return out
    return out.model_copy(update={"id": new_id})


def apply_scenario(
    base: MarketSnapshot,
    scenario: ScenarioInput,
    *,
    scenario_id: str | None = None,
) -> MarketSnapshot:
    """Apply one multi-factor scenario to ``base``.

    Formal ``Scenario`` and adapted ``StressScenario`` / ``MarketScenario``
    paths share ``scenario_model.apply_scenario``. Explicit shock lists apply
    non-zero amounts in caller order via ``MarketSnapshot.apply``.

    When ``RISKFORGE_SCENARIO_CACHE`` is enabled (default), results are memoized
    by base id + content hash + expanded shock fingerprint + scenario id tag.
    """
    from app.risk.scenario_memo import (
        get_scenario_result_memo,
        scenario_memo_enabled,
        scenario_memo_key,
    )

    if not scenario_memo_enabled():
        return _apply_scenario_uncached(base, scenario, scenario_id=scenario_id)

    shocks = expand_scenario(base, scenario)
    tag = _scenario_tag(scenario, scenario_id)
    key = scenario_memo_key(base, shocks, id_tag=tag)
    memo = get_scenario_result_memo()
    hit = memo.get(key)
    if hit is not None:
        return hit

    out = _apply_scenario_uncached(base, scenario, scenario_id=scenario_id)
    return memo.put(key, out)


def shocked_snapshots(
    base: MarketSnapshot,
    scenarios: Sequence[ScenarioInput],
) -> list[MarketSnapshot]:
    """Apply each scenario independently to ``base`` (not cumulative)."""
    return [apply_scenario(base, s) for s in scenarios]


class ScenarioEngine:
    """Stateful façade for multi-factor scenario application (M3.2)."""

    def expand(self, base: MarketSnapshot, scenario: ScenarioInput) -> tuple[FactorShock, ...]:
        return expand_scenario(base, scenario)

    def apply(
        self,
        base: MarketSnapshot,
        scenario: ScenarioInput,
        *,
        scenario_id: str | None = None,
    ) -> MarketSnapshot:
        return apply_scenario(base, scenario, scenario_id=scenario_id)

    def apply_many(
        self,
        base: MarketSnapshot,
        scenarios: Sequence[ScenarioInput],
    ) -> list[MarketSnapshot]:
        return shocked_snapshots(base, scenarios)

    def to_formal(self, base: MarketSnapshot, scenario: ScenarioInput) -> Scenario:
        """Lift any supported input into a formal ``Scenario`` (needs ``base`` for StressScenario)."""
        if isinstance(scenario, Scenario):
            return scenario
        if isinstance(scenario, StressScenario):
            return scenario_from_stress(scenario, base)
        if isinstance(scenario, MarketScenario):
            return scenario_from_market_scenario(scenario)
        shocks = expand_scenario(base, scenario)
        tag = _scenario_tag(scenario, None) or "adhoc"
        return Scenario(
            id=tag,
            name=tag,
            category=ScenarioCategory.CUSTOM,
            shocks=shocks,
        )


__all__ = [
    "ScenarioEngine",
    "ScenarioInput",
    "apply_scenario",
    "expand_scenario",
    "expand_stress_scenario",
    "shocked_snapshots",
]
