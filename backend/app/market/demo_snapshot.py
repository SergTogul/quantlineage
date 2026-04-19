"""Legacy sample-mark adapter (removed). Marks no longer live on Position DTOs."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import MarketSnapshot, Portfolio


@dataclass(frozen=True)
class SampleMarkCandidate:
    position_id: str
    value: float
    legacy_field: str


class ConflictingSampleMarkError(ValueError):
    """Raised when legacy trades propose unequal marks for one market key.

    Retained for tests/docs that historically asserted conflict detection; the
    sample-mark adapter no longer extracts marks from Position DTOs.
    """

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


class SampleMarksRemovedError(ValueError):
    """Position DTOs no longer carry live marks for snapshot construction."""


class DemoSampleMarksSnapshotAdapter:
    """Former bridge from Position sample marks → MarketSnapshot.

    RF-001 Phase B removed mark fields from ``*Position`` DTOs. Callers must
    supply an explicit ``MarketSnapshot`` (or use ``demo_market_snapshot`` for
    canned demo portfolio identities).
    """

    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        raise SampleMarksRemovedError(
            "sample marks no longer live on Position DTOs; "
            "supply an explicit MarketSnapshot (or use demo_market_snapshot "
            f"for a canned demo id, got portfolio.id={portfolio.id!r})"
        )


__all__ = [
    "ConflictingSampleMarkError",
    "DemoSampleMarksSnapshotAdapter",
    "MissingMarketDataError",
    "SampleMarkCandidate",
    "SampleMarksRemovedError",
]
