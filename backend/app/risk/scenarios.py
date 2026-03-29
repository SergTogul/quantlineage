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
- rates: observation series stores **basis points**; bump uses **decimal**
  (1bp → ``RateZero(..., "ALL")`` with amount ``1/10000``)
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from app.domain.models import MarketSnapshot, ScenarioKind, StressScenario
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero, RiskFactor
from app.risk.historical_data import FactorObservationSeries, HistoricalMarketDataset


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
        decimal_shift = bps / 10000.0
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
            rate_shocks_bps[factor.currency] = amount * 10000.0
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
    "historical_market_scenarios",
    "historical_shocked_snapshots",
    "iter_aggregate_changes",
    "iter_historical_shocked_snapshots",
    "iter_shocked_snapshots",
    "market_scenario_from_change",
    "shocked_snapshots",
    "to_stress_scenario",
]
