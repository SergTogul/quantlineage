"""RF-011 R0.4.1-C: equity/option rate lookup uses explicit instrument currency.

Missing EUR (or other non-USD) rates on an explicit snapshot fail closed.
``MarketSnapshot.rates`` still defaults to ``{"USD": 0.04}`` when omitted.
USD demo books and snapshot ids stay unchanged. No invented FX/rate numbers.
"""

from __future__ import annotations

from datetime import date

import pytest
from tests.quantlib_gate import import_quantlib

from app.domain.instrument_terms import terms_from_position
from app.domain.models import (
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    MarketSnapshot,
)
from app.market.demo_snapshot import MissingMarketDataError
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine
from app.risk.attribution import _rate_currency
from app.sample import (
    CROSS_ASSET_PORTFOLIO,
    DEMO_PORTFOLIOS,
    EQUITY_VOL_PORTFOLIO,
    RATES_MACRO_PORTFOLIO,
    SAMPLE_PORTFOLIO,
    demo_aggregate_market_snapshot,
    demo_market_snapshot,
)

builtin = BuiltinPricingEngine()


def _eur_option() -> EuropeanOptionPosition:
    return EuropeanOptionPosition(
        type="european_option",
        id="eur-opt",
        symbol="DAX",
        quantity=1.0,
        strike=100.0,
        maturity_years=1.0,
        option_type="call",
        currency="EUR",
    )


def _eur_future() -> EquityFuturePosition:
    return EquityFuturePosition(
        type="equity_future",
        id="eur-fut",
        symbol="DAX",
        quantity=1.0,
        multiplier=25.0,
        maturity_years=0.25,
        currency="EUR",
    )


def _usd_option() -> EuropeanOptionPosition:
    return EuropeanOptionPosition(
        type="european_option",
        id="usd-opt",
        symbol="SPY",
        quantity=1.0,
        strike=100.0,
        maturity_years=1.0,
        option_type="call",
    )


def _option_market(*, symbol: str, rates: dict[str, float] | None, **extra) -> MarketSnapshot:
    payload: dict = {
        "id": "explicit-ccy",
        "equity_spots": {symbol: 100.0},
        "equity_vols": {symbol: 0.20},
        "dividend_yields": {symbol: 0.0},
    }
    if rates is not None:
        payload["rates"] = rates
    payload.update(extra)
    return MarketSnapshot(**payload)


@pytest.mark.parametrize(
    "rates",
    [{}, {"USD": 0.04}],
    ids=["empty-rates", "usd-only"],
)
def test_eur_equity_option_missing_eur_rate_fails_closed(rates: dict[str, float]) -> None:
    position = _eur_option()
    market = _option_market(symbol=position.symbol, rates=rates)
    with pytest.raises(MissingMarketDataError) as raised:
        builtin.value(position, market)
    assert raised.value.factor_key == "rates[EUR]"


@pytest.mark.parametrize(
    "rates",
    [{}, {"USD": 0.04}],
    ids=["empty-rates", "usd-only"],
)
def test_eur_equity_future_missing_eur_rate_fails_closed(rates: dict[str, float]) -> None:
    position = _eur_future()
    market = MarketSnapshot(
        id="explicit-ccy-fut",
        equity_spots={position.symbol: 100.0},
        dividend_yields={position.symbol: 0.0},
        rates=rates,
    )
    with pytest.raises(MissingMarketDataError) as raised:
        builtin.value(position, market)
    assert raised.value.factor_key == "rates[EUR]"


def test_eur_option_uses_eur_rate_not_usd_when_both_present() -> None:
    position = _eur_option()
    eur_only_change = _option_market(
        symbol=position.symbol, rates={"USD": 0.04, "EUR": 0.03}
    )
    usd_only_change = _option_market(
        symbol=position.symbol, rates={"USD": 0.10, "EUR": 0.03}
    )
    both_eur_higher = _option_market(
        symbol=position.symbol, rates={"USD": 0.04, "EUR": 0.08}
    )
    pv_base = builtin.value(position, eur_only_change).market_value
    pv_usd_moved = builtin.value(position, usd_only_change).market_value
    pv_eur_moved = builtin.value(position, both_eur_higher).market_value
    assert pv_usd_moved == pytest.approx(pv_base, rel=1e-12, abs=1e-12)
    assert pv_eur_moved != pytest.approx(pv_base, rel=1e-12, abs=1e-12)


def test_usd_option_empty_rates_fails_closed() -> None:
    position = _usd_option()
    market = _option_market(symbol=position.symbol, rates={})
    with pytest.raises(MissingMarketDataError) as raised:
        builtin.value(position, market)
    assert raised.value.factor_key == "rates[USD]"


def test_usd_option_omitted_snapshot_rates_uses_constructor_default() -> None:
    position = _usd_option()
    market = _option_market(symbol=position.symbol, rates=None)
    assert market.rates == {"USD": 0.04}
    valuation = builtin.value(position, market)
    assert isinstance(valuation.market_value, float)


def test_market_snapshot_omitted_rates_still_defaults_usd() -> None:
    snap = MarketSnapshot()
    assert snap.rates == {"USD": 0.04}
    empty = MarketSnapshot(rates={})
    assert dict(empty.rates) == {}


def test_terms_from_position_copies_explicit_equity_currency() -> None:
    option = _eur_option()
    future = _eur_future()
    cash = EquityPosition(
        type="equity", id="eur-eq", symbol="DAX", quantity=1.0, currency="EUR"
    )
    assert terms_from_position(option).currency == "EUR"
    assert terms_from_position(future).currency == "EUR"
    assert terms_from_position(cash).currency == "EUR"
    assert terms_from_position(_usd_option()).currency == "USD"


def test_rate_currency_uses_explicit_equity_derivative_currency() -> None:
    assert _rate_currency(_eur_option()) == "EUR"
    assert _rate_currency(_eur_future()) == "EUR"
    assert _rate_currency(_usd_option()) == "USD"
    cash = EquityPosition(type="equity", id="eq", symbol="SPY", quantity=1.0)
    assert _rate_currency(cash) is None


def test_eur_cash_equity_does_not_require_rates() -> None:
    position = EquityPosition(
        type="equity", id="eur-eq", symbol="DAX", quantity=2.0, currency="EUR"
    )
    market = MarketSnapshot(id="cash", equity_spots={"DAX": 50.0}, rates={})
    assert builtin.value(position, market).market_value == pytest.approx(100.0)


def test_usd_demo_books_and_snapshot_ids_unchanged() -> None:
    assert [p.id for p in DEMO_PORTFOLIOS] == [
        "equity-vol",
        "rates-macro",
        "global-macro",
    ]
    assert SAMPLE_PORTFOLIO is CROSS_ASSET_PORTFOLIO
    assert [p.id for p in EQUITY_VOL_PORTFOLIO.positions] == [
        "eq-nvda",
        "eq-spy",
        "opt-spy-put",
        "opt-nvda-call",
        "opt-spy-call-short",
        "fut-es",
    ]
    assert [p.id for p in RATES_MACRO_PORTFOLIO.positions] == [
        "bond-ust2",
        "bond-ust10",
        "swap-usd2y",
        "swap-usd5y",
        "swap-usd10y",
        "fut-ed",
    ]
    assert [p.id for p in CROSS_ASSET_PORTFOLIO.positions] == [
        "eq-nvda",
        "eq-spy",
        "opt-spy-put",
        "opt-nvda-call",
        "bond-ust10",
        "swap-usd5y",
        "fut-es",
        "fxf-eurusd",
        "fxo-eurusd",
    ]
    assert demo_market_snapshot(EQUITY_VOL_PORTFOLIO).id == "demo:equity-vol"
    assert demo_market_snapshot(RATES_MACRO_PORTFOLIO).id == "demo:rates-macro"
    assert demo_market_snapshot(CROSS_ASSET_PORTFOLIO).id == "demo:global-macro"
    assert demo_aggregate_market_snapshot(EQUITY_VOL_PORTFOLIO).id == (
        "demo-aggregate:equity-vol"
    )
    for position in EQUITY_VOL_PORTFOLIO.positions:
        assert getattr(position, "currency", "USD") == "USD"
    pv = builtin.value(
        EQUITY_VOL_PORTFOLIO.positions[2],
        demo_market_snapshot(EQUITY_VOL_PORTFOLIO),
    ).market_value
    assert isinstance(pv, float)


@pytest.fixture
def quantlib_engine():
    import_quantlib()
    return QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))


@pytest.mark.parametrize(
    "rates",
    [{}, {"USD": 0.04}],
    ids=["empty-rates", "usd-only"],
)
def test_quantlib_eur_option_missing_eur_rate_fails_closed(
    quantlib_engine, rates: dict[str, float]
) -> None:
    position = _eur_option()
    market = _option_market(symbol=position.symbol, rates=rates)
    with pytest.raises(MissingMarketDataError) as raised:
        quantlib_engine.value(position, market)
    assert raised.value.factor_key == "rates[EUR]"
