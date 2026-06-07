"""Historical crisis library (M3.3).

Crisis presets are **HISTORICAL_APPROXIMATION** only: stylized, documented
multi-factor shocks inspired by named market episodes. They are never exact
path replays of observed marks.

``HISTORICAL_REPLAY`` is reserved for observation-derived scenarios built from
``FactorObservationSeries`` / ``MarketScenario`` (see
``replay_scenarios_from_observations`` and ``scenario_from_market_scenario``).

Units for template scalars (same as ``StressScenario`` / ``MarketSnapshot.bump``):
- equity / FX: relative return (``-0.35`` = −35%)
- vol: relative change of vol level (``1.0`` = +100% of current vol)
- rates: parallel shift in basis points (``-100`` → −1% absolute rate)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.risk.historical_data import FactorObservationSeries, HistoricalMarketDataset
from app.risk.scenario_model import (
    BroadcastScenarioDefinition,
    BroadcastShockTemplate,
    Scenario,
    ScenarioCategory,
    ScenarioSeverity,
    ScenarioThreshold,
    apply_scenario,
    scenario_from_market_scenario,
    scenario_from_stress,
    scenario_to_stress,
)
from app.risk.scenarios import historical_market_scenarios

APPROXIMATION_DISCLAIMER = (
    "HISTORICAL_APPROXIMATION — stylized multi-factor shock inspired by a named "
    "episode; not an exact replay of observed market paths."
)

REPLAY_DISCLAIMER = (
    "HISTORICAL_REPLAY — observation-derived factor moves applied to the base "
    "snapshot; not a crisis-library stylized preset."
)


@dataclass(frozen=True, slots=True)
class CrisisShockTemplate:
    """Aggregate scalar moves expanded onto factors present in a base snapshot."""

    equity_shock: float = 0.0
    vol_shock: float = 0.0
    rates_shift_bps: float = 0.0
    fx_shock: float = 0.0


@dataclass(frozen=True, slots=True)
class CrisisDefinition:
    """Documented crisis preset (always an approximation unless category says otherwise)."""

    id: str
    name: str
    episode: str
    description: str
    shocks: CrisisShockTemplate
    threshold: ScenarioThreshold = field(default_factory=lambda: ScenarioThreshold(max_loss_pct=0.15))
    severity: ScenarioSeverity | None = ScenarioSeverity.SEVERE
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("CrisisDefinition.id must be non-empty")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def _crisis_metadata(defn: CrisisDefinition) -> dict[str, Any]:
    meta = {
        "labeling": ScenarioCategory.HISTORICAL_APPROXIMATION.value,
        "episode": defn.episode,
        "exact_replay": False,
        "source": "crisis_library",
        "disclaimer": APPROXIMATION_DISCLAIMER,
    }
    meta.update(dict(defn.metadata))
    # Hard invariants — callers cannot override honesty flags via metadata.
    meta["labeling"] = ScenarioCategory.HISTORICAL_APPROXIMATION.value
    meta["exact_replay"] = False
    meta["disclaimer"] = APPROXIMATION_DISCLAIMER
    return meta


def crisis_as_broadcast(defn: CrisisDefinition) -> BroadcastScenarioDefinition:
    """Library template for apply-time expansion (not a frozen ``Scenario``)."""
    return BroadcastScenarioDefinition(
        id=defn.id,
        name=defn.name,
        description=defn.description,
        category=ScenarioCategory.HISTORICAL_APPROXIMATION,
        shocks=BroadcastShockTemplate(
            equity_shock=defn.shocks.equity_shock,
            vol_shock=defn.shocks.vol_shock,
            rates_shift_bps=defn.shocks.rates_shift_bps,
            fx_shock=defn.shocks.fx_shock,
        ),
        threshold=defn.threshold,
        severity=defn.severity,
        metadata=_crisis_metadata(defn),
    )


def crisis_as_stress(defn: CrisisDefinition) -> StressScenario:
    """Wire/API shape for legacy stress endpoints (kind remains HISTORICAL_STYLE)."""
    return StressScenario(
        id=defn.id,
        name=defn.name,
        description=defn.description,
        kind=ScenarioKind.HISTORICAL_STYLE,
        equity_shock=defn.shocks.equity_shock,
        vol_shock=defn.shocks.vol_shock,
        rates_shift_bps=defn.shocks.rates_shift_bps,
        fx_shock=defn.shocks.fx_shock,
        max_loss_pct=defn.threshold.max_loss_pct,
    )


def crisis_scenario(defn: CrisisDefinition, base: MarketSnapshot) -> Scenario:
    """Expand a crisis preset onto ``base`` as a formal HISTORICAL_APPROXIMATION."""
    return scenario_from_stress(
        crisis_as_stress(defn),
        base,
        historical_as=ScenarioCategory.HISTORICAL_APPROXIMATION,
        severity=defn.severity,
        metadata=_crisis_metadata(defn),
    )


def crisis_scenarios(base: MarketSnapshot, library: Sequence[CrisisDefinition] | None = None) -> list[Scenario]:
    """Expand every library preset against ``base`` (independent, not cumulative)."""
    defs = library if library is not None else CRISIS_LIBRARY
    return [crisis_scenario(d, base) for d in defs]


def crisis_stress_scenarios(library: Sequence[CrisisDefinition] | None = None) -> list[StressScenario]:
    """Legacy ``StressScenario`` list for threat evaluation / OpenAPI."""
    defs = library if library is not None else CRISIS_LIBRARY
    return [crisis_as_stress(d) for d in defs]


def is_historical_approximation(scenario: Scenario) -> bool:
    return scenario.category == ScenarioCategory.HISTORICAL_APPROXIMATION


def is_historical_replay(scenario: Scenario) -> bool:
    return scenario.category == ScenarioCategory.HISTORICAL_REPLAY


def assert_honest_historical_labeling(scenario: Scenario) -> None:
    """Raise if an approximation claims exact replay (or vice versa without evidence)."""
    meta = dict(scenario.metadata)
    if scenario.category == ScenarioCategory.HISTORICAL_APPROXIMATION:
        if meta.get("exact_replay") is True:
            raise ValueError(
                f"scenario {scenario.id!r} is HISTORICAL_APPROXIMATION but metadata "
                "claims exact_replay=True"
            )
        if "exact replay" in scenario.description.lower() and "not an exact" not in scenario.description.lower():
            raise ValueError(
                f"scenario {scenario.id!r} description must not present an approximation as exact replay"
            )
    if scenario.category == ScenarioCategory.HISTORICAL_REPLAY:
        if meta.get("exact_replay") is False and meta.get("observation_index") is None:
            raise ValueError(
                f"scenario {scenario.id!r} is HISTORICAL_REPLAY without observation_index"
            )


def replay_scenarios_from_observations(
    base: MarketSnapshot,
    source: HistoricalMarketDataset | FactorObservationSeries,
    *,
    id_prefix: str = "hist",
) -> list[Scenario]:
    """Build formal HISTORICAL_REPLAY scenarios from observation series (not crisis presets)."""
    markets = historical_market_scenarios(base, source, id_prefix=id_prefix)
    out: list[Scenario] = []
    for market in markets:
        formal = scenario_from_market_scenario(
            market,
            category=ScenarioCategory.HISTORICAL_REPLAY,
            metadata={
                "labeling": ScenarioCategory.HISTORICAL_REPLAY.value,
                "exact_replay": True,
                "source": "observation_series",
                "disclaimer": REPLAY_DISCLAIMER,
            },
        )
        out.append(formal)
    return out


# ---------------------------------------------------------------------------
# Documented crisis presets (magnitudes are illustrative approximations)
# ---------------------------------------------------------------------------

CRISIS_LIBRARY: tuple[CrisisDefinition, ...] = (
    CrisisDefinition(
        id="lehman_2008",
        name="2008 Lehman / GFC (approx)",
        episode="2008-09 Lehman Brothers / Global Financial Crisis",
        description=(
            f"{APPROXIMATION_DISCLAIMER} Rough risk-off profile: deep equity drawdown, "
            "vol spike, and flight-to-quality rate cuts — not a day-by-day 2008 path replay."
        ),
        shocks=CrisisShockTemplate(
            equity_shock=-0.35,
            vol_shock=1.00,
            rates_shift_bps=-100.0,
            fx_shock=-0.05,
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.15),
        severity=ScenarioSeverity.SEVERE,
        metadata={"period": "2008-09", "aliases": ("gfc_style",)},
    ),
    CrisisDefinition(
        id="covid_2020_03",
        name="March 2020 COVID crash (approx)",
        episode="2020-03 COVID-19 market crash",
        description=(
            f"{APPROXIMATION_DISCLAIMER} Fast equity selloff with an extreme implied-vol "
            "expansion and policy-rate cuts — stylized, not a March 2020 tick replay."
        ),
        shocks=CrisisShockTemplate(
            equity_shock=-0.30,
            vol_shock=1.50,
            rates_shift_bps=-75.0,
            fx_shock=-0.03,
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.15),
        severity=ScenarioSeverity.SEVERE,
        metadata={"period": "2020-03", "aliases": ("covid_style",)},
    ),
    CrisisDefinition(
        id="rates_shock_2022",
        name="2022 rates shock (approx)",
        episode="2022 global hiking / rates regime break",
        description=(
            f"{APPROXIMATION_DISCLAIMER} Abrupt parallel rate rise with equity weakness "
            "and moderate vol — illustrative of 2022 hiking stress, not a curve-path replay."
        ),
        shocks=CrisisShockTemplate(
            equity_shock=-0.18,
            vol_shock=0.40,
            rates_shift_bps=250.0,
            fx_shock=0.02,
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.12),
        severity=ScenarioSeverity.HIGH,
        metadata={"period": "2022", "aliases": ("rate_shock",)},
    ),
    CrisisDefinition(
        id="euro_crisis_2011",
        name="2011 Eurozone crisis (approx)",
        episode="2011 Eurozone sovereign / banking stress",
        description=(
            f"{APPROXIMATION_DISCLAIMER} Equity risk-off, EUR weakness, and elevated vol "
            "inspired by 2011 sovereign stress — not a sovereign-spread path replay."
        ),
        shocks=CrisisShockTemplate(
            equity_shock=-0.22,
            vol_shock=0.70,
            rates_shift_bps=50.0,
            fx_shock=-0.12,
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.12),
        severity=ScenarioSeverity.HIGH,
        metadata={"period": "2011"},
    ),
    CrisisDefinition(
        id="volmageddon_2018",
        name="Volmageddon 2018 (approx)",
        episode="2018-02 short-vol / VIX spike (Volmageddon)",
        description=(
            f"{APPROXIMATION_DISCLAIMER} Extreme implied-vol dislocation with a modest "
            "equity drop — stylized short-vol unwind, not an exact Feb-2018 replay."
        ),
        shocks=CrisisShockTemplate(
            equity_shock=-0.10,
            vol_shock=2.00,
            rates_shift_bps=0.0,
            fx_shock=0.0,
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.10),
        severity=ScenarioSeverity.HIGH,
        metadata={"period": "2018-02", "aliases": ("vol_dislocation",)},
    ),
    CrisisDefinition(
        id="china_shock_2015",
        name="2015 China shock (approx)",
        episode="2015 China equity / FX devaluation stress",
        description=(
            f"{APPROXIMATION_DISCLAIMER} Equity selloff, FX pressure, and vol expansion "
            "inspired by 2015 China stress — not a CSI/FX path replay."
        ),
        shocks=CrisisShockTemplate(
            equity_shock=-0.20,
            vol_shock=0.60,
            rates_shift_bps=-25.0,
            fx_shock=-0.08,
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.10),
        severity=ScenarioSeverity.HIGH,
        metadata={"period": "2015-08"},
    ),
    CrisisDefinition(
        id="dotcom_equity_crash",
        name="Dot-com-style equity crash (approx)",
        episode="2000–2002 tech / equity bear market (stylized)",
        description=(
            f"{APPROXIMATION_DISCLAIMER} Large equity crash with elevated vol and mild "
            "flight-to-quality rates — dot-com-style proxy, not a 2000–02 path replay."
        ),
        shocks=CrisisShockTemplate(
            equity_shock=-0.45,
            vol_shock=0.90,
            rates_shift_bps=-75.0,
            fx_shock=-0.02,
        ),
        threshold=ScenarioThreshold(max_loss_pct=0.18),
        severity=ScenarioSeverity.SEVERE,
        metadata={"period": "2000-2002", "aliases": ("tech_crash",)},
    ),
)


CRISIS_BY_ID: Mapping[str, CrisisDefinition] = MappingProxyType({c.id: c for c in CRISIS_LIBRARY})

# Legacy StressScenario list used by threat APIs / THREAT_SCENARIOS.
CRISIS_STRESS_SCENARIOS: list[StressScenario] = crisis_stress_scenarios()


def get_crisis(crisis_id: str) -> CrisisDefinition:
    """Lookup by id; raises KeyError if unknown."""
    try:
        return CRISIS_BY_ID[crisis_id]
    except KeyError as exc:
        raise KeyError(f"unknown crisis id: {crisis_id!r}") from exc


def apply_crisis(base: MarketSnapshot, crisis_id: str) -> MarketSnapshot:
    """Apply one library crisis (approximation) to ``base`` via formal Scenario."""
    return apply_scenario(base, crisis_scenario(get_crisis(crisis_id), base))


# Re-export adapters useful to callers wiring formal ↔ legacy.
__all__ = [
    "APPROXIMATION_DISCLAIMER",
    "CRISIS_BY_ID",
    "CRISIS_LIBRARY",
    "CRISIS_STRESS_SCENARIOS",
    "CrisisDefinition",
    "CrisisShockTemplate",
    "REPLAY_DISCLAIMER",
    "apply_crisis",
    "assert_honest_historical_labeling",
    "crisis_as_broadcast",
    "crisis_as_stress",
    "crisis_scenario",
    "crisis_scenarios",
    "crisis_stress_scenarios",
    "get_crisis",
    "is_historical_approximation",
    "is_historical_replay",
    "replay_scenarios_from_observations",
    "scenario_to_stress",
]
