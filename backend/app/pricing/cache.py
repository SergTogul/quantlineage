"""Valuation cache wrapping any ``PricingEngine`` without leaking QuantLib.

Cache keys bind:
- contractual trade economics (``terms_from_position``; unknown families fail closed),
- required market snapshot content hash,
- parseable snapshot ``as_of`` (``date`` or ISO ``YYYY-MM-DD``; engine labels omitted),
- pricing configuration (engine identity + evaluation date + extras).

A market bump produces a new ``content_hash`` and therefore a miss — no separate
invalidation registry is required for correctness. Callers may still ``clear()``
when replacing an engine or resetting a worker.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.instrument_terms import terms_from_position
from app.domain.models import (
    MarketSnapshot,
    Position,
    Valuation,
    calendar_as_of,
)
from app.interfaces.pricing import PricingEngine

# Family schema ids keep v1 cache identity. Equity-family InstrumentTerms add
# settlement ``currency`` that Positions never hashed; drop it at hash time.
_TRADE_CACHE_SCHEMAS: dict[str, str] = {
    "equity": "equity_terms_v1",
    "equity_future": "equity_future_terms_v1",
    "european_option": "equity_option_terms_v1",
    "bond": "bond_terms_v1",
    "swap": "swap_terms_v1",
    "fx_forward": "fx_forward_terms_v1",
    "fx_option": "fx_option_terms_v1",
    "ir_future": "ir_future_terms_v1",
    "cap_floor": "cap_floor_terms_v1",
    "swaption": "swaption_terms_v1",
}
_EQUITY_FAMILY_TYPES = frozenset({"equity", "equity_future", "european_option"})


def _stable_json_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class PricingConfiguration:
    """Pricing knobs that participate in the valuation cache key.

    Keep this free of QuantLib types — only portable scalars / strings.
    """

    engine_id: str
    evaluation_date: str | None = None
    extras: tuple[tuple[str, str], ...] = ()

    def fingerprint(self) -> str:
        return _stable_json_hash(
            {
                "engine_id": self.engine_id,
                "evaluation_date": self.evaluation_date,
                "extras": list(self.extras),
            }
        )

    @classmethod
    def from_engine(cls, engine: PricingEngine, *, extras: dict[str, str] | None = None) -> PricingConfiguration:
        if isinstance(engine, CachedPricingEngine):
            base = engine.config
            if not extras:
                return base
            merged = dict(base.extras)
            merged.update({str(k): str(v) for k, v in extras.items()})
            return cls(
                engine_id=base.engine_id,
                evaluation_date=base.evaluation_date,
                extras=tuple(sorted(merged.items())),
            )
        engine_id = type(engine).__name__
        evaluation_date: str | None = None
        raw_date = getattr(engine, "evaluation_date", None)
        if isinstance(raw_date, date):
            evaluation_date = raw_date.isoformat()
        elif raw_date is not None:
            evaluation_date = str(raw_date)
        extra_items = tuple(sorted((str(k), str(v)) for k, v in (extras or {}).items()))
        return cls(engine_id=engine_id, evaluation_date=evaluation_date, extras=extra_items)


def trade_cache_key(position: Position) -> str:
    """Versioned economics hash from ``terms_from_position``; marks excluded."""
    terms = terms_from_position(position)
    schema = _TRADE_CACHE_SCHEMAS.get(terms.type)
    if schema is None:
        raise TypeError(
            f"trade_cache_key has no terms projection for {type(position).__name__}"
        )
    economics = terms.model_dump(mode="json")
    if terms.type in _EQUITY_FAMILY_TYPES:
        economics.pop("currency", None)
    return _stable_json_hash({"schema": schema, "economics": economics})


def _parseable_as_of(as_of: object) -> date | None:
    """Return a calendar date from snapshot ``as_of``, or None for engine labels.

    Matches the domain / QuantLib contract: ``date`` and ISO ``YYYY-MM-DD``
    are load-bearing; ``current`` / ``t0`` fall back to engine
    ``evaluation_date`` (already in ``PricingConfiguration``).
    """
    return calendar_as_of(as_of)


def market_cache_key(market: MarketSnapshot | None) -> str:
    """Snapshot content hash plus parseable ``as_of``; ``id`` and labels omitted."""
    if market is None:
        raise ValueError("production cache keys require an explicit MarketSnapshot")
    parsed = _parseable_as_of(market.as_of)
    if parsed is None:
        return f"market:{market.content_hash()}"
    return f"market:{market.content_hash()}|as_of:{parsed.isoformat()}"


def valuation_cache_key(
    position: Position,
    market: MarketSnapshot | None,
    config: PricingConfiguration,
) -> str:
    return f"v2|{trade_cache_key(position)}|{market_cache_key(market)}|{config.fingerprint()}"


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    size: int = 0

    @property
    def requests(self) -> int:
        return self.hits + self.misses


class CachedPricingEngine(PricingEngine):
    """LRU valuation cache in front of an inner ``PricingEngine``.

    Does not import or expose QuantLib. Scenario-invariant paths (same trade +
    same base snapshot + same config) hit; shocked/bumped markets miss.
    """

    def __init__(
        self,
        inner: PricingEngine,
        *,
        maxsize: int = 4096,
        config: PricingConfiguration | None = None,
    ) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        if isinstance(inner, CachedPricingEngine):
            raise TypeError("CachedPricingEngine must not wrap another CachedPricingEngine")
        self._inner = inner
        self._config = config or PricingConfiguration.from_engine(inner)
        self._maxsize = maxsize
        self._cache: OrderedDict[str, Valuation] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    @property
    def inner(self) -> PricingEngine:
        return self._inner

    @property
    def config(self) -> PricingConfiguration:
        return self._config

    @property
    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(hits=self._hits, misses=self._misses, size=len(self._cache))

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def value(self, position: Position, market: MarketSnapshot | None = None) -> Valuation:
        if market is None:
            raise ValueError("CachedPricingEngine requires an explicit MarketSnapshot")
        key = valuation_cache_key(position, market, self._config)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._hits += 1
                return cached.model_copy()
            self._misses += 1

        # Compute outside the lock so inner engines (e.g. QuantLib RLock) are not nested.
        valuation = self._inner.value(position, market)

        with self._lock:
            # Another thread may have filled the key; prefer first writer, still LRU-touch.
            existing = self._cache.get(key)
            if existing is not None:
                self._cache.move_to_end(key)
                return existing.model_copy()
            self._cache[key] = valuation
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)
            return valuation.model_copy()
