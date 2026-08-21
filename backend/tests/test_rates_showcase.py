"""Stage 10.5: USD rates-macro curve showcase and true key-rate DV01.

Quant contract
--------------
- Shock unit: RateZero 1bp = 1e-4 decimal on zeros / key_rates (existing bump).
- Sensitivity: DV01 and KR-DV01 = currency P&L for +1bp (SensitivityEngine).
- Sign: existing SensitivityEngine (long rates risk is typically negative DV01).
- Currency / notional: position currency; demo book notionals unchanged.
- Base market: demo ``rates-macro`` snapshot with attached USD OIS/SOFR-style curves.
- Reconciliation: KR_2Y ≠ KR_10Y; 2Y vs 10Y isolation; sum of 2Y/5Y/10Y KR ≠ parallel
  when extra pillars / scalar rates / triangular interpolation apply.

This is a scoped demo curve, not a production multi-curve framework.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Portfolio
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import RateZero
from app.risk.sensitivities import SensitivityEngine
from app.sample import RATES_MACRO_PORTFOLIO, demo_market_snapshot

SHOWCASE_TENORS = ("2Y", "5Y", "10Y")
pricing = BuiltinPricingEngine()


def _kr_by_tenor(portfolio: Portfolio, market) -> dict[str, float]:
    engine = SensitivityEngine(rate_bump_bps=1.0)
    out: dict[str, float] = {}
    for measure in engine.calculate(
        portfolio, pricing, measures=("key_rate_dv01",), market=market
    ):
        if measure.name != "key_rate_dv01":
            continue
        factor = measure.factor
        if isinstance(factor, RateZero) and factor.currency == "USD":
            out[factor.tenor] = float(measure.value)
    return out


def _parallel_dv01(portfolio: Portfolio, market) -> float:
    engine = SensitivityEngine(rate_bump_bps=1.0)
    measures = engine.calculate(portfolio, pricing, measures=("dv01",), market=market)
    parallel = [m for m in measures if m.name == "dv01"]
    assert len(parallel) == 1
    return float(parallel[0].value)


def test_rates_macro_attaches_non_flat_usd_ois_sofr_nodes():
    market = demo_market_snapshot(RATES_MACRO_PORTFOLIO)
    assert market.id == "demo:rates-macro"
    assert "USD_OIS" in market.curves
    ois = market.curves["USD_OIS"]
    assert ois["currency"] == "USD"
    assert ois["curve_type"] == "discount"
    zeros = ois["zeros"]
    assert set(SHOWCASE_TENORS) <= set(zeros)
    assert zeros["2Y"] != pytest.approx(zeros["10Y"])
    assert "USD_SOFR" in market.curves
    sofr = market.curves["USD_SOFR"]
    assert sofr["curve_type"] == "projection"
    assert set(SHOWCASE_TENORS) <= set(sofr["zeros"])
    # Panel apply still needs USD 0Y on key_rates.
    assert "0Y" in market.key_rates["USD"]
    assert "2Y" in market.key_rates["USD"]
    assert "10Y" in market.key_rates["USD"]


def test_rates_macro_2y_swap_isolated_from_10y_pillar():
    """2Y swap PV is unchanged by a 10Y key-rate bump; 10Y swap is unchanged by 2Y."""
    market = demo_market_snapshot(RATES_MACRO_PORTFOLIO)
    swap_2y = next(p for p in RATES_MACRO_PORTFOLIO.positions if p.id == "swap-usd2y")
    swap_10y = next(p for p in RATES_MACRO_PORTFOLIO.positions if p.id == "swap-usd10y")
    base_2y = pricing.value(swap_2y, market).market_value
    base_10y = pricing.value(swap_10y, market).market_value

    bumped_10y = market.bump(RateZero("USD", "10Y"), 0.0001)
    assert pricing.value(swap_2y, bumped_10y).market_value == pytest.approx(base_2y, rel=1e-12)
    assert pricing.value(swap_10y, bumped_10y).market_value != pytest.approx(base_10y, rel=1e-12)

    bumped_2y = market.bump(RateZero("USD", "2Y"), 0.0001)
    assert pricing.value(swap_10y, bumped_2y).market_value == pytest.approx(base_10y, rel=1e-12)
    assert pricing.value(swap_2y, bumped_2y).market_value != pytest.approx(base_2y, rel=1e-12)


def test_rates_macro_kr_dv01_not_equal_to_parallel():
    """True tenor KR-DV01 is not parallel DV01 on the non-flat demo curve."""
    market = demo_market_snapshot(RATES_MACRO_PORTFOLIO)
    kr = _kr_by_tenor(RATES_MACRO_PORTFOLIO, market)
    parallel = _parallel_dv01(RATES_MACRO_PORTFOLIO, market)
    assert set(SHOWCASE_TENORS) <= set(kr)
    assert kr["2Y"] != pytest.approx(kr["10Y"], rel=1e-9, abs=1e-6)
    assert kr["2Y"] != pytest.approx(parallel, rel=1e-9, abs=1e-6)
    assert kr["10Y"] != pytest.approx(parallel, rel=1e-9, abs=1e-6)
    kr_sum = sum(kr[t] for t in SHOWCASE_TENORS)
    assert kr_sum != pytest.approx(parallel, rel=1e-9, abs=1e-6)


def test_rates_showcase_api_returns_backend_curve_and_kr_dv01():
    with TestClient(app) as client:
        resp = client.get("/api/v1/market/rates-showcase")
    assert resp.status_code == 200
    body = resp.json()
    assert body["portfolio_id"] == "rates-macro"
    assert body["market_snapshot_id"] == "demo:rates-macro"
    conventions = body["conventions"]
    assert conventions["shock_unit"] == "1bp = 1e-4 decimal"
    assert conventions["sensitivity_unit"] == "currency P&L per +1bp"
    assert "not" in conventions["limitations"].lower()
    assert "multi-curve" in conventions["limitations"].lower()
    nodes = {n["tenor"]: n for n in body["discount_curve"]["nodes"]}
    assert set(SHOWCASE_TENORS) <= set(nodes)
    kr = {row["tenor"]: row["value"] for row in body["key_rate_dv01"]}
    assert set(SHOWCASE_TENORS) <= set(kr)
    assert kr["2Y"] != pytest.approx(kr["10Y"], rel=1e-9, abs=1e-6)
    assert kr["2Y"] != pytest.approx(body["parallel_dv01"], rel=1e-9, abs=1e-6)
    assert all(row["unit"] == "per_bp" for row in body["key_rate_dv01"])
    # API numbers equal SensitivityEngine on the same demo snapshot (no UI math).
    market = demo_market_snapshot(RATES_MACRO_PORTFOLIO)
    expected = _kr_by_tenor(RATES_MACRO_PORTFOLIO, market)
    for tenor in SHOWCASE_TENORS:
        assert kr[tenor] == pytest.approx(expected[tenor], rel=1e-12, abs=1e-9)
    assert body["parallel_dv01"] == pytest.approx(_parallel_dv01(RATES_MACRO_PORTFOLIO, market), rel=1e-12, abs=1e-9)
