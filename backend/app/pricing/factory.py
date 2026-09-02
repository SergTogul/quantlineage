from __future__ import annotations

import os

from app.interfaces.pricing import PricingEngine
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine


def create_pricing_engine() -> PricingEngine:
    """Create the configured pricing adapter.

    QuantLib is the application default.  The built-in implementation exists as a
    deterministic development/test fallback and as a cross-check implementation.
    """
    name = os.getenv("RISKFORGE_PRICING_ENGINE", "quantlib").strip().lower()
    if name == "quantlib":
        return QuantLibPricingEngine()
    if name == "builtin":
        return BuiltinPricingEngine()
    raise ValueError(f"Unknown pricing engine: {name!r}")
