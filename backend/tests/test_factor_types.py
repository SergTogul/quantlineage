"""Tests for typed risk-factor taxonomy (M1.6)."""

from __future__ import annotations

import math

from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import (
    EquitySpot,
    EquityVol,
    FXSpot,
    FXVol,
    RateZero,
    parse_risk_factor,
)
from app.risk.factors import RiskFactorEngine
from app.risk.historical import HistoricalRiskEngine
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService


def test_equity_spot_identity_and_key():
    a = EquitySpot("NVDA")
    b = EquitySpot("NVDA")
    c = EquitySpot("SPY")
    assert a == b
    assert hash(a) == hash(b)
    assert a != c
    assert a.key == "NVDA"
    assert a.factor_type == "equity"
    assert a.bucket == "NVDA"


def test_equity_vol_key_stable_while_surface_dims_differ():
    atm = EquityVol(underlying="SPX", expiry="3M", moneyness="ATM")
    wing = EquityVol(underlying="SPX", expiry="3M", moneyness="25D")
    other = EquityVol(underlying="SPY", expiry="3M", moneyness="ATM")
    assert atm.key == "SPX:VOL"
    assert wing.key == "SPX:VOL"
    assert atm != wing  # richer taxonomy distinguishes surface buckets
    assert hash(atm) != hash(wing)
    assert atm != other
    assert atm.factor_type == "vol"
    assert atm.bucket == "SPX"


def test_rate_zero_and_fx_spot_keys():
    rate = RateZero(currency="USD", tenor="10Y")
    assert rate.key == "USD:RATE"
    assert rate.factor_type == "rate"
    assert rate.bucket == "10Y"
    assert RateZero("USD", "10Y") == rate
    assert RateZero("USD", "5Y") != rate

    fx = FXSpot("EURUSD")
    assert fx.key == "EURUSD"
    assert fx.factor_type == "fx"
    assert fx.bucket == "EURUSD"
    assert FXVol("EURUSD").key == "EURUSD:VOL"


def test_parse_risk_factor_round_trip():
    assert parse_risk_factor("NVDA", "equity", "NVDA") == EquitySpot("NVDA")
    assert parse_risk_factor("SPY:VOL", "vol", "SPY") == EquityVol(underlying="SPY")
    assert parse_risk_factor("USD:RATE", "rate", "10Y") == RateZero("USD", "10Y")
    assert parse_risk_factor("EURUSD", "fx", "EURUSD") == FXSpot("EURUSD")
    assert parse_risk_factor("EURUSD:VOL", "vol", "EURUSD") == FXVol(pair="EURUSD")


def test_factor_engine_uses_typed_keys_with_string_api():
    engine = RiskFactorEngine()
    pricing = BuiltinPricingEngine()
    typed = engine.calculate_typed(SAMPLE_PORTFOLIO, pricing)
    api = engine.calculate(SAMPLE_PORTFOLIO, pricing)

    assert typed
    assert len(typed) == len(api)
    for (factor, exposure), dto in zip(typed, api):
        assert dto.factor == factor.key
        assert dto.factor_type == factor.factor_type
        assert dto.bucket == factor.bucket
        assert math.isclose(dto.exposure, exposure, rel_tol=0, abs_tol=0)

    keys = {f.key for f, _ in typed}
    assert "NVDA" in keys
    assert "SPY" in keys
    assert "SPY:VOL" in keys
    assert "NVDA:VOL" in keys
    assert "USD:RATE" in keys
    assert "EURUSD" in keys
    assert "EURUSD:VOL" in keys

    types = {f.factor_type for f, _ in typed}
    assert types == {"equity", "vol", "rate", "fx"}

    # Aggregation still merges same typed factors (e.g. multiple SPY equity legs).
    spy_spot = next(f for f, _ in typed if f == EquitySpot("SPY"))
    assert isinstance(spy_spot, EquitySpot)


def test_portfolio_factor_aggregation_smoke():
    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    exposures = svc.factors(SAMPLE_PORTFOLIO)
    by_key = {x.factor: x for x in exposures}
    assert by_key["NVDA"].factor_type == "equity"
    assert by_key["SPY:VOL"].factor_type == "vol"
    assert by_key["USD:RATE"].factor_type == "rate"
    assert by_key["EURUSD"].factor_type == "fx"
    # Bond (~10Y) and swap (5Y) remain distinct rate buckets under one currency key.
    rate_buckets = {x.bucket for x in exposures if x.factor == "USD:RATE"}
    assert rate_buckets == {"10Y", "5Y"}
    assert all(isinstance(x.factor, str) for x in exposures)
