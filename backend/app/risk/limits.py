"""Configurable risk limits (M4.5).

Evaluates firm/desk-scoped metrics against hard limits with OK / WARNING / BREACH
status. Warning bands are per-limit via ``RiskLimit.warning_threshold_pct``
(utilization %). Hierarchy nodes pass the node sub-portfolio so the same
``var_99`` / ES definitions act as firm or desk limits depending on level.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.models import (
    LimitResult,
    LimitStatus,
    MarketSnapshot,
    Portfolio,
    RiskLimit,
    RiskSummary,
)
from app.interfaces.pricing import PricingEngine

DEFAULT_WARNING_THRESHOLD_PCT = 80.0

# Firm / desk VaR & ES plus concentration, Greeks, FX, and stress loss.
# Hierarchy applies these to each node subset (firm root vs desk vs book).
DEFAULT_LIMITS: list[RiskLimit] = [
    RiskLimit(
        metric="var_99",
        limit=250_000.0,
        warning_threshold_pct=80.0,
        scope="firm",
        label="Firm/desk VaR 99%",
    ),
    RiskLimit(
        metric="expected_shortfall_99",
        limit=350_000.0,
        warning_threshold_pct=80.0,
        scope="firm",
        label="Firm/desk ES 99%",
    ),
    RiskLimit(
        metric="dv01",
        limit=10_000.0,
        warning_threshold_pct=80.0,
        label="DV01",
    ),
    RiskLimit(
        metric="key_rate_dv01",
        limit=8_000.0,
        warning_threshold_pct=80.0,
        label="Key-rate DV01",
    ),
    RiskLimit(
        metric="vega",
        limit=30_000.0,
        warning_threshold_pct=80.0,
        label="Vega",
    ),
    RiskLimit(
        metric="fx_delta",
        limit=50_000.0,
        warning_threshold_pct=80.0,
        label="FX exposure",
    ),
    RiskLimit(
        metric="single_position_pct",
        limit=35.0,
        warning_threshold_pct=80.0,
        label="Concentration",
    ),
    RiskLimit(
        metric="stress_loss",
        limit=400_000.0,
        warning_threshold_pct=80.0,
        label="Stress loss",
    ),
]


def classify_limit_status(
    value: float,
    limit: float,
    warning_threshold_pct: float = DEFAULT_WARNING_THRESHOLD_PCT,
) -> LimitStatus:
    """Map absolute metric value to OK / WARNING / BREACH.

    BREACH when ``value > limit`` (strict). WARNING when utilization
    ``value/limit*100 >= warning_threshold_pct`` but not breached.
    """
    if limit <= 0:
        return "BREACH" if value > 0 else "OK"
    if value > limit:
        return "BREACH"
    utilization = value / limit * 100.0
    if utilization >= warning_threshold_pct:
        return "WARNING"
    return "OK"


def _concentration_pct(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    market: MarketSnapshot | None = None,
) -> float:
    values = [
        abs(pricing_engine.value(p, market).market_value) for p in portfolio.positions
    ]
    gross = sum(values) or 1.0
    return max(values, default=0.0) / gross * 100.0


def _risk_abs(
    risk: RiskSummary,
    name: str,
    extra: Mapping[str, float] | None = None,
    default: float = 0.0,
) -> float:
    if extra is not None and name in extra:
        return abs(float(extra[name]))
    return abs(float(getattr(risk, name, default)))


def _key_rate_dv01_abs(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    risk: RiskSummary,
    market: MarketSnapshot | None = None,
    extra: Mapping[str, float] | None = None,
) -> float:
    if extra is not None and "key_rate_dv01" in extra:
        return abs(float(extra["key_rate_dv01"]))
    # Lazy: avoid importing sensitivities at module load for light callers.
    from app.risk.sensitivities import SensitivityEngine

    measures = SensitivityEngine().calculate(
        portfolio, pricing_engine, measures=("key_rate_dv01",), market=market
    )
    if not measures:
        # Fall back to parallel DV01 when no key-rate pillars are available.
        return abs(float(risk.dv01))
    return max(abs(m.value) for m in measures)


def _stress_loss_abs(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    market: MarketSnapshot | None = None,
    extra: Mapping[str, float] | None = None,
) -> float:
    if extra is not None and "stress_loss" in extra:
        return abs(float(extra["stress_loss"]))
    from app.risk.stress import DEFAULT_SCENARIOS, StressEngine

    results = StressEngine().run(
        portfolio, pricing_engine, DEFAULT_SCENARIOS, market=market
    )
    if not results:
        return 0.0
    # Loss = -pnl for adverse scenarios; take the worst loss (>= 0).
    return max(0.0, max(-float(r.pnl) for r in results))


class LimitEngine:
    def resolve_metrics(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        risk: RiskSummary,
        needed: set[str] | None = None,
        market: MarketSnapshot | None = None,
        extra: Mapping[str, float] | None = None,
    ) -> dict[str, float]:
        """Absolute metric values used for utilization / breach checks."""
        want = needed or {
            "var_99",
            "var_95",
            "expected_shortfall_99",
            "dv01",
            "key_rate_dv01",
            "vega",
            "fx_delta",
            "single_position_pct",
            "stress_loss",
        }
        out: dict[str, float] = {}
        if "var_99" in want:
            out["var_99"] = _risk_abs(risk, "var_99", extra)
        if "var_95" in want:
            out["var_95"] = _risk_abs(risk, "var_95", extra)
        if "expected_shortfall_99" in want:
            out["expected_shortfall_99"] = _risk_abs(risk, "expected_shortfall_99", extra)
        if "dv01" in want:
            out["dv01"] = _risk_abs(risk, "dv01", extra)
        if "vega" in want:
            out["vega"] = _risk_abs(risk, "vega", extra)
        if "fx_delta" in want:
            out["fx_delta"] = _risk_abs(risk, "fx_delta", extra)
        if "single_position_pct" in want:
            out["single_position_pct"] = _concentration_pct(
                portfolio, pricing_engine, market
            )
        if "key_rate_dv01" in want:
            out["key_rate_dv01"] = _key_rate_dv01_abs(
                portfolio, pricing_engine, risk, market, extra
            )
        if "stress_loss" in want:
            out["stress_loss"] = _stress_loss_abs(
                portfolio, pricing_engine, market, extra
            )
        return out

    def evaluate(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        risk: RiskSummary,
        limits: list[RiskLimit],
        market: MarketSnapshot | None = None,
        extra: Mapping[str, float] | None = None,
    ) -> list[LimitResult]:
        needed = {item.metric for item in limits}
        metrics = self.resolve_metrics(
            portfolio, pricing_engine, risk, needed, market=market, extra=extra
        )
        results: list[LimitResult] = []
        for item in limits:
            value = metrics[item.metric]
            warn_pct = item.warning_threshold_pct
            status = classify_limit_status(value, item.limit, warn_pct)
            utilization = (
                value / item.limit * 100.0 if item.limit else float("inf")
            )
            results.append(
                LimitResult(
                    metric=item.metric,
                    value=value,
                    limit=item.limit,
                    utilization_pct=utilization,
                    breached=status == "BREACH",
                    status=status,
                    warning_threshold_pct=warn_pct,
                    scope=item.scope,
                    label=item.label,
                )
            )
        return results
