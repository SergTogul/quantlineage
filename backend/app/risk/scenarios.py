"""Historical scenario generation (M2.2 / R0.4.2-G).

Pipeline:

    FactorObservationSeries
      → AggregateFactorChange[]   (per-observation aggregate moves)
      → Scenario[]                (typed FactorShock vs the live snapshot)
      → shocked MarketSnapshot[]  (via apply_scenario)

    ``MarketScenario`` / ``FactorChange`` remain adapters (like deprecated
    ``StressScenario``). Callers that still need ``MarketScenario`` convert at
    the boundary via ``scenario_to_market_scenario``.

    Approximation VaR paths (`LINEAR` / ``DELTA_GAMMA``) still consume raw observation
    arrays. ``FULL_REVALUATION`` historical VaR (M2.3) consumes shocked snapshots
    from this module via ``iter_historical_shocked_snapshots`` (one snapshot at a
    time). ``historical_shocked_snapshots`` remains a list wrapper for callers
    that still need the materialized collection.

Units (aligned with ``FactorObservationSeries`` and ``MarketSnapshot.bump``):
- equity / FX: relative return (0.01 = +1%)
- vol: relative change of vol level (0.07 ≈ +7% of current vol)
- rates: observation / panel stores **basis points**; engine-facing
  ``FactorShock`` / bump uses **decimal** via
  :func:`app.risk.shock_units.bps_to_decimal_rate` at expand boundaries
  (1bp → ``RateZero(..., "ALL")`` with amount ``0.0001``)

Opt-in ``HistoricalFactorPanel`` path (R0.5.3 leftover):
``iter_panel_shocked_snapshots`` applies per-name / per-tenor panel columns
without broadcasting four-macro aggregates. Default
``iter_historical_shocked_snapshots`` is unchanged. Rate panel units stay
basis points and are converted here before bump.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.risk.factor_panel import FactorPanelObservation, HistoricalFactorPanel
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero, RiskFactor
from app.risk.historical_data import FactorObservationSeries, HistoricalMarketDataset
from app.risk.shock_units import bps_to_decimal_rate, decimal_rate_to_bps

if TYPE_CHECKING:
    from app.risk.scenario_model import FactorShock, Scenario


@dataclass(frozen=True, slots=True)
class AggregateFactorChange:
    """One historical observation as aggregate factor moves (dataset units)."""

    index: int
    equity_return: float
    vol_move: float
    rate_move_bps: float
    fx_return: float


@dataclass(frozen=True, slots=True)
class FactorChange:
    """Single typed factor shock in ``MarketSnapshot.bump`` units."""

    factor: RiskFactor
    amount: float


@dataclass(frozen=True, slots=True)
class MarketScenario:
    """Multi-factor market scenario ready to apply to a ``MarketSnapshot``."""

    id: str
    name: str
    shocks: tuple[FactorChange, ...]
    kind: ScenarioKind = ScenarioKind.HISTORICAL_STYLE
    description: str = ""
    observation_index: int | None = None

    def shock_pairs(self) -> list[tuple[RiskFactor, float]]:
        """Ordered ``(RiskFactor, amount)`` list for ``MarketSnapshot.apply``."""
        return [(s.factor, s.amount) for s in self.shocks]


def iter_aggregate_changes(series: FactorObservationSeries) -> list[AggregateFactorChange]:
    """Map observation arrays to one ``AggregateFactorChange`` per row."""
    return [
        AggregateFactorChange(
            index=i,
            equity_return=float(series.equity_returns[i]),
            vol_move=float(series.vol_moves[i]),
            rate_move_bps=float(series.rate_moves_bps[i]),
            fx_return=float(series.fx_returns[i]),
        )
        for i in range(series.n_observations)
    ]


def expand_aggregate_change(
    change: AggregateFactorChange,
    base: MarketSnapshot,
) -> tuple[FactorShock, ...]:
    """Broadcast aggregate moves onto typed factors present in ``base``.

    Order matches ``shock_snapshot``: equity spots, equity vols, FX spots,
    FX vols, then parallel rates. Zero-amount moves are omitted. Rate
    bp→decimal only via ``shock_units``.
    """
    from app.risk.scenario_model import FactorShock

    shocks: list[FactorShock] = []
    eq = change.equity_return
    if eq:
        for sym in base.equity_spots:
            shocks.append(FactorShock(EquitySpot(sym), eq))
    vol = change.vol_move
    if vol:
        for sym in base.equity_vols:
            shocks.append(FactorShock(EquityVol(underlying=sym), vol))
    fx = change.fx_return
    if fx:
        for pair in base.fx_spots:
            shocks.append(FactorShock(FXSpot(pair), fx))
    if vol:
        for pair in base.fx_vols:
            shocks.append(FactorShock(FXVol(pair=pair), vol))
    bps = change.rate_move_bps
    if bps:
        decimal_shift = bps_to_decimal_rate(bps)
        for ccy in base.rates:
            shocks.append(FactorShock(RateZero(currency=ccy, tenor="ALL"), decimal_shift))
    return tuple(shocks)


_HIST_REPLAY_DESCRIPTION = (
    "Observation-derived historical replay of aggregate equity/vol/rate/FX "
    "moves onto factors present in the base market snapshot "
    "(not an illustrative crisis preset)."
)


def scenario_from_change(
    change: AggregateFactorChange,
    base: MarketSnapshot,
    *,
    id_prefix: str = "hist",
) -> Scenario:
    """Build a canonical ``Scenario`` by expanding one aggregate observation."""
    from app.risk.scenario_model import Scenario, ScenarioCategory

    return Scenario(
        id=f"{id_prefix}_{change.index}",
        name=f"Historical observation {change.index}",
        category=ScenarioCategory.HISTORICAL_REPLAY,
        description=_HIST_REPLAY_DESCRIPTION,
        shocks=expand_aggregate_change(change, base),
        metadata={"observation_index": change.index},
    )


def market_scenario_from_change(
    change: AggregateFactorChange,
    base: MarketSnapshot,
    *,
    id_prefix: str = "hist",
) -> MarketScenario:
    """Adapter: canonical historical ``Scenario`` → ``MarketScenario``."""
    from app.risk.scenario_model import scenario_to_market_scenario

    return scenario_to_market_scenario(scenario_from_change(change, base, id_prefix=id_prefix))


def historical_market_scenarios(
    base: MarketSnapshot,
    source: HistoricalMarketDataset | FactorObservationSeries,
    *,
    id_prefix: str = "hist",
) -> list[Scenario]:
    """Generate one canonical ``Scenario`` per historical observation."""
    series = source if isinstance(source, FactorObservationSeries) else source.factor_observations()
    return [scenario_from_change(c, base, id_prefix=id_prefix) for c in iter_aggregate_changes(series)]


def apply_market_scenario(base: MarketSnapshot, scenario: MarketScenario | Scenario) -> MarketSnapshot:
    """Adapter: apply ``MarketScenario`` or ``Scenario`` via ``apply_scenario``."""
    from app.risk.scenario_engine import apply_scenario

    return apply_scenario(base, scenario)


def iter_shocked_snapshots(
    base: MarketSnapshot,
    scenarios: Sequence[MarketScenario | Scenario],
) -> Iterator[MarketSnapshot]:
    """Yield one shocked snapshot at a time (independent shocks, not cumulative)."""
    from app.risk.scenario_engine import apply_scenario

    for scenario in scenarios:
        yield apply_scenario(base, scenario)


def shocked_snapshots(
    base: MarketSnapshot,
    scenarios: Sequence[MarketScenario | Scenario],
) -> list[MarketSnapshot]:
    """Apply each scenario to ``base`` (independent shocks, not cumulative)."""
    return list(iter_shocked_snapshots(base, scenarios))


def iter_historical_shocked_snapshots(
    base: MarketSnapshot,
    source: HistoricalMarketDataset | FactorObservationSeries,
    *,
    id_prefix: str = "hist",
) -> Iterator[MarketSnapshot]:
    """End-to-end: observations → scenarios → shocked snapshots, one at a time."""
    yield from iter_shocked_snapshots(
        base, historical_market_scenarios(base, source, id_prefix=id_prefix)
    )


def historical_shocked_snapshots(
    base: MarketSnapshot,
    source: HistoricalMarketDataset | FactorObservationSeries,
    *,
    id_prefix: str = "hist",
) -> list[MarketSnapshot]:
    """End-to-end: observations → scenarios → shocked snapshots."""
    return list(iter_historical_shocked_snapshots(base, source, id_prefix=id_prefix))


def panel_amount_to_bump(factor: RiskFactor, amount: float) -> float:
    """Convert a panel change into ``MarketSnapshot.bump`` units.

    Panel rate moves are basis points (``1.0`` = +1bp); bump uses decimal
    rate via :func:`bps_to_decimal_rate`. Equity / FX / vol stay relative.
    """
    if isinstance(factor, RateZero):
        return bps_to_decimal_rate(amount)
    return float(amount)


def factor_shocks_from_panel_observation(
    observation: FactorPanelObservation,
) -> tuple[FactorShock, ...]:
    """One panel row → typed FactorShock. Zero-amount moves are omitted."""
    from app.risk.scenario_model import FactorShock

    shocks: list[FactorShock] = []
    for factor, amount in observation.changes.items():
        bump = panel_amount_to_bump(factor, amount)
        if bump:
            shocks.append(FactorShock(factor, bump))
    return tuple(shocks)


def factor_changes_from_panel_observation(
    observation: FactorPanelObservation,
) -> tuple[FactorChange, ...]:
    """Adapter: panel row → ``FactorChange`` (MarketScenario)."""
    return tuple(s.as_factor_change() for s in factor_shocks_from_panel_observation(observation))


_PANEL_REPLAY_DESCRIPTION = (
    "Per-factor historical replay from HistoricalFactorPanel "
    "(not a four-macro broadcast)."
)


def scenario_from_panel_observation(
    observation: FactorPanelObservation,
    *,
    index: int,
    id_prefix: str = "hist_panel",
) -> Scenario:
    """Build a canonical ``Scenario`` from one per-factor panel row."""
    from app.risk.scenario_model import Scenario, ScenarioCategory

    return Scenario(
        id=f"{id_prefix}_{index}",
        name=f"Panel observation {index}",
        category=ScenarioCategory.HISTORICAL_REPLAY,
        description=_PANEL_REPLAY_DESCRIPTION,
        shocks=factor_shocks_from_panel_observation(observation),
        metadata={"observation_index": index},
    )


def market_scenario_from_panel_observation(
    observation: FactorPanelObservation,
    *,
    index: int,
    id_prefix: str = "hist_panel",
) -> MarketScenario:
    """Adapter: panel ``Scenario`` → ``MarketScenario``."""
    from app.risk.scenario_model import scenario_to_market_scenario

    return scenario_to_market_scenario(
        scenario_from_panel_observation(observation, index=index, id_prefix=id_prefix)
    )


def historical_market_scenarios_from_panel(
    panel: HistoricalFactorPanel,
    *,
    id_prefix: str = "hist_panel",
) -> list[Scenario]:
    """One canonical ``Scenario`` per panel date; shocks stay per name / tenor."""
    return [
        scenario_from_panel_observation(obs, index=i, id_prefix=id_prefix)
        for i, obs in enumerate(panel.observations)
    ]


def iter_panel_shocked_snapshots(
    base: MarketSnapshot,
    panel: HistoricalFactorPanel,
    *,
    id_prefix: str = "hist_panel",
) -> Iterator[MarketSnapshot]:
    """Apply per-factor panel moves to ``base`` (independent, not cumulative).

    Does **not** broadcast one equity/rate aggregate onto every name/tenor.
    Missing snapshot marks fail closed via ``MarketSnapshot.bump``.
    """
    yield from iter_shocked_snapshots(
        base, historical_market_scenarios_from_panel(panel, id_prefix=id_prefix)
    )


def to_stress_scenario(scenario: MarketScenario | Scenario) -> StressScenario:
    """Adapter: typed shocks → ``StressScenario`` dict fields for ``shock_snapshot``.

    Aggregate scalar fields stay at zero; per-name dicts carry the moves so
    ``shock_snapshot(base, to_stress_scenario(s))`` matches ``apply_scenario``.
    """
    from app.risk.scenario_model import Scenario as CanonicalScenario
    from app.risk.scenario_model import category_to_kind, scenario_to_market_scenario

    if isinstance(scenario, CanonicalScenario):
        adapted = scenario_to_market_scenario(scenario)
        kind = category_to_kind(scenario.category)
    else:
        adapted = scenario
        kind = scenario.kind
    equity_shocks: dict[str, float] = {}
    vol_shocks: dict[str, float] = {}
    rate_shocks_bps: dict[str, float] = {}
    fx_shocks: dict[str, float] = {}
    for change in adapted.shocks:
        factor = change.factor
        amount = change.amount
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
        id=adapted.id,
        name=adapted.name,
        description=adapted.description,
        kind=kind,
        equity_shocks=equity_shocks,
        vol_shocks=vol_shocks,
        rate_shocks_bps=rate_shocks_bps,
        fx_shocks=fx_shocks,
    )


__all__ = [
    "AggregateFactorChange",
    "FactorChange",
    "MarketScenario",
    "apply_market_scenario",
    "expand_aggregate_change",
    "factor_changes_from_panel_observation",
    "factor_shocks_from_panel_observation",
    "historical_market_scenarios",
    "historical_market_scenarios_from_panel",
    "historical_shocked_snapshots",
    "iter_aggregate_changes",
    "iter_historical_shocked_snapshots",
    "iter_panel_shocked_snapshots",
    "iter_shocked_snapshots",
    "market_scenario_from_change",
    "market_scenario_from_panel_observation",
    "panel_amount_to_bump",
    "scenario_from_change",
    "scenario_from_panel_observation",
    "shocked_snapshots",
    "to_stress_scenario",
]
