"""VaR methodology comparison (M2.4).

Runs LINEAR, DELTA_GAMMA, and FULL_REVALUATION on the same portfolio / dataset
and returns VaR95, VaR99, ES99, and wall-clock runtime per methodology.

Delegates all P&L / quantile math to :class:`HistoricalRiskEngine` (M2.3) so
this module does not duplicate approximation or full-revaluation logic.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    VaRMethodology,
    VaRMethodologyComparison,
    VaRMethodologyMetrics,
)
from app.interfaces.pricing import PricingEngine
from app.risk.historical import HistoricalRiskEngine

DEFAULT_COMPARE_METHODOLOGIES: tuple[VaRMethodology, ...] = (
    VaRMethodology.LINEAR,
    VaRMethodology.DELTA_GAMMA,
    VaRMethodology.FULL_REVALUATION,
)


def compare_methodologies(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    *,
    risk_engine: HistoricalRiskEngine | None = None,
    methodologies: Sequence[VaRMethodology] | None = None,
    market: MarketSnapshot | None = None,
) -> VaRMethodologyComparison:
    """Compare historical VaR methodologies on a shared market path.

    Units / sign: same as ``HistoricalRiskEngine.calculate`` (loss VaR ≥ 0,
    ES ≥ VaR99). ``runtime_ms`` is wall-clock per methodology (includes pricing
    for FULL_REVALUATION); it is not a risk metric and is not asserted for
    determinism.
    """
    engine = risk_engine or HistoricalRiskEngine()
    meths = tuple(methodologies) if methodologies is not None else DEFAULT_COMPARE_METHODOLOGIES
    if not meths:
        raise ValueError("methodologies must be non-empty")

    results: list[VaRMethodologyMetrics] = []
    for meth in meths:
        t0 = time.perf_counter()
        result = engine.calculate(
            portfolio,
            pricing_engine,
            methodology=meth,
            market=market,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        results.append(
            VaRMethodologyMetrics(
                methodology=meth,
                var_95=float(result.var_95),
                var_99=float(result.var_99),
                expected_shortfall_99=float(result.expected_shortfall_99),
                runtime_ms=float(elapsed_ms),
            )
        )

    return VaRMethodologyComparison(
        portfolio_id=portfolio.id,
        observations=int(engine.observations),
        results=results,
    )
