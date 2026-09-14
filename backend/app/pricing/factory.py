from __future__ import annotations

import os

from app.interfaces.pricing import PricingEngine
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.cache import CachedPricingEngine, PricingConfiguration
from app.pricing.quantlib import QuantLibPricingEngine


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def create_pricing_engine() -> PricingEngine:
    """Create the configured pricing adapter.

    QuantLib is the application default.  The built-in implementation exists as a
    deterministic development/test fallback and as a cross-check implementation.

    When ``QUANTLINEAGE_PRICING_CACHE`` is enabled (default), the adapter is wrapped
    in :class:`~app.pricing.cache.CachedPricingEngine` so repeated valuations of
    the same trade + market + pricing configuration hit an LRU cache. Unique-shock
    / FULL_REVALUATION loops enter :func:`~app.pricing.cache.bypass_valuation_lru`
    so that LRU is not consulted on snapshots that cannot hit.
    """
    name = os.getenv("QUANTLINEAGE_PRICING_ENGINE", "quantlib").strip().lower()
    if name == "quantlib":
        engine: PricingEngine = QuantLibPricingEngine()
    elif name == "builtin":
        engine = BuiltinPricingEngine()
    else:
        raise ValueError(f"Unknown pricing engine: {name!r}")

    if _env_flag("QUANTLINEAGE_PRICING_CACHE", default=True):
        maxsize_raw = os.getenv("QUANTLINEAGE_PRICING_CACHE_SIZE", "4096").strip()
        try:
            maxsize = max(1, int(maxsize_raw))
        except ValueError:
            maxsize = 4096
        engine = CachedPricingEngine(
            engine,
            maxsize=maxsize,
            config=PricingConfiguration.from_engine(engine),
        )
    return engine
