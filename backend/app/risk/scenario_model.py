"""Formal Scenario domain model (M3.1).

A ``Scenario`` is the typed stress/threat definition: identity, category,
description, ordered typed-factor shocks, governance threshold, optional
declared severity, and opaque metadata.

Shock application rule (charter): transform a base ``MarketSnapshot`` via
``MarketSnapshot.apply`` / ``bump`` — never embed instrument pricing in
scenario code.

Engine-facing shocks are ``FactorShock`` amounts in ``MarketSnapshot.bump``
units (see ``FactorShock`` and ``app.risk.shock_units``). Legacy
``StressScenario`` bp fields (``rates_shift_bps`` / ``rate_shocks_bps``)
convert only at the adapter boundary via ``bps_to_decimal_rate`` /
``decimal_rate_to_bps`` — expand/collapse must not inline bp↔decimal scales.

Legacy ``StressScenario`` (flat scalar/dict fields) remains the HTTP/wire
adapter for deprecated POST endpoints. R0.4.2-C: ``GET .../scenarios`` returns
formal ``ScenarioWire`` (``/scenarios/formal`` is an identical alias); formal
POST twins stay under ``/api/v1/risk/stress/formal/*`` (see
``app.api.scenario_wire``). R0.4.2-E: engine-facing stress / attribution /
threat convert ``StressScenario`` once at the HTTP or engine boundary via
``to_canonical_scenario``; internals apply typed ``Scenario`` only. R0.4.2-F:
in-code DEFAULT/THREAT libraries are ``BroadcastScenarioDefinition`` templates
expanded at apply time against the live ``MarketSnapshot`` (do not freeze demo
names at import). Persistence stores canonical ``Scenario``. R0.4.2-G: historical
replay generates/applies canonical ``Scenario``; reverse-stress results carry
the applied ``Scenario``. ``MarketScenario`` remains an adapter like deprecated
``StressScenario``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero, RiskFactor
from app.risk.scenarios import FactorChange, MarketScenario
from app.risk.shock_units import bps_to_decimal_rate, decimal_rate_to_bps


class ScenarioCategory(str, Enum):
    """Governance / library category for a scenario definition."""

    FACTOR = "factor"
    MACRO = "macro"
    HYPOTHETICAL = "hypothetical"
    HISTORICAL_REPLAY = "historical_replay"
    HISTORICAL_APPROXIMATION = "historical_approximation"
    CUSTOM = "custom"
    REVERSE = "reverse"


class ScenarioSeverity(str, Enum):
    """Threat / severity band (aligned with StressEngine ``_threat_level``)."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


# Loss % of |NAV| boundaries (inclusive lower edge of each band above LOW).
SEVERITY_MODERATE_MIN = 0.03
SEVERITY_HIGH_MIN = 0.08
SEVERITY_SEVERE_MIN = 0.15


@dataclass(frozen=True, slots=True)
class ScenarioThreshold:
    """Governance loss threshold as a fraction of |NAV| (e.g. 0.05 = 5%)."""

    max_loss_pct: float | None = None

    def __post_init__(self) -> None:
        if self.max_loss_pct is not None and self.max_loss_pct <= 0:
            raise ValueError("max_loss_pct must be > 0 when set")


@dataclass(frozen=True, slots=True)
class BroadcastShockTemplate:
    """Aggregate scalar macros expanded onto factors present in a live snapshot.

    Same units as ``StressScenario`` / ``CrisisShockTemplate``:
    equity/FX relative, vol relative, rates in bp (converted at expand via
    ``shock_units`` only).
    """

    equity_shock: float = 0.0
    vol_shock: float = 0.0
    rates_shift_bps: float = 0.0
    fx_shock: float = 0.0


@dataclass(frozen=True, slots=True)
class BroadcastScenarioDefinition:
    """In-code library template — not a stored ``Scenario``.

    Broadcast macros expand at apply time via
    :func:`expand_broadcast_definition` / :func:`to_canonical_scenario`
    against the live ``MarketSnapshot`` (same walk as
    ``crisis_scenarios(base)``). Demo equity names must not be frozen here.
    """

    id: str
    name: str
    description: str = ""
    category: ScenarioCategory = ScenarioCategory.FACTOR
    shocks: BroadcastShockTemplate = field(default_factory=BroadcastShockTemplate)
    threshold: ScenarioThreshold = field(default_factory=ScenarioThreshold)
    severity: ScenarioSeverity | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("BroadcastScenarioDefinition.id must be non-empty")
        if not self.name:
            raise ValueError("BroadcastScenarioDefinition.name must be non-empty")
        object.__setattr__(self, "metadata", _freeze_metadata(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class FactorShock:
    """One typed risk-factor shock in ``MarketSnapshot.bump`` units.

    Units (same as ``MarketSnapshot`` / ``FactorChange``):
    - EquitySpot / FXSpot: relative return (0.01 = +1%)
    - EquityVol / FXVol: relative vol-level change
    - RateZero: absolute decimal rate (0.0001 = +1bp)
    """

    factor: RiskFactor
    amount: float

    def as_pair(self) -> tuple[RiskFactor, float]:
        return (self.factor, self.amount)

    def as_factor_change(self) -> FactorChange:
        return FactorChange(self.factor, self.amount)


def _freeze_metadata(metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    raw = dict(metadata or {})
    return MappingProxyType(raw)


@dataclass(frozen=True, slots=True)
class Scenario:
    """Formal multi-factor scenario definition (M3.1)."""

    id: str
    name: str
    category: ScenarioCategory
    description: str = ""
    shocks: tuple[FactorShock, ...] = ()
    threshold: ScenarioThreshold = field(default_factory=ScenarioThreshold)
    severity: ScenarioSeverity | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Scenario.id must be non-empty")
        if not self.name:
            raise ValueError("Scenario.name must be non-empty")
        # Normalize metadata to an immutable mapping.
        object.__setattr__(self, "metadata", _freeze_metadata(dict(self.metadata)))
        if not isinstance(self.shocks, tuple):
            object.__setattr__(self, "shocks", tuple(self.shocks))

    def shock_pairs(self) -> list[tuple[RiskFactor, float]]:
        """Ordered ``(RiskFactor, amount)`` list for ``MarketSnapshot.apply``."""
        return [s.as_pair() for s in self.shocks]

    @property
    def is_empty(self) -> bool:
        return not self.shocks or all(s.amount == 0.0 for s in self.shocks)


def classify_severity(loss_pct_nav: float) -> ScenarioSeverity:
    """Map realized loss fraction of |NAV| to a severity band.

    Boundaries match ``StressEngine`` threat classification:
    - ``SEVERE``: loss_pct >= 15%
    - ``HIGH``: loss_pct >= 8%
    - ``MODERATE``: loss_pct >= 3%
    - ``LOW``: otherwise
    """
    if loss_pct_nav >= SEVERITY_SEVERE_MIN:
        return ScenarioSeverity.SEVERE
    if loss_pct_nav >= SEVERITY_HIGH_MIN:
        return ScenarioSeverity.HIGH
    if loss_pct_nav >= SEVERITY_MODERATE_MIN:
        return ScenarioSeverity.MODERATE
    return ScenarioSeverity.LOW


def threshold_breached(loss_pct_nav: float, threshold: ScenarioThreshold | float | None) -> bool:
    """True when loss exceeds an explicit governance threshold."""
    if isinstance(threshold, ScenarioThreshold):
        limit = threshold.max_loss_pct
    else:
        limit = threshold
    if limit is None:
        return False
    return loss_pct_nav > limit


def category_to_kind(category: ScenarioCategory) -> ScenarioKind:
    """Map formal category onto legacy ``ScenarioKind`` for StressScenario APIs."""
    if category == ScenarioCategory.FACTOR:
        return ScenarioKind.FACTOR
    if category in (ScenarioCategory.MACRO, ScenarioCategory.HYPOTHETICAL):
        return ScenarioKind.MACRO
    if category in (
        ScenarioCategory.HISTORICAL_REPLAY,
        ScenarioCategory.HISTORICAL_APPROXIMATION,
    ):
        return ScenarioKind.HISTORICAL_STYLE
    if category == ScenarioCategory.REVERSE:
        return ScenarioKind.REVERSE
    return ScenarioKind.CUSTOM


def kind_to_category(kind: ScenarioKind, *, historical_as: ScenarioCategory | None = None) -> ScenarioCategory:
    """Map legacy ``ScenarioKind`` onto formal category.

    Historical-style presets are treated as approximations unless
    ``historical_as`` overrides (e.g. true replay from observations).
    """
    if kind == ScenarioKind.FACTOR:
        return ScenarioCategory.FACTOR
    if kind == ScenarioKind.MACRO:
        return ScenarioCategory.MACRO
    if kind == ScenarioKind.HISTORICAL_STYLE:
        return historical_as or ScenarioCategory.HISTORICAL_APPROXIMATION
    if kind == ScenarioKind.REVERSE:
        return ScenarioCategory.REVERSE
    return ScenarioCategory.CUSTOM


def apply_scenario(base: MarketSnapshot, scenario: Scenario) -> MarketSnapshot:
    """Apply typed shocks; empty / zero shocks leave market marks unchanged."""
    pairs = [(f, a) for f, a in scenario.shock_pairs() if a]
    out = base.apply(pairs) if pairs else base
    new_id = f"{base.id}:{scenario.id}"
    if out.id == new_id:
        return out
    return out.model_copy(update={"id": new_id})


def _expand_macro_to_shocks(
    base: MarketSnapshot,
    *,
    equity_shock: float = 0.0,
    vol_shock: float = 0.0,
    rates_shift_bps: float = 0.0,
    fx_shock: float = 0.0,
    equity_shocks: Mapping[str, float] | None = None,
    vol_shocks: Mapping[str, float] | None = None,
    rate_shocks_bps: Mapping[str, float] | None = None,
    fx_shocks: Mapping[str, float] | None = None,
) -> tuple[FactorShock, ...]:
    """Expand scalar/dict macros onto factors present in ``base``.

    Order matches ``shock_snapshot``: equity spots, equity vols, FX spots,
    FX vols, then parallel rates. Rate bp fields convert to decimal bump
    amounts via :func:`bps_to_decimal_rate` at this adapter boundary only.
    """
    equity_named = equity_shocks or {}
    vol_named = vol_shocks or {}
    rate_named = rate_shocks_bps or {}
    fx_named = fx_shocks or {}
    shocks: list[FactorShock] = []
    for sym in base.equity_spots:
        amt = equity_named.get(sym, equity_shock)
        if amt:
            shocks.append(FactorShock(EquitySpot(sym), float(amt)))
    for sym in base.equity_vols:
        amt = vol_named.get(sym, vol_shock)
        if amt:
            shocks.append(FactorShock(EquityVol(underlying=sym), float(amt)))
    for pair in base.fx_spots:
        amt = fx_named.get(pair, fx_shock)
        if amt:
            shocks.append(FactorShock(FXSpot(pair), float(amt)))
    for pair in base.fx_vols:
        amt = vol_named.get(pair, vol_shock)
        if amt:
            shocks.append(FactorShock(FXVol(pair=pair), float(amt)))
    for ccy in base.rates:
        bps = rate_named.get(ccy, rates_shift_bps)
        if bps:
            shocks.append(
                FactorShock(RateZero(currency=ccy, tenor="ALL"), bps_to_decimal_rate(float(bps)))
            )
    return tuple(shocks)


def _expand_stress_to_shocks(stress: StressScenario, base: MarketSnapshot) -> tuple[FactorShock, ...]:
    """Expand legacy scalar/dict StressScenario fields onto factors in ``base``."""
    return _expand_macro_to_shocks(
        base,
        equity_shock=float(stress.equity_shock),
        vol_shock=float(stress.vol_shock),
        rates_shift_bps=float(stress.rates_shift_bps),
        fx_shock=float(stress.fx_shock),
        equity_shocks=stress.equity_shocks,
        vol_shocks=stress.vol_shocks,
        rate_shocks_bps=stress.rate_shocks_bps,
        fx_shocks=stress.fx_shocks,
    )


def expand_broadcast_definition(
    definition: BroadcastScenarioDefinition, base: MarketSnapshot
) -> Scenario:
    """Expand a library template onto ``base`` as canonical ``Scenario``."""
    macros = definition.shocks
    return Scenario(
        id=definition.id,
        name=definition.name,
        category=definition.category,
        description=definition.description,
        shocks=_expand_macro_to_shocks(
            base,
            equity_shock=macros.equity_shock,
            vol_shock=macros.vol_shock,
            rates_shift_bps=macros.rates_shift_bps,
            fx_shock=macros.fx_shock,
        ),
        threshold=definition.threshold,
        severity=definition.severity,
        metadata=dict(definition.metadata),
    )


CanonicalScenarioInput = Scenario | BroadcastScenarioDefinition | StressScenario


def to_canonical_scenario(scenario: CanonicalScenarioInput, base: MarketSnapshot) -> Scenario:
    """Adapt engine/HTTP/library input to canonical ``Scenario``.

    Formal ``Scenario`` is returned unchanged. ``BroadcastScenarioDefinition``
    expands against ``base`` (apply-time names). Legacy ``StressScenario`` is
    expanded via :func:`scenario_from_stress` (rate bp→decimal only through
    ``shock_units``). Other types raise ``TypeError``.
    """
    if isinstance(scenario, Scenario):
        return scenario
    if isinstance(scenario, BroadcastScenarioDefinition):
        return expand_broadcast_definition(scenario, base)
    if isinstance(scenario, StressScenario):
        return scenario_from_stress(scenario, base)
    raise TypeError(f"unsupported engine scenario type: {type(scenario)!r}")


def to_canonical_scenarios(
    scenarios: Sequence[CanonicalScenarioInput],
    base: MarketSnapshot,
) -> list[Scenario]:
    """Adapt a sequence of engine/HTTP/library inputs to canonical ``Scenario``."""
    return [to_canonical_scenario(s, base) for s in scenarios]


def scenario_from_stress(
    stress: StressScenario,
    base: MarketSnapshot,
    *,
    historical_as: ScenarioCategory | None = None,
    severity: ScenarioSeverity | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Scenario:
    """Lift a legacy ``StressScenario`` into the formal model (needs ``base`` for expansion)."""
    scenario_id = stress.id or stress.name
    meta = dict(metadata or {})
    # Preserve original flat fields for diagnostics / round-trip hints.
    meta.setdefault("legacy_kind", stress.kind.value)
    meta.setdefault("horizon", stress.horizon)
    return Scenario(
        id=scenario_id,
        name=stress.name,
        category=kind_to_category(stress.kind, historical_as=historical_as),
        description=stress.description,
        shocks=_expand_stress_to_shocks(stress, base),
        threshold=ScenarioThreshold(max_loss_pct=stress.max_loss_pct),
        severity=severity,
        metadata=meta,
    )


def scenario_to_stress(scenario: Scenario) -> StressScenario:
    """Project formal typed shocks onto legacy ``StressScenario`` dict fields.

    Aggregate scalar fields stay at zero; per-name dicts carry moves so
    ``shock_snapshot(base, scenario_to_stress(s))`` matches ``apply_scenario``.
    Rate decimal bump amounts convert back to bp via
    :func:`decimal_rate_to_bps` at this adapter boundary only.
    """
    equity_shocks: dict[str, float] = {}
    vol_shocks: dict[str, float] = {}
    rate_shocks_bps: dict[str, float] = {}
    fx_shocks: dict[str, float] = {}
    for shock in scenario.shocks:
        factor = shock.factor
        amount = shock.amount
        if isinstance(factor, EquitySpot):
            equity_shocks[factor.symbol] = amount
        elif isinstance(factor, EquityVol):
            vol_shocks[factor.underlying] = amount
        elif isinstance(factor, FXVol):
            vol_shocks[factor.pair] = amount
        elif isinstance(factor, FXSpot):
            fx_shocks[factor.pair] = amount
        elif isinstance(factor, RateZero):
            rate_shocks_bps[factor.currency] = decimal_rate_to_bps(amount)
        else:
            raise TypeError(f"unsupported risk factor type: {type(factor)!r}")
    return StressScenario(
        id=scenario.id,
        name=scenario.name,
        description=scenario.description,
        kind=category_to_kind(scenario.category),
        equity_shocks=equity_shocks,
        vol_shocks=vol_shocks,
        rate_shocks_bps=rate_shocks_bps,
        fx_shocks=fx_shocks,
        max_loss_pct=scenario.threshold.max_loss_pct,
    )


def scenario_from_market_scenario(
    market: MarketScenario,
    *,
    category: ScenarioCategory | None = None,
    threshold: ScenarioThreshold | None = None,
    severity: ScenarioSeverity | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Scenario:
    """Promote M2.2 ``MarketScenario`` into the formal Scenario model."""
    hist_default = (
        ScenarioCategory.HISTORICAL_REPLAY
        if market.kind == ScenarioKind.HISTORICAL_STYLE
        else None
    )
    meta = dict(metadata or {})
    if market.observation_index is not None:
        meta.setdefault("observation_index", market.observation_index)
    return Scenario(
        id=market.id,
        name=market.name,
        category=category or kind_to_category(market.kind, historical_as=hist_default),
        description=market.description,
        shocks=tuple(FactorShock(c.factor, c.amount) for c in market.shocks),
        threshold=threshold or ScenarioThreshold(),
        severity=severity,
        metadata=meta,
    )


def scenario_to_market_scenario(scenario: Scenario) -> MarketScenario:
    """Downgrade formal Scenario to M2.2 ``MarketScenario`` for snapshot pipelines."""
    obs = scenario.metadata.get("observation_index")
    observation_index = int(obs) if obs is not None else None
    return MarketScenario(
        id=scenario.id,
        name=scenario.name,
        shocks=tuple(s.as_factor_change() for s in scenario.shocks),
        kind=category_to_kind(scenario.category),
        description=scenario.description,
        observation_index=observation_index,
    )


def compose_shocks(*groups: Sequence[FactorShock]) -> tuple[FactorShock, ...]:
    """Concatenate shock groups in call order (later shocks apply after earlier ones)."""
    out: list[FactorShock] = []
    for group in groups:
        out.extend(group)
    return tuple(out)


__all__ = [
    "BroadcastScenarioDefinition",
    "BroadcastShockTemplate",
    "CanonicalScenarioInput",
    "FactorShock",
    "SEVERITY_HIGH_MIN",
    "SEVERITY_MODERATE_MIN",
    "SEVERITY_SEVERE_MIN",
    "Scenario",
    "ScenarioCategory",
    "ScenarioSeverity",
    "ScenarioThreshold",
    "apply_scenario",
    "category_to_kind",
    "classify_severity",
    "compose_shocks",
    "expand_broadcast_definition",
    "kind_to_category",
    "scenario_from_market_scenario",
    "scenario_from_stress",
    "scenario_to_market_scenario",
    "scenario_to_stress",
    "threshold_breached",
    "to_canonical_scenario",
    "to_canonical_scenarios",
]
