"""LRU cache for RiskForge ``YieldCurve`` construction (M5.5).

Keys bind currency-relevant market marks (rates / key_rates / curves /
projection for that currency) plus ``prefer_projection``. Equity/FX/vol bumps
that leave rate marks unchanged are cache hits. A rate bump changes the
fingerprint and misses — no separate invalidation registry.

QuantLib types stay out of this module; adapters still build term structures
from cached ``YieldCurve`` instances.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.domain.models import MarketSnapshot, _deep_unfreeze
from app.market.curves import YieldCurve
from app.pricing.cache import CacheStats


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _stable_json_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def curve_market_fingerprint(market: MarketSnapshot, currency: str) -> str:
    """Hash of rate-curve inputs for ``currency`` (excludes equity/FX/vol marks)."""
    ccy = currency.upper()
    curves: dict[str, Any] = {}
    for name, payload in market.curves.items():
        if not isinstance(payload, Mapping):
            continue
        if str(payload.get("currency", "")).upper() != ccy:
            continue
        curves[str(name)] = _deep_unfreeze(payload)
    nested_kr = market.key_rates.get(currency) or market.key_rates.get(ccy)
    payload = {
        "currency": ccy,
        "rates": market.rates.get(currency, market.rates.get(ccy)),
        "projection_rates": market.projection_rates.get(
            currency, market.projection_rates.get(ccy)
        ),
        "key_rates": _deep_unfreeze(nested_kr) if nested_kr is not None else None,
        "curves": curves,
    }
    return _stable_json_hash(payload)


def curve_cache_key(market: MarketSnapshot, currency: str, *, prefer_projection: bool) -> str:
    return (
        f"curve:v1|{curve_market_fingerprint(market, currency)}"
        f"|{currency.upper()}|{int(prefer_projection)}"
    )


@dataclass
class CurveConstructionCache:
    """Thread-safe LRU of constructed ``YieldCurve`` objects."""

    maxsize: int = 256

    def __post_init__(self) -> None:
        if self.maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._cache: OrderedDict[str, YieldCurve] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(hits=self._hits, misses=self._misses, size=len(self._cache))

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def get(self, key: str) -> YieldCurve | None:
        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                self._misses += 1
                return None
            self._cache.move_to_end(key)
            self._hits += 1
            return cached

    def put(self, key: str, curve: YieldCurve) -> YieldCurve:
        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                self._cache.move_to_end(key)
                return existing
            self._cache[key] = curve
            self._cache.move_to_end(key)
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)
            return curve


_CACHE: CurveConstructionCache | None = None
_CACHE_LOCK = threading.RLock()


def curve_cache_enabled() -> bool:
    return _env_flag("RISKFORGE_CURVE_CACHE", default=True)


def _cache_maxsize() -> int:
    raw = os.getenv("RISKFORGE_CURVE_CACHE_SIZE", "256").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 256


def get_curve_construction_cache() -> CurveConstructionCache:
    """Process-wide curve construction LRU (created lazily from env)."""
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is None:
            _CACHE = CurveConstructionCache(maxsize=_cache_maxsize())
        return _CACHE


def reset_curve_construction_cache() -> None:
    """Drop the process-wide cache (tests / worker reset)."""
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is not None:
            _CACHE.clear()
        _CACHE = None


__all__ = [
    "CurveConstructionCache",
    "curve_cache_enabled",
    "curve_cache_key",
    "curve_market_fingerprint",
    "get_curve_construction_cache",
    "reset_curve_construction_cache",
]
