"""Builtin FX fail-closed snapshot authority (R0.2 family B).

When ``market`` is supplied, FX forwards and options require snapshot marks
and must not fall back to trade-local spot / vol / rates. ``market is None``
keeps the existing demo/reference path.
"""

from __future__ import annotations

import math

import pytest

from app.domain.models import FXForwardPosition, FXOptionPosition, MarketSnapshot
from app.market.demo_snapshot import MissingMarketDataError
from app.pricing.builtin import BuiltinPricingEngine
from app.sample import (
    CROSS_ASSET_PORTFOLIO,
    _DEMO_AGGREGATE_MARKETS,
    demo_aggregate_market_snapshot,
)


def _fx_forward() -> FXForwardPosition:
    return FXForwardPosition(
        type="fx_forward",
        id="fxf-auth",
        pair="EURUSD",
        notional_base=1_000_000.0,
        spot=1.50,
        strike=1.105,
        maturity_years=0.5,
        domestic_rate=0.10,
        foreign_rate=0.01,
    )


def _fx_option() -> FXOptionPosition:
    return FXOptionPosition(
        type="fx_option",
        id="fxo-auth",
        pair="EURUSD",
        notional_base=250_000.0,
        spot=1.50,
        strike=1.12,
        maturity_years=0.4,
        volatility=0.50,
        domestic_rate=0.10,
        foreign_rate=0.01,
        option_type="call",
    )


def _complete_fx_market(*, include_vol: bool = True) -> MarketSnapshot:
    payload: dict = {
        "id": "fx-complete",
        "fx_spots": {"EURUSD": 1.10},
        "rates": {"USD": 0.04, "EUR": 0.03},
    }
    if include_vol:
        payload["fx_vols"] = {"EURUSD": 0.12}
    return MarketSnapshot(**payload)


def _cip_pv(notional: float, spot: float, strike: float, t: float, rd: float, rf: float) -> float:
    forward = spot * math.exp((rd - rf) * t)
    return notional * (forward - strike) * math.exp(-rd * t)


@pytest.mark.parametrize("book_factory", [_fx_forward, _fx_option], ids=["forward", "option"])
@pytest.mark.parametrize(
    "fx_spots",
    [{}, {"GBPUSD": 1.25}],
    ids=["empty-spots", "gbp-only"],
)
def test_missing_fx_spot_raises_when_market_is_supplied(book_factory, fx_spots: dict[str, float]) -> None:
    position = book_factory()
    extra = {"fx_vols": {"EURUSD": 0.12}} if position.type == "fx_option" else {}
    market = MarketSnapshot(
        id="no-eurusd-spot",
        fx_spots=fx_spots,
        rates={"USD": 0.04, "EUR": 0.03},
        **extra,
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(position, market)
    assert raised.value.factor_key == f"fx_spots[{position.pair}]"


@pytest.mark.parametrize(
    "fx_vols",
    [{}, {"GBPUSD": 0.11}],
    ids=["empty-vols", "gbp-vol"],
)
def test_missing_fx_option_vol_raises_when_market_is_supplied(fx_vols: dict[str, float]) -> None:
    position = _fx_option()
    market = MarketSnapshot(
        id="no-eurusd-vol",
        fx_spots={"EURUSD": 1.10},
        fx_vols=fx_vols,
        rates={"USD": 0.04, "EUR": 0.03},
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(position, market)
    assert raised.value.factor_key == f"fx_vols[{position.pair}]"


@pytest.mark.parametrize("book_factory", [_fx_forward, _fx_option], ids=["forward", "option"])
@pytest.mark.parametrize(
    "rates",
    [{}, {"EUR": 0.03}],
    ids=["empty-rates", "eur-only"],
)
def test_missing_fx_domestic_rate_raises_when_market_is_supplied(
    book_factory, rates: dict[str, float]
) -> None:
    position = book_factory()
    extra = {"fx_vols": {"EURUSD": 0.12}} if position.type == "fx_option" else {}
    market = MarketSnapshot(
        id="no-usd-rate",
        fx_spots={"EURUSD": 1.10},
        rates=rates,
        **extra,
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(position, market)
    assert raised.value.factor_key == "rates[USD]"


@pytest.mark.parametrize("book_factory", [_fx_forward, _fx_option], ids=["forward", "option"])
def test_missing_fx_foreign_rate_raises_when_market_is_supplied(book_factory) -> None:
    position = book_factory()
    extra = {"fx_vols": {"EURUSD": 0.12}} if position.type == "fx_option" else {}
    market = MarketSnapshot(
        id="no-eur-rate",
        fx_spots={"EURUSD": 1.10},
        rates={"USD": 0.04},
        **extra,
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(position, market)
    assert raised.value.factor_key == "rates[EUR]"


def test_complete_snapshot_fx_forward_matches_cip_and_does_not_mutate_trade() -> None:
    position = _fx_forward()
    original = position.model_dump(mode="json")
    market = _complete_fx_market(include_vol=False)

    valuation = BuiltinPricingEngine().value(position, market)
    expected = _cip_pv(
        position.notional_base, 1.10, position.strike, position.maturity_years, 0.04, 0.03
    )

    assert valuation.market_value == pytest.approx(expected, rel=1e-12, abs=1e-9)
    assert valuation.market_value != BuiltinPricingEngine().value(position).market_value
    assert position.model_dump(mode="json") == original


def test_complete_snapshot_fx_option_prices_without_mutating_trade() -> None:
    position = _fx_option()
    original = position.model_dump(mode="json")
    market = _complete_fx_market()
    local_marks = position.model_copy(
        update={"spot": 1.10, "volatility": 0.12, "domestic_rate": 0.04, "foreign_rate": 0.03}
    )

    valuation = BuiltinPricingEngine().value(position, market)
    reference = BuiltinPricingEngine().value(local_marks)

    assert valuation.market_value == pytest.approx(reference.market_value, rel=1e-12, abs=1e-9)
    assert valuation.market_value != BuiltinPricingEngine().value(position).market_value
    assert position.model_dump(mode="json") == original


def test_fx_uses_trade_local_marks_when_market_is_none() -> None:
    forward = _fx_forward()
    option = _fx_option()
    pricing = BuiltinPricingEngine()

    fwd_expected = _cip_pv(
        forward.notional_base,
        forward.spot,
        forward.strike,
        forward.maturity_years,
        forward.domestic_rate,
        forward.foreign_rate,
    )
    assert pricing.value(forward).market_value == pytest.approx(fwd_expected, rel=1e-12, abs=1e-9)
    assert pricing.value(option).market_value > 0.0


def test_fx_option_surface_quote_satisfies_vol_without_fx_vols() -> None:
    from app.market.vol_surfaces import build_fx_vol_surface

    position = _fx_option()
    surface = build_fx_vol_surface("EURUSD", 0.12)
    market = MarketSnapshot(
        id="fx-surface-only",
        fx_spots={"EURUSD": 1.10},
        rates={"USD": 0.04, "EUR": 0.03},
        vol_surfaces={"EURUSD": surface.to_dict()},
    )
    scalar = _complete_fx_market()

    valuation = BuiltinPricingEngine().value(position, market)
    reference = BuiltinPricingEngine().value(position, scalar)
    assert valuation.market_value == pytest.approx(reference.market_value, rel=1e-12, abs=1e-9)


def test_aggregate_demo_snapshots_seed_required_fx_marks() -> None:
    seeded = _DEMO_AGGREGATE_MARKETS["global-macro"]
    assert seeded.fx_spots["EURUSD"] == 1.10
    assert seeded.fx_vols["EURUSD"] == 0.12
    assert seeded.rates["USD"] == 0.04
    assert seeded.rates["EUR"] == 0.03
    resolved = demo_aggregate_market_snapshot(CROSS_ASSET_PORTFOLIO)
    assert resolved.fx_spots["EURUSD"] == 1.10
    assert resolved.fx_vols["EURUSD"] == 0.12
    assert resolved.rates["EUR"] == 0.03


def test_dropping_aggregate_fx_spot_fails_closed_on_sample_forward() -> None:
    market = demo_aggregate_market_snapshot(CROSS_ASSET_PORTFOLIO)
    stripped = market.model_copy(update={"fx_spots": {}})
    forward = next(p for p in CROSS_ASSET_PORTFOLIO.positions if p.id == "fxf-eurusd")
    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(forward, stripped)
    assert raised.value.factor_key == "fx_spots[EURUSD]"
