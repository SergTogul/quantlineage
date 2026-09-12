"""Merge curated catalog records with injected InstrumentSearchProvider hits."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.market.catalog.models import CatalogRecord, CatalogSearchHit, CatalogSearchResult
from app.market.catalog.universe import WAVE_A_UNIVERSE
from app.market.ingestion.errors import ProviderError
from app.market.ingestion.models import InstrumentCandidate
from app.market.ingestion.protocols import InstrumentSearchProvider

_EQUITY_ETF_TYPES = frozenset({"equity", "etf"})


def search_catalog(
    query: str,
    *,
    provider: InstrumentSearchProvider | None = None,
    universe: tuple[CatalogRecord, ...] = WAVE_A_UNIVERSE,
) -> CatalogSearchResult:
    """Return curated matches merged with provider hits. Curated identity wins."""
    needle = query.strip()
    if not needle:
        return CatalogSearchResult(hits=[])

    curated_matches = [record for record in universe if _matches(record, needle)]
    hits: dict[str, CatalogSearchHit] = {}
    for record in curated_matches:
        hits[record.instrument_id] = _hit_from_record(record)

    provider_error: ProviderError | None = None
    if provider is not None and _should_call_provider(curated_matches):
        try:
            raw_hits = provider.search(needle)
        except ProviderError as exc:
            provider_error = exc
            raw_hits = []
        source_index = _source_index(universe)
        for raw in raw_hits:
            candidate = _as_candidate(raw)
            if candidate is None:
                continue
            mapped = source_index.get(_source_key(candidate.provider, candidate.source_symbol))
            if mapped is not None:
                hits.setdefault(mapped.instrument_id, _hit_from_record(mapped))
                continue
            if candidate.instrument_id in hits:
                continue
            hits[candidate.instrument_id] = _hit_from_unsupported(candidate)

    return CatalogSearchResult(hits=list(hits.values()), provider_error=provider_error)


def _should_call_provider(curated_matches: list[CatalogRecord]) -> bool:
    if not curated_matches:
        return True
    return any(record.asset_type in _EQUITY_ETF_TYPES for record in curated_matches)


def _matches(record: CatalogRecord, query: str) -> bool:
    haystack = _haystack(record)
    lowered = query.lower()
    if lowered in haystack:
        return True
    tokens = [token for token in lowered.split() if token]
    return bool(tokens) and all(token in haystack for token in tokens)


def _haystack(record: CatalogRecord) -> str:
    parts = [
        record.instrument_id,
        record.display_name,
        record.asset_type,
        record.currency,
        record.geography,
        record.exchange or "",
        record.risk_factor_mapping or "",
        *record.search_aliases,
    ]
    for mapping in record.provider_mappings:
        parts.append(mapping.provider)
        parts.append(mapping.source_symbol)
    return " ".join(parts).lower()


def _source_index(universe: tuple[CatalogRecord, ...]) -> dict[tuple[str, str], CatalogRecord]:
    index: dict[tuple[str, str], CatalogRecord] = {}
    for record in universe:
        for mapping in record.provider_mappings:
            index[_source_key(mapping.provider, mapping.source_symbol)] = record
    return index


def _source_key(provider: str, source_symbol: str) -> tuple[str, str]:
    return (provider.strip().lower(), source_symbol.strip().upper())


def _as_candidate(raw: Any) -> InstrumentCandidate | None:
    if isinstance(raw, InstrumentCandidate):
        return raw
    if isinstance(raw, dict):
        try:
            return InstrumentCandidate.model_validate(raw)
        except ValidationError:
            return None
    return None


def _hit_from_record(record: CatalogRecord) -> CatalogSearchHit:
    mapping = record.provider_mappings[0]
    return CatalogSearchHit(
        instrument_id=record.instrument_id,
        display_name=record.display_name,
        provider=mapping.provider,
        source_symbol=mapping.source_symbol,
        asset_type=record.asset_type,
        currency=record.currency,
        supported_for_history=record.supported_for_history,
        supported_for_snapshot=record.supported_for_snapshot,
        supported_for_risk_factor=record.supported_for_risk_factor,
        risk_factor_mapping=record.risk_factor_mapping,
        coverage=None,
    )


def _hit_from_unsupported(candidate: InstrumentCandidate) -> CatalogSearchHit:
    return CatalogSearchHit(
        instrument_id=candidate.instrument_id,
        display_name=candidate.display_name,
        provider=candidate.provider,
        source_symbol=candidate.source_symbol,
        asset_type=candidate.asset_type,
        currency=candidate.currency,
        supported_for_history=False,
        supported_for_snapshot=False,
        supported_for_risk_factor=False,
        risk_factor_mapping=None,
        coverage=None,
    )
