"""Valuation cache wrapping any ``PricingEngine`` without leaking QuantLib.

Cache keys bind:
- trade (full position payload),
- market snapshot content hash (or a sentinel when ``market is None``),
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

from app.domain.models import MarketSnapshot, Position, Valuation
from app.interfaces.pricing import PricingEngine

_NONE_MARKET = "market:none"


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
    """Hash of the full trade payload (identity + economics)."""
    return _stable_json_hash(position.model_dump(mode="json"))


def market_cache_key(market: MarketSnapshot | None) -> str:
    """Snapshot content hash, independent of ``id`` / ``as_of`` labels."""
    if market is None:
        return _NONE_MARKET
    return f"market:{market.content_hash()}"


def valuation_cache_key(
    position: Position,
    market: MarketSnapshot | None,
    config: PricingConfiguration,
) -> str:
    return f"v1|{trade_cache_key(position)}|{market_cache_key(market)}|{config.fingerprint()}"


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
