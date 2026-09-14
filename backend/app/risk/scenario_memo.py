"""LRU memo for multi-factor scenario application (M5.5).

Keys bind ``base.id``, ``MarketSnapshot.content_hash`` (marks), expanded shock
fingerprint, and the scenario id tag. A market bump that changes marks misses;
repeated ``shocked_value`` / stress paths with the same base + scenario hit.

``base.id`` is part of the key because shocked snapshot ids embed the base id
(``{base.id}:{scenario_id}`` / bump chains).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.models import MarketSnapshot
from app.pricing.cache import CacheStats
from app.risk.scenario_model import FactorShock


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _stable_json_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def shock_fingerprint(shocks: Sequence[FactorShock]) -> str:
    """Ordered shock identity (factor key + amount)."""
    payload = [{"factor": s.factor.key, "amount": float(s.amount)} for s in shocks]
    return _stable_json_hash(payload)


def scenario_memo_key(
    base: MarketSnapshot,
    shocks: Sequence[FactorShock],
    *,
    id_tag: str | None,
) -> str:
    tag = id_tag if id_tag is not None else ""
    return (
        f"scenario:v1|{base.id}|{base.content_hash()}"
        f"|{shock_fingerprint(shocks)}|{tag}"
    )


@dataclass
class ScenarioResultMemo:
    """Thread-safe LRU of shocked ``MarketSnapshot`` results."""

    maxsize: int = 1024

    def __post_init__(self) -> None:
        if self.maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._cache: OrderedDict[str, MarketSnapshot] = OrderedDict()
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

    def get(self, key: str) -> MarketSnapshot | None:
        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                self._misses += 1
                return None
            self._cache.move_to_end(key)
            self._hits += 1
            # Copy so callers cannot share identity with the memo entry (or base).
            return cached.model_copy()

    def put(self, key: str, snapshot: MarketSnapshot) -> MarketSnapshot:
        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                self._cache.move_to_end(key)
                return existing.model_copy()
            stored = snapshot.model_copy()
            self._cache[key] = stored
            self._cache.move_to_end(key)
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)
            return stored.model_copy()


_MEMO: ScenarioResultMemo | None = None
_MEMO_LOCK = threading.RLock()


def scenario_memo_enabled() -> bool:
    return _env_flag("QUANTLINEAGE_SCENARIO_CACHE", default=True)


def _memo_maxsize() -> int:
    raw = os.getenv("QUANTLINEAGE_SCENARIO_CACHE_SIZE", "1024").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1024


def get_scenario_result_memo() -> ScenarioResultMemo:
    """Process-wide scenario-result LRU (created lazily from env)."""
    global _MEMO
    with _MEMO_LOCK:
        if _MEMO is None:
            _MEMO = ScenarioResultMemo(maxsize=_memo_maxsize())
        return _MEMO


def reset_scenario_result_memo() -> None:
    """Drop the process-wide memo (tests / worker reset)."""
    global _MEMO
    with _MEMO_LOCK:
        if _MEMO is not None:
            _MEMO.clear()
        _MEMO = None


__all__ = [
    "ScenarioResultMemo",
    "get_scenario_result_memo",
    "reset_scenario_result_memo",
    "scenario_memo_enabled",
    "scenario_memo_key",
    "shock_fingerprint",
]
