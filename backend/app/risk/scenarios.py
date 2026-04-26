"""Historical scenario generation (M2.2).

Pipeline:

    FactorObservationSeries
      → AggregateFactorChange[]   (per-observation aggregate moves)
      → MarketScenario[]          (typed RiskFactor shocks vs a base snapshot)
      → shocked MarketSnapshot[]  (via MarketSnapshot.apply / bump)

Approximation VaR paths (`LINEAR` / ``DELTA_GAMMA``) still consume raw observation
arrays. ``FULL_REVALUATION`` historical VaR (M2.3) consumes shocked snapshots
from this module via ``iter_historical_shocked_snapshots`` (one snapshot at a
time). ``historical_shocked_snapshots`` remains a list wrapper for callers
that still need the materialized collection.

Units (aligned with ``FactorObservationSeries`` and ``MarketSnapshot.bump``):
- equity / FX: relative return (0.01 = +1%)
- vol: relative change of vol level (0.07 ≈ +7% of current vol)
- rates: observation / panel stores **basis points**; engine-facing
  ``FactorChange`` / bump uses **decimal** via
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

from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.risk.factor_panel import FactorPanelObservation, HistoricalFactorPanel
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero, RiskFactor
from app.risk.historical_data import FactorObservationSeries, HistoricalMarketDataset
from app.risk.shock_units import bps_to_decimal_rate, decimal_rate_to_bps


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
) -> tuple[FactorChange, ...]:
    """Broadcast aggregate moves onto typed factors present in ``base``.

    Order matches ``shock_snapshot``: equity spots, equity vols, FX spots,
    FX vols, then parallel rates. Zero-amount moves are omitted.
    """
    shocks: list[FactorChange] = []
    eq = change.equity_return
    if eq:
        for sym in base.equity_spots:
            shocks.append(FactorChange(EquitySpot(sym), eq))
    vol = change.vol_move
    if vol:
        for sym in base.equity_vols:
            shocks.append(FactorChange(EquityVol(underlying=sym), vol))
    fx = change.fx_return
    if fx:
        for pair in base.fx_spots:
            shocks.append(FactorChange(FXSpot(pair), fx))
    if vol:
        for pair in base.fx_vols:
            shocks.append(FactorChange(FXVol(pair=pair), vol))
    bps = change.rate_move_bps
    if bps:
        decimal_shift = bps_to_decimal_rate(bps)
        for ccy in base.rates:
            shocks.append(FactorChange(RateZero(currency=ccy, tenor="ALL"), decimal_shift))
    return tuple(shocks)


def market_scenario_from_change(
    change: AggregateFactorChange,
    base: MarketSnapshot,
    *,
    id_prefix: str = "hist",
) -> MarketScenario:
    """Build a typed ``MarketScenario`` by expanding one aggregate observation."""
    shocks = expand_aggregate_change(change, base)
    return MarketScenario(
        id=f"{id_prefix}_{change.index}",
        name=f"Historical observation {change.index}",
        shocks=shocks,
        kind=ScenarioKind.HISTORICAL_STYLE,
        description=(
            "Observation-derived historical replay of aggregate equity/vol/rate/FX "
            "moves onto factors present in the base market snapshot "
            "(not an illustrative crisis preset)."
        ),
        observation_index=change.index,
    )


def historical_market_scenarios(
    base: MarketSnapshot,
    source: HistoricalMarketDataset | FactorObservationSeries,
    *,
    id_prefix: str = "hist",
) -> list[MarketScenario]:
    """Generate one ``MarketScenario`` per historical observation."""
    series = source if isinstance(source, FactorObservationSeries) else source.factor_observations()
    return [market_scenario_from_change(c, base, id_prefix=id_prefix) for c in iter_aggregate_changes(series)]


def apply_market_scenario(base: MarketSnapshot, scenario: MarketScenario) -> MarketSnapshot:
    """Apply typed shocks via ``MarketSnapshot.apply``; empty shocks leave marks unchanged."""
    pairs = scenario.shock_pairs()
    out = base.apply(pairs) if pairs else base
    if out.id == f"{base.id}:{scenario.id}":
        return out
    return out.model_copy(update={"id": f"{base.id}:{scenario.id}"})


def iter_shocked_snapshots(
    base: MarketSnapshot,
    scenarios: Sequence[MarketScenario],
) -> Iterator[MarketSnapshot]:
    """Yield one shocked snapshot at a time (independent shocks, not cumulative)."""
    for scenario in scenarios:
        yield apply_market_scenario(base, scenario)


def shocked_snapshots(
    base: MarketSnapshot,
    scenarios: Sequence[MarketScenario],
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


def factor_changes_from_panel_observation(
    observation: FactorPanelObservation,
) -> tuple[FactorChange, ...]:
    """One panel row → typed shocks. Zero-amount moves are omitted."""
    shocks: list[FactorChange] = []
    for factor, amount in observation.changes.items():
        bump = panel_amount_to_bump(factor, amount)
        if bump:
            shocks.append(FactorChange(factor, bump))
    return tuple(shocks)


def market_scenario_from_panel_observation(
    observation: FactorPanelObservation,
    *,
    index: int,
    id_prefix: str = "hist_panel",
) -> MarketScenario:
    """Build a typed ``MarketScenario`` from one per-factor panel row."""
    return MarketScenario(
        id=f"{id_prefix}_{index}",
        name=f"Panel observation {index}",
        shocks=factor_changes_from_panel_observation(observation),
        kind=ScenarioKind.HISTORICAL_STYLE,
        description=(
            "Per-factor historical replay from HistoricalFactorPanel "
            "(not a four-macro broadcast)."
        ),
        observation_index=index,
    )


def historical_market_scenarios_from_panel(
    panel: HistoricalFactorPanel,
    *,
    id_prefix: str = "hist_panel",
) -> list[MarketScenario]:
    """One ``MarketScenario`` per panel date; shocks stay per name / tenor."""
    return [
        market_scenario_from_panel_observation(obs, index=i, id_prefix=id_prefix)
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


def to_stress_scenario(scenario: MarketScenario) -> StressScenario:
    """Convert typed shocks to ``StressScenario`` dict fields for ``shock_snapshot``.

    Aggregate scalar fields stay at zero; per-name dicts carry the moves so
    ``shock_snapshot(base, to_stress_scenario(s))`` matches ``apply_market_scenario``.
    """
    equity_shocks: dict[str, float] = {}
    vol_shocks: dict[str, float] = {}
    rate_shocks_bps: dict[str, float] = {}
    fx_shocks: dict[str, float] = {}
    for change in scenario.shocks:
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
        id=scenario.id,
        name=scenario.name,
        description=scenario.description,
        kind=scenario.kind,
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
    "shocked_snapshots",
    "to_stress_scenario",
]
