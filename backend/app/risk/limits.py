"""Configurable risk limits (M4.5).

Evaluates firm/desk-scoped metrics against hard limits with OK / WARNING / BREACH
status. Warning bands are per-limit via ``RiskLimit.warning_threshold_pct``
(utilization %). Hierarchy nodes pass the node sub-portfolio so the same
``var_99`` / ES definitions act as firm or desk limits depending on level.
"""

from __future__ import annotations

from app.domain.models import LimitResult, LimitStatus, Portfolio, RiskLimit
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


def _concentration_pct(portfolio: Portfolio, pricing_engine: PricingEngine) -> float:
    values = [abs(pricing_engine.value(p).market_value) for p in portfolio.positions]
    gross = sum(values) or 1.0
    return max(values, default=0.0) / gross * 100.0


def _key_rate_dv01_abs(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    risk: dict[str, float],
) -> float:
    if "key_rate_dv01" in risk:
        return abs(float(risk["key_rate_dv01"]))
    # Lazy: avoid importing sensitivities at module load for light callers.
    from app.risk.sensitivities import SensitivityEngine

    measures = SensitivityEngine().calculate(
        portfolio, pricing_engine, measures=("key_rate_dv01",)
    )
    if not measures:
        # Fall back to parallel DV01 when no key-rate pillars are available.
        return abs(float(risk.get("dv01", 0.0)))
    return max(abs(m.value) for m in measures)


def _stress_loss_abs(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    risk: dict[str, float],
) -> float:
    if "stress_loss" in risk:
        return abs(float(risk["stress_loss"]))
    from app.risk.stress import DEFAULT_SCENARIOS, StressEngine

    results = StressEngine().run(portfolio, pricing_engine, DEFAULT_SCENARIOS)
    if not results:
        return 0.0
    # Loss = -pnl for adverse scenarios; take the worst loss (>= 0).
    return max(0.0, max(-float(r.pnl) for r in results))


class LimitEngine:
    def resolve_metrics(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        risk: dict[str, float],
        needed: set[str] | None = None,
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
            out["var_99"] = abs(float(risk.get("var_99", 0.0)))
        if "var_95" in want:
            out["var_95"] = abs(float(risk.get("var_95", 0.0)))
        if "expected_shortfall_99" in want:
            out["expected_shortfall_99"] = abs(float(risk.get("expected_shortfall_99", 0.0)))
        if "dv01" in want:
            out["dv01"] = abs(float(risk.get("dv01", 0.0)))
        if "vega" in want:
            out["vega"] = abs(float(risk.get("vega", 0.0)))
        if "fx_delta" in want:
            out["fx_delta"] = abs(float(risk.get("fx_delta", 0.0)))
        if "single_position_pct" in want:
            out["single_position_pct"] = _concentration_pct(portfolio, pricing_engine)
        if "key_rate_dv01" in want:
            out["key_rate_dv01"] = _key_rate_dv01_abs(portfolio, pricing_engine, risk)
        if "stress_loss" in want:
            out["stress_loss"] = _stress_loss_abs(portfolio, pricing_engine, risk)
        return out

    def evaluate(
        self,
        portfolio: Portfolio,
        pricing_engine: PricingEngine,
        risk: dict[str, float],
        limits: list[RiskLimit],
    ) -> list[LimitResult]:
        needed = {item.metric for item in limits}
        metrics = self.resolve_metrics(portfolio, pricing_engine, risk, needed)
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
