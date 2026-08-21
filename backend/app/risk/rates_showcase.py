"""USD rates-macro showcase: curve nodes + true key-rate DV01.

Quant contract (Stage 10.5)
----------------------------
- Shock unit: RateZero 1bp = 1e-4 decimal on zeros / key_rates.
- Sensitivity: DV01 and KR-DV01 = currency P&L for +1bp (SensitivityEngine).
- Sign: existing SensitivityEngine.
- Currency / notional: position currency on the rates-macro demo book.
- Base market: demo rates snapshot with attached USD OIS/SOFR-style curves.
- Reconciliation: KR_2Y ≠ KR_10Y; sum of 2Y/5Y/10Y KR ≠ parallel when extra
  pillars / scalar rates / triangular isolation apply.

This payload is a scoped demo. It is not a production multi-curve framework.
"""

from __future__ import annotations

from typing import Any

from app.domain.models import MarketSnapshot, Portfolio
from app.interfaces.pricing import PricingEngine
from app.market.curves import tenor_to_years
from app.risk.factor_types import RateZero
from app.risk.sensitivities import SensitivityEngine

SHOWCASE_TENORS: tuple[str, ...] = ("2Y", "5Y", "10Y")

RATES_SHOWCASE_CONVENTIONS: dict[str, str] = {
    "shock_unit": "1bp = 1e-4 decimal",
    "sensitivity_unit": "currency P&L per +1bp",
    "sign": "SensitivityEngine P&L for +1bp; long rates typically negative",
    "day_count": "Actual/365 linear-in-zero interpolation",
    "limitations": (
        "Demo SOFR/OIS-style zeros on the rates-macro book; "
        "not a production multi-curve framework."
    ),
}


def _curve_view(payload: dict[str, Any] | None, *, name: str) -> dict[str, Any] | None:
    if not payload:
        return None
    zeros = payload.get("zeros") or {}
    nodes = []
    for tenor in SHOWCASE_TENORS:
        if tenor not in zeros:
            continue
        nodes.append(
            {
                "tenor": tenor,
                "years": tenor_to_years(tenor),
                "zero_rate": float(zeros[tenor]),
            }
        )
    return {
        "name": str(payload.get("name") or name),
        "currency": str(payload.get("currency") or ""),
        "curve_type": str(payload.get("curve_type") or ""),
        "nodes": nodes,
        "limitations": str(
            payload.get("limitations") or RATES_SHOWCASE_CONVENTIONS["limitations"]
        ),
    }


def build_rates_showcase(
    portfolio: Portfolio,
    market: MarketSnapshot,
    pricing: PricingEngine,
) -> dict[str, Any]:
    """Assemble the rates showcase from SensitivityEngine + snapshot curves."""
    engine = SensitivityEngine(rate_bump_bps=1.0)
    parallel = 0.0
    key_rate_dv01: list[dict[str, Any]] = []
    for measure in engine.calculate(
        portfolio, pricing, measures=("dv01", "key_rate_dv01"), market=market
    ):
        if measure.name == "dv01":
            parallel = float(measure.value)
            continue
        if measure.name != "key_rate_dv01":
            continue
        factor = measure.factor
        if not isinstance(factor, RateZero) or factor.currency != "USD":
            continue
        if factor.tenor not in SHOWCASE_TENORS:
            continue
        key_rate_dv01.append(
            {
                "tenor": factor.tenor,
                "factor": f"RateZero:{factor.currency}:{factor.tenor}",
                "value": float(measure.value),
                "unit": measure.unit,
                "method": measure.method,
            }
        )
    tenor_order = {tenor: i for i, tenor in enumerate(SHOWCASE_TENORS)}
    key_rate_dv01.sort(key=lambda row: tenor_order.get(row["tenor"], 99))

    curves = market.curves
    discount = _curve_view(curves.get("USD_OIS"), name="USD_OIS")
    projection = _curve_view(curves.get("USD_SOFR"), name="USD_SOFR")
    if discount is None:
        raise ValueError("rates showcase requires USD_OIS discount curve on the snapshot")

    return {
        "portfolio_id": portfolio.id,
        "market_snapshot_id": market.id,
        "conventions": dict(RATES_SHOWCASE_CONVENTIONS),
        "discount_curve": discount,
        "projection_curve": projection,
        "parallel_dv01": parallel,
        "key_rate_dv01": key_rate_dv01,
    }
