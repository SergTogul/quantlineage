from app.domain.models import LimitResult, Portfolio, RiskLimit
from app.interfaces.pricing import PricingEngine


DEFAULT_LIMITS = [
    RiskLimit(metric="var_99", limit=250_000.0),
    RiskLimit(metric="dv01", limit=10_000.0),
    RiskLimit(metric="vega", limit=30_000.0),
    RiskLimit(metric="single_position_pct", limit=35.0),
]


class LimitEngine:
    def evaluate(self, portfolio: Portfolio, pricing_engine: PricingEngine, risk: dict[str, float], limits: list[RiskLimit]) -> list[LimitResult]:
        values = [abs(pricing_engine.value(p).market_value) for p in portfolio.positions]
        gross = sum(values) or 1.0
        largest_pct = max(values, default=0.0) / gross * 100.0
        metrics = {
            "var_99": abs(risk["var_99"]),
            "dv01": abs(risk["dv01"]),
            "vega": abs(risk["vega"]),
            "single_position_pct": largest_pct,
        }
        return [
            LimitResult(
                metric=item.metric,
                value=metrics[item.metric],
                limit=item.limit,
                utilization_pct=(metrics[item.metric] / item.limit * 100.0 if item.limit else float("inf")),
                breached=metrics[item.metric] > item.limit,
            )
            for item in limits
        ]
