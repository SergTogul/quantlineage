"""Regression coverage for durable RiskRun as-of and hierarchy KR-DV01 correctness."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.models import BondPosition, MarketSnapshot, Portfolio, RiskSummary
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.limits import LimitEngine
from app.risk.sensitivities import SensitivityEngine
from app.services.risk_factories import (
    ResolvedRiskRunSpec,
    build_portfolio_service,
    dataset_identity,
    portfolio_service_for_spec,
)


def _spec(*, as_of: date) -> ResolvedRiskRunSpec:
    service = build_portfolio_service()
    dataset_id, dataset_version = dataset_identity(service.risk.dataset)
    return ResolvedRiskRunSpec(
        historical_dataset_id=dataset_id,
        historical_dataset_version=dataset_version,
        as_of=as_of,
    )


def test_portfolio_service_for_spec_rejects_market_as_of_mismatch():
    base = build_portfolio_service()
    market = MarketSnapshot(id="snap", as_of="2026-09-02")
    with pytest.raises(ValueError, match="risk run as_of does not match persisted market snapshot"):
        portfolio_service_for_spec(base, _spec(as_of=date(2026, 9, 3)), market=market)


def test_portfolio_service_for_spec_accepts_matching_market_as_of():
    base = build_portfolio_service()
    market = MarketSnapshot(id="snap", as_of="2026-09-02")
    rebound = portfolio_service_for_spec(base, _spec(as_of=date(2026, 9, 2)), market=market)
    assert rebound.market_data.snapshot(Portfolio(id="p", name="p", positions=[])).as_of == date(2026, 9, 2)


def test_key_rate_limit_does_not_trust_parallel_dv01_proxy_when_tenors_exist():
    pricing = BuiltinPricingEngine()
    position = BondPosition(
        type="bond",
        id="bond-10y",
        issuer="UST",
        face_value=1_000_000,
        quantity=1,
        maturity_years=10.0,
        duration=8.0,
    )
    portfolio = Portfolio(id="rates", name="Rates", positions=[position])
    market = MarketSnapshot(
        id="rates-snap",
        as_of="2026-09-02",
        rates={"USD": 0.04},
        key_rates={"USD": {"2Y": 0.03, "10Y": 0.04}},
    )
    valuation = pricing.value(position, market)
    risk = RiskSummary(
        portfolio_id=portfolio.id,
        market_value=valuation.market_value,
        delta=valuation.delta,
        gamma=valuation.gamma,
        vega=valuation.vega,
        dv01=valuation.dv01,
        fx_delta=valuation.fx_delta,
        var_95=0.0,
        var_99=0.0,
        expected_shortfall_99=0.0,
    )
    expected = max(
        abs(m.value)
        for m in SensitivityEngine().calculate(
            portfolio,
            pricing,
            measures=("key_rate_dv01",),
            market=market,
        )
    )
    metrics = LimitEngine().resolve_metrics(
        portfolio,
        pricing,
        risk,
        needed={"key_rate_dv01"},
        market=market,
        extra={"key_rate_dv01": 0.01},
    )
    assert metrics["key_rate_dv01"] == pytest.approx(expected)
    assert metrics["key_rate_dv01"] > 1.0
