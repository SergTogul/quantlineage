"""Formal Scenario domain model (M3.1).

A ``Scenario`` is the typed stress/threat definition: identity, category,
description, ordered typed-factor shocks, governance threshold, optional
declared severity, and opaque metadata.

Shock application rule (charter): transform a base ``MarketSnapshot`` via
``MarketSnapshot.apply`` / ``bump`` — never embed instrument pricing in
scenario code.

Legacy ``StressScenario`` (flat scalar/dict fields) remains the wire/API shape
for existing stress endpoints. M3.8 adds formal ``ScenarioWire`` under
``/api/v1/risk/stress/formal/*`` and ``GET .../scenarios/formal`` (see
``app.api.scenario_wire``). Use the adapters in this module to convert
without rewriting ``StressEngine`` / what-if / VaR paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero, RiskFactor
from app.risk.scenarios import FactorChange, MarketScenario


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


def _expand_stress_to_shocks(stress: StressScenario, base: MarketSnapshot) -> tuple[FactorShock, ...]:
    """Expand legacy scalar/dict StressScenario fields onto factors in ``base``.

    Order matches ``shock_snapshot``: equity spots, equity vols, FX spots,
    FX vols, then parallel rates.
    """
    shocks: list[FactorShock] = []
    for sym in base.equity_spots:
        amt = stress.equity_shocks.get(sym, stress.equity_shock)
        if amt:
            shocks.append(FactorShock(EquitySpot(sym), float(amt)))
    for sym in base.equity_vols:
        amt = stress.vol_shocks.get(sym, stress.vol_shock)
        if amt:
            shocks.append(FactorShock(EquityVol(underlying=sym), float(amt)))
    for pair in base.fx_spots:
        amt = stress.fx_shocks.get(pair, stress.fx_shock)
        if amt:
            shocks.append(FactorShock(FXSpot(pair), float(amt)))
    for pair in base.fx_vols:
        amt = stress.vol_shocks.get(pair, stress.vol_shock)
        if amt:
            shocks.append(FactorShock(FXVol(pair=pair), float(amt)))
    for ccy in base.rates:
        bps = stress.rate_shocks_bps.get(ccy, stress.rates_shift_bps)
        if bps:
            shocks.append(FactorShock(RateZero(currency=ccy, tenor="ALL"), float(bps) / 10000.0))
    return tuple(shocks)


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
            rate_shocks_bps[factor.currency] = amount * 10000.0
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
    "kind_to_category",
    "scenario_from_market_scenario",
    "scenario_from_stress",
    "scenario_to_market_scenario",
    "scenario_to_stress",
    "threshold_breached",
]
