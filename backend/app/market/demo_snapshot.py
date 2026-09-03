"""Validated bridge from legacy position sample marks to a market snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import (
    BondPosition,
    CapFloorPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    Portfolio,
    SwapPosition,
    SwaptionPosition,
)


@dataclass(frozen=True)
class SampleMarkCandidate:
    position_id: str
    value: float
    legacy_field: str


class ConflictingSampleMarkError(ValueError):
    """Raised when legacy trades propose unequal marks for one market key."""

    def __init__(self, factor_key: str, candidates: tuple[SampleMarkCandidate, ...]):
        self.factor_key = factor_key
        self.candidates = candidates
        details = ", ".join(
            f"{candidate.position_id}.{candidate.legacy_field}={candidate.value!r}"
            for candidate in candidates
        )
        super().__init__(f"Conflicting sample marks for {factor_key}: {details}")


class MissingMarketDataError(ValueError):
    """Raised when a supplied snapshot lacks a required market observable."""

    def __init__(self, factor_key: str):
        self.factor_key = factor_key
        super().__init__(f"Missing market data for {factor_key}")


class DemoSampleMarksSnapshotAdapter:
    """Create demo/test snapshots only after validating all shared sample marks."""

    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        candidates: dict[tuple[str, str], list[SampleMarkCandidate]] = {}

        def add(group: str, key: str, position_id: str, field: str, value: float) -> None:
            candidates.setdefault((group, key), []).append(
                SampleMarkCandidate(position_id, float(value), field)
            )

        for position in portfolio.positions:
            if isinstance(position, EquityPosition):
                add("equity_spots", position.symbol, position.id, "price", position.price)
            elif isinstance(position, (EuropeanOptionPosition, EquityFuturePosition)):
                add("equity_spots", position.symbol, position.id, "spot", position.spot)
                add(
                    "rates",
                    "USD",
                    position.id,
                    "risk_free_rate",
                    position.risk_free_rate,
                )
                add(
                    "dividend_yields",
                    position.symbol,
                    position.id,
                    "dividend_yield",
                    position.dividend_yield,
                )
                if isinstance(position, EuropeanOptionPosition):
                    add(
                        "equity_vols",
                        position.symbol,
                        position.id,
                        "volatility",
                        position.volatility,
                    )
            elif isinstance(position, BondPosition):
                add("rates", position.currency, position.id, "yield_rate", position.yield_rate)
            elif isinstance(position, SwapPosition):
                add(
                    "rates",
                    position.currency,
                    position.id,
                    "market_swap_rate",
                    position.market_swap_rate,
                )
            elif isinstance(position, InterestRateFuturePosition):
                add(
                    "rates",
                    position.currency,
                    position.id,
                    "forward_rate",
                    position.forward_rate,
                )
            elif isinstance(position, CapFloorPosition):
                add(
                    "rates",
                    position.currency,
                    position.id,
                    "discount_rate",
                    position.discount_rate,
                )
                add(
                    "projection_rates",
                    position.currency,
                    position.id,
                    "forward_rate",
                    position.forward_rate,
                )
            elif isinstance(position, SwaptionPosition):
                add(
                    "rates",
                    position.currency,
                    position.id,
                    "discount_rate",
                    position.discount_rate,
                )
                add(
                    "projection_rates",
                    position.currency,
                    position.id,
                    "forward_swap_rate",
                    position.forward_swap_rate,
                )
            elif isinstance(position, (FXForwardPosition, FXOptionPosition)):
                add("fx_spots", position.pair, position.id, "spot", position.spot)
                add(
                    "rates",
                    position.pair[-3:],
                    position.id,
                    "domestic_rate",
                    position.domestic_rate,
                )
                add(
                    "rates",
                    position.pair[:3],
                    position.id,
                    "foreign_rate",
                    position.foreign_rate,
                )
                if isinstance(position, FXOptionPosition):
                    add(
                        "fx_vols",
                        position.pair,
                        position.id,
                        "volatility",
                        position.volatility,
                    )

        validated: dict[str, dict[str, float]] = {
            "equity_spots": {},
            "equity_vols": {},
            "fx_spots": {},
            "fx_vols": {},
            "rates": {},
            "projection_rates": {},
            "dividend_yields": {},
        }
        for (group, key), proposed in candidates.items():
            first = proposed[0].value
            if any(candidate.value != first for candidate in proposed[1:]):
                raise ConflictingSampleMarkError(
                    f"{group}[{key}]", tuple(proposed)
                )
            validated[group][key] = first

        return MarketSnapshot(id="demo_sample_marks", **validated)


__all__ = [
    "ConflictingSampleMarkError",
    "DemoSampleMarksSnapshotAdapter",
    "MissingMarketDataError",
    "SampleMarkCandidate",
]
