"""Builtin fail-closed snapshot authority (R0.2 FX + rates/IR families).

When ``market`` is supplied, FX, bond, swap, IR-future, cap/floor, and
swaption pricing require snapshot marks and must not fall back to
trade-local yields / par rates / quotes / IR vol. ``market is None``
keeps the existing demo/reference path.
"""

from __future__ import annotations

import math

import pytest

from app.domain.models import (
    BondPosition,
    CapFloorPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    SwapPosition,
    SwaptionPosition,
)
from app.market.demo_snapshot import MissingMarketDataError
from app.pricing.builtin import BuiltinPricingEngine
from app.sample import (
    CROSS_ASSET_PORTFOLIO,
    RATES_MACRO_PORTFOLIO,
    _DEMO_AGGREGATE_MARKETS,
    demo_aggregate_market_snapshot,
    demo_market_snapshot,
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


def _bond() -> BondPosition:
    return BondPosition(
        type="bond",
        id="bond-auth",
        issuer="UST",
        face_value=1_000_000.0,
        quantity=1.0,
        maturity_years=5.0,
        yield_rate=0.10,
        duration=4.5,
        currency="USD",
    )


def _swap() -> SwapPosition:
    return SwapPosition(
        type="swap",
        id="swap-auth",
        currency="USD",
        notional=1_000_000.0,
        maturity_years=5.0,
        fixed_rate=0.04,
        market_swap_rate=0.10,
        pay_fixed=True,
        duration=4.0,
    )


def _ir_future() -> InterestRateFuturePosition:
    return InterestRateFuturePosition(
        type="ir_future",
        id="ed-auth",
        currency="USD",
        quantity=10.0,
        pv01=25.0,
        quoted_rate=0.10,
        forward_rate=0.10,
        maturity_years=0.25,
    )


def _cap() -> CapFloorPosition:
    return CapFloorPosition(
        type="cap_floor",
        id="cap-auth",
        currency="USD",
        notional=1_000_000.0,
        strike=0.04,
        maturity_years=2.0,
        volatility=0.50,
        option_type="cap",
        forward_rate=0.10,
        discount_rate=0.10,
        payment_frequency_per_year=2,
    )


def _swaption() -> SwaptionPosition:
    return SwaptionPosition(
        type="swaption",
        id="swaption-auth",
        currency="USD",
        notional=1_000_000.0,
        strike=0.04,
        option_maturity_years=1.0,
        swap_tenor_years=5.0,
        volatility=0.50,
        option_type="payer",
        forward_swap_rate=0.10,
        discount_rate=0.10,
        payment_frequency_per_year=2,
    )


def _act365_fixed_years(maturity_years: float) -> float:
    return max(1, round(float(maturity_years) * 365.0)) / 365.0


@pytest.mark.parametrize("book_factory", [_bond, _swap], ids=["bond", "swap"])
@pytest.mark.parametrize(
    "rates",
    [{}, {"EUR": 0.03}],
    ids=["empty-rates", "eur-only"],
)
def test_missing_bond_swap_rate_raises_when_market_is_supplied(
    book_factory, rates: dict[str, float]
) -> None:
    market = MarketSnapshot(id="no-usd-rate", rates=rates)

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(book_factory(), market)
    assert raised.value.factor_key == "rates[USD]"


@pytest.mark.parametrize(
    "rates,projection_rates,factor_key",
    [
        ({}, {}, "projection_rates[USD]"),
        ({}, {"EUR": 0.03}, "projection_rates[USD]"),
        ({"EUR": 0.03}, {}, "projection_rates[USD]"),
    ],
    ids=["empty", "eur-proj", "eur-rates"],
)
def test_missing_ir_future_forward_raises_when_market_is_supplied(
    rates: dict[str, float], projection_rates: dict[str, float], factor_key: str
) -> None:
    market = MarketSnapshot(
        id="no-usd-fwd",
        rates=rates,
        projection_rates=projection_rates,
        ir_future_quotes={"USD": 0.042},
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(_ir_future(), market)
    assert raised.value.factor_key == factor_key


@pytest.mark.parametrize(
    "quotes",
    [{}, {"EUR": 0.03}],
    ids=["empty-quotes", "eur-only"],
)
def test_missing_ir_future_quote_raises_when_market_is_supplied(
    quotes: dict[str, float],
) -> None:
    market = MarketSnapshot(
        id="no-usd-quote",
        rates={"USD": 0.0425},
        projection_rates={"USD": 0.0425},
        ir_future_quotes=quotes,
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(_ir_future(), market)
    assert raised.value.factor_key == "ir_future_quotes[USD]"


@pytest.mark.parametrize("book_factory", [_cap, _swaption], ids=["cap", "swaption"])
@pytest.mark.parametrize(
    "rates",
    [{}, {"EUR": 0.03}],
    ids=["empty-rates", "eur-only"],
)
def test_missing_ir_option_discount_raises_when_market_is_supplied(
    book_factory, rates: dict[str, float]
) -> None:
    market = MarketSnapshot(
        id="no-usd-discount",
        rates=rates,
        projection_rates={"USD": 0.04},
        ir_vols={"USD": 0.20},
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(book_factory(), market)
    assert raised.value.factor_key == "rates[USD]"


@pytest.mark.parametrize("book_factory", [_cap, _swaption], ids=["cap", "swaption"])
@pytest.mark.parametrize(
    "projection_rates",
    [{}, {"EUR": 0.03}],
    ids=["empty-proj", "eur-only"],
)
def test_missing_ir_option_forward_raises_when_market_is_supplied(
    book_factory, projection_rates: dict[str, float]
) -> None:
    market = MarketSnapshot(
        id="no-usd-proj",
        rates={},
        projection_rates=projection_rates,
        ir_vols={"USD": 0.20},
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(book_factory(), market)
    assert raised.value.factor_key == "projection_rates[USD]"


@pytest.mark.parametrize("book_factory", [_cap, _swaption], ids=["cap", "swaption"])
@pytest.mark.parametrize(
    "ir_vols",
    [{}, {"EUR": 0.15}],
    ids=["empty-vols", "eur-only"],
)
def test_missing_ir_option_vol_raises_when_market_is_supplied(
    book_factory, ir_vols: dict[str, float]
) -> None:
    market = MarketSnapshot(
        id="no-usd-ir-vol",
        rates={"USD": 0.035},
        projection_rates={"USD": 0.04},
        ir_vols=ir_vols,
    )

    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(book_factory(), market)
    assert raised.value.factor_key == "ir_vols[USD]"


def test_complete_snapshot_bond_matches_scalar_path_and_does_not_mutate_trade() -> None:
    position = _bond()
    original = position.model_dump(mode="json")
    market = MarketSnapshot(id="bond-complete", rates={"USD": 0.04})
    local = position.model_copy(update={"yield_rate": 0.04})

    valuation = BuiltinPricingEngine().value(position, market)
    t = _act365_fixed_years(position.maturity_years)
    expected = position.face_value * position.quantity * math.exp(-0.04 * t)

    assert valuation.market_value == pytest.approx(expected, rel=1e-12, abs=1e-9)
    assert valuation.market_value == pytest.approx(
        BuiltinPricingEngine().value(local).market_value, rel=1e-12, abs=1e-9
    )
    assert valuation.market_value != BuiltinPricingEngine().value(position).market_value
    assert position.model_dump(mode="json") == original


def test_complete_snapshot_swap_prices_without_mutating_trade() -> None:
    position = _swap()
    original = position.model_dump(mode="json")
    market = MarketSnapshot(id="swap-complete", rates={"USD": 0.041})
    local = position.model_copy(update={"market_swap_rate": 0.041})

    valuation = BuiltinPricingEngine().value(position, market)
    reference = BuiltinPricingEngine().value(local)

    assert valuation.market_value == pytest.approx(reference.market_value, rel=1e-12, abs=1e-9)
    assert valuation.market_value != BuiltinPricingEngine().value(position).market_value
    assert position.model_dump(mode="json") == original


def test_complete_snapshot_ir_future_prices_without_mutating_trade() -> None:
    position = _ir_future()
    original = position.model_dump(mode="json")
    market = MarketSnapshot(
        id="ed-complete",
        rates={"USD": 0.0425},
        projection_rates={"USD": 0.0425},
        ir_future_quotes={"USD": 0.042},
    )
    local = position.model_copy(update={"quoted_rate": 0.042, "forward_rate": 0.0425})

    valuation = BuiltinPricingEngine().value(position, market)
    reference = BuiltinPricingEngine().value(local)

    assert valuation.market_value == pytest.approx(reference.market_value, rel=1e-12, abs=1e-9)
    assert valuation.market_value != BuiltinPricingEngine().value(position).market_value
    assert position.model_dump(mode="json") == original


def test_complete_snapshot_ir_options_price_without_mutating_trade() -> None:
    cap = _cap()
    swaption = _swaption()
    original_cap = cap.model_dump(mode="json")
    original_swaption = swaption.model_dump(mode="json")
    market = MarketSnapshot(
        id="ir-opt-complete",
        rates={"USD": 0.035},
        projection_rates={"USD": 0.04},
        ir_vols={"USD": 0.20},
    )
    cap_local = cap.model_copy(
        update={"volatility": 0.20, "forward_rate": 0.04, "discount_rate": 0.035}
    )
    swaption_local = swaption.model_copy(
        update={"volatility": 0.20, "forward_swap_rate": 0.04, "discount_rate": 0.035}
    )
    pricing = BuiltinPricingEngine()

    assert pricing.value(cap, market).market_value == pytest.approx(
        pricing.value(cap_local).market_value, rel=1e-12, abs=1e-8
    )
    assert pricing.value(swaption, market).market_value == pytest.approx(
        pricing.value(swaption_local).market_value, rel=1e-12, abs=1e-8
    )
    assert pricing.value(cap, market).market_value != pricing.value(cap).market_value
    assert pricing.value(swaption, market).market_value != pricing.value(swaption).market_value
    assert cap.model_dump(mode="json") == original_cap
    assert swaption.model_dump(mode="json") == original_swaption


def test_rates_ir_use_trade_local_marks_when_market_is_none() -> None:
    pricing = BuiltinPricingEngine()
    bond = _bond()
    t = _act365_fixed_years(bond.maturity_years)
    bond_expected = bond.face_value * bond.quantity * math.exp(-bond.yield_rate * t)
    swap = _swap()
    swap_expected = (swap.market_swap_rate - swap.fixed_rate) * swap.notional * swap.duration
    future = _ir_future()
    future_expected = future.quantity * future.pv01 * (future.quoted_rate - future.forward_rate) * 10000.0

    assert pricing.value(bond).market_value == pytest.approx(bond_expected, rel=1e-12, abs=1e-9)
    assert pricing.value(swap).market_value == pytest.approx(swap_expected, rel=1e-12, abs=1e-9)
    assert pricing.value(future).market_value == pytest.approx(future_expected, rel=1e-12, abs=1e-9)
    assert pricing.value(_cap()).market_value > 0.0
    assert pricing.value(_swaption()).market_value > 0.0


def test_aggregate_demo_snapshots_seed_required_rates_ir_marks() -> None:
    seeded = _DEMO_AGGREGATE_MARKETS["rates-macro"]
    assert seeded.rates["USD"] == 0.0425
    assert seeded.ir_future_quotes["USD"] == 0.042
    resolved = demo_aggregate_market_snapshot(RATES_MACRO_PORTFOLIO)
    assert resolved.rates["USD"] == 0.0425
    assert resolved.ir_future_quotes["USD"] == 0.042
    explicit = demo_market_snapshot(RATES_MACRO_PORTFOLIO)
    assert explicit.ir_future_quotes["USD"] == 0.042
    future = next(p for p in RATES_MACRO_PORTFOLIO.positions if p.id == "fut-ed")
    BuiltinPricingEngine().value(future, resolved)
    BuiltinPricingEngine().value(future, explicit)


def test_dropping_aggregate_rate_fails_closed_on_sample_bond() -> None:
    market = demo_aggregate_market_snapshot(RATES_MACRO_PORTFOLIO)
    stripped = market.model_copy(update={"rates": {}, "key_rates": {}, "curves": {}})
    bond = next(p for p in RATES_MACRO_PORTFOLIO.positions if p.id == "bond-ust10")
    with pytest.raises(MissingMarketDataError) as raised:
        BuiltinPricingEngine().value(bond, stripped)
    assert raised.value.factor_key == "rates[USD]"
