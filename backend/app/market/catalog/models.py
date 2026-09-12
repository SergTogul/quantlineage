"""Canonical instrument catalog records. Projects to ingestion search candidates."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from app.market.ingestion.errors import ProviderError
from app.market.ingestion.models import InstrumentCandidate


class ProviderMapping(BaseModel):
    """Provider symbol is an attribute of the internal record, not a second identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    source_symbol: str


class CatalogRecord(BaseModel):
    """Supported (or catalogued) instrument with capabilities and risk-factor mapping."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str
    display_name: str
    asset_type: str
    currency: str
    geography: str
    exchange: str | None = None
    provider_mappings: tuple[ProviderMapping, ...]
    supported_for_history: bool
    supported_for_snapshot: bool
    supported_for_risk_factor: bool
    risk_factor_mapping: str | None = None
    search_aliases: tuple[str, ...] = ()

    def to_candidate(self) -> InstrumentCandidate:
        mapping = self.provider_mappings[0]
        return InstrumentCandidate(
            instrument_id=self.instrument_id,
            display_name=self.display_name,
            provider=mapping.provider,
            source_symbol=mapping.source_symbol,
            asset_type=self.asset_type,
            currency=self.currency,
            supported_for_history=self.supported_for_history,
            supported_for_snapshot=self.supported_for_snapshot,
            supported_for_risk_factor=self.supported_for_risk_factor,
        )


class CatalogSearchHit(BaseModel):
    """API/search row. Unsupported provider hits keep capabilities false."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str
    display_name: str
    provider: str
    source_symbol: str
    asset_type: str
    currency: str
    supported_for_history: bool
    supported_for_snapshot: bool
    supported_for_risk_factor: bool
    risk_factor_mapping: str | None = None
    coverage: str | None = None


@dataclass(frozen=True)
class CatalogSearchResult:
    """Merged curated + provider hits, plus a provider failure if one occurred."""

    hits: list[CatalogSearchHit] = field(default_factory=list)
    provider_error: ProviderError | None = None
