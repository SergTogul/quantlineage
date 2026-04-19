"""Typed InstrumentTerms extract contractual economics and omit live marks.

Structural equality only — no invented pricing or risk numbers.
"""

from __future__ import annotations

import pytest

from app.domain.instrument_terms import (
    BondTerms,
    CapFloorTerms,
    EquityFutureTerms,
    EquityTerms,
    EuropeanOptionTerms,
    FXForwardTerms,
    FXOptionTerms,
    InstrumentTerms,
    InterestRateFutureTerms,
    SwapTerms,
    SwaptionTerms,
    terms_from_position,
)
from app.domain.models import (
    BondPosition,
    CapFloorPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    SwapPosition,
    SwaptionPosition,
)


def _equity() -> EquityPosition:
    return EquityPosition(
        type="equity",
        id="eq1",
        symbol="SPY",
        quantity=10.0,
        sector="Index",
        book="Equity",
        desk="Delta",
        strategy="Core")


def _equity_future() -> EquityFuturePosition:
    return EquityFuturePosition(
        type="equity_future",
        id="eqf1",
        symbol="ES",
        quantity=2.0,
        multiplier=50.0,
        maturity_years=0.25,
        sector="Index",
        book="Equity Derivatives",
        desk="Futures",
        strategy="Beta")


def _equity_option() -> EuropeanOptionPosition:
    return EuropeanOptionPosition(
        type="european_option",
        id="eqo1",
        symbol="AAPL",
        quantity=5.0,
        strike=175.0,
        maturity_years=0.5,
        option_type="call",
        sector="Tech",
        book="Equity Derivatives",
        desk="Options",
        strategy="Vol")


def _bond() -> BondPosition:
    return BondPosition(
        type="bond",
        id="bnd1",
        issuer="UST",
        face_value=1000.0,
        quantity=2.0,
        maturity_years=5.0,
        duration=4.5,
        currency="USD",
        book="Rates",
        desk="Rates Cash",
        strategy="Govvies")


def _swap() -> SwapPosition:
    return SwapPosition(
        type="swap",
        id="swp1",
        currency="USD",
        notional=1_000_000.0,
        maturity_years=5.0,
        fixed_rate=0.035,
        pay_fixed=True,
        duration=4.0,
        book="Rates Derivatives",
        desk="Swaps",
        strategy="Pay")


def _fx_forward() -> FXForwardPosition:
    return FXForwardPosition(
        type="fx_forward",
        id="fxf1",
        pair="EURUSD",
        notional_base=1_000_000.0,
        strike=1.08,
        maturity_years=0.5,
        book="FX",
        desk="FX Cash",
        strategy="Forwards")


def _fx_option() -> FXOptionPosition:
    return FXOptionPosition(
        type="fx_option",
        id="fxo1",
        pair="EURUSD",
        notional_base=1_000_000.0,
        strike=1.10,
        maturity_years=0.5,
        option_type="put",
        book="FX Derivatives",
        desk="FX Vol",
        strategy="Hedge")


def _ir_future() -> InterestRateFuturePosition:
    return InterestRateFuturePosition(
        type="ir_future",
        id="irf1",
        currency="USD",
        quantity=10.0,
        pv01=25.0,
        maturity_years=0.25,
        book="Rates Derivatives",
        desk="STIR",
        strategy="Curve")


def _cap_floor() -> CapFloorPosition:
    return CapFloorPosition(
        type="cap_floor",
        id="cap1",
        currency="USD",
        notional=1_000_000.0,
        quantity=1.0,
        strike=0.03,
        maturity_years=2.0,
        option_type="cap",
        payment_frequency_per_year=2,
        book="Rates Derivatives",
        desk="IR Vol",
        strategy="Caps")


def _swaption() -> SwaptionPosition:
    return SwaptionPosition(
        type="swaption",
        id="swn1",
        currency="USD",
        notional=1_000_000.0,
        quantity=1.0,
        strike=0.03,
        option_maturity_years=1.0,
        swap_tenor_years=5.0,
        option_type="payer",
        payment_frequency_per_year=2,
        book="Rates Derivatives",
        desk="IR Vol",
        strategy="Swaptions")


# Live observables / derived duration that trade_cache_key already excludes.
_FAMILY_CASES = [
    (
        "equity",
        _equity,
        EquityTerms,
        frozenset({"price"}),
        {"price": 125.0},
        {"quantity": 20.0},
    ),
    (
        "equity_future",
        _equity_future,
        EquityFutureTerms,
        frozenset({"spot", "risk_free_rate", "dividend_yield"}),
        {"spot": 4800.0, "risk_free_rate": 0.05, "dividend_yield": 0.02},
        {"maturity_years": 0.5},
    ),
    (
        "european_option",
        _equity_option,
        EuropeanOptionTerms,
        frozenset({"spot", "volatility", "risk_free_rate", "dividend_yield"}),
        {"spot": 200.0, "volatility": 0.40},
        {"strike": 190.0},
    ),
    (
        "bond",
        _bond,
        BondTerms,
        frozenset({"yield_rate", "duration"}),
        {"yield_rate": 0.09, "duration": 3.0},
        {"maturity_years": 10.0},
    ),
    (
        "swap",
        _swap,
        SwapTerms,
        frozenset({"market_swap_rate", "duration"}),
        {"market_swap_rate": 0.06, "duration": 3.0},
        {"notional": 2_000_000.0},
    ),
    (
        "fx_forward",
        _fx_forward,
        FXForwardTerms,
        frozenset({"spot", "domestic_rate", "foreign_rate"}),
        {"spot": 1.25, "domestic_rate": 0.05, "foreign_rate": 0.01},
        {"strike": 1.20},
    ),
    (
        "fx_option",
        _fx_option,
        FXOptionTerms,
        frozenset({"spot", "volatility", "domestic_rate", "foreign_rate"}),
        {"spot": 1.25, "volatility": 0.30},
        {"strike": 1.20},
    ),
    (
        "ir_future",
        _ir_future,
        InterestRateFutureTerms,
        frozenset({"quoted_rate", "forward_rate"}),
        {"quoted_rate": 0.05, "forward_rate": 0.055},
        {"quantity": 20.0},
    ),
    (
        "cap_floor",
        _cap_floor,
        CapFloorTerms,
        frozenset({"volatility", "forward_rate", "discount_rate"}),
        {"volatility": 0.35, "forward_rate": 0.04, "discount_rate": 0.05},
        {"strike": 0.04},
    ),
    (
        "swaption",
        _swaption,
        SwaptionTerms,
        frozenset({"volatility", "forward_swap_rate", "discount_rate"}),
        {"volatility": 0.35, "forward_swap_rate": 0.04, "discount_rate": 0.05},
        {"strike": 0.04},
    ),
]


def _assert_hierarchy_round_trip(position, terms) -> None:
    assert terms.desk == position.desk
    assert terms.strategy == position.strategy
    assert terms.book == position.book
    if hasattr(position, "sector"):
        assert terms.sector == position.sector


def _assert_contractual_round_trip(position, terms) -> None:
    assert terms.id == position.id
    assert terms.type == position.type
    _assert_hierarchy_round_trip(position, terms)

    if isinstance(position, EquityPosition):
        assert terms.symbol == position.symbol
        assert terms.quantity == position.quantity
        assert terms.currency == "USD"
    elif isinstance(position, EquityFuturePosition):
        assert terms.symbol == position.symbol
        assert terms.quantity == position.quantity
        assert terms.multiplier == position.multiplier
        assert terms.maturity_years == position.maturity_years
        assert terms.currency == "USD"
    elif isinstance(position, EuropeanOptionPosition):
        assert terms.symbol == position.symbol
        assert terms.quantity == position.quantity
        assert terms.strike == position.strike
        assert terms.maturity_years == position.maturity_years
        assert terms.option_type == position.option_type
        assert terms.currency == "USD"
    elif isinstance(position, BondPosition):
        assert terms.issuer == position.issuer
        assert terms.face_value == position.face_value
        assert terms.quantity == position.quantity
        assert terms.maturity_years == position.maturity_years
        assert terms.currency == position.currency
    elif isinstance(position, SwapPosition):
        assert terms.currency == position.currency
        assert terms.notional == position.notional
        assert terms.maturity_years == position.maturity_years
        assert terms.fixed_rate == position.fixed_rate
        assert terms.pay_fixed == position.pay_fixed
    elif isinstance(position, FXForwardPosition):
        assert terms.pair == position.pair
        assert terms.notional_base == position.notional_base
        assert terms.strike == position.strike
        assert terms.maturity_years == position.maturity_years
    elif isinstance(position, FXOptionPosition):
        assert terms.pair == position.pair
        assert terms.notional_base == position.notional_base
        assert terms.strike == position.strike
        assert terms.maturity_years == position.maturity_years
        assert terms.option_type == position.option_type
    elif isinstance(position, InterestRateFuturePosition):
        assert terms.currency == position.currency
        assert terms.quantity == position.quantity
        assert terms.pv01 == position.pv01
        assert terms.maturity_years == position.maturity_years
    elif isinstance(position, CapFloorPosition):
        assert terms.currency == position.currency
        assert terms.notional == position.notional
        assert terms.quantity == position.quantity
        assert terms.strike == position.strike
        assert terms.maturity_years == position.maturity_years
        assert terms.option_type == position.option_type
        assert terms.payment_frequency_per_year == position.payment_frequency_per_year
    elif isinstance(position, SwaptionPosition):
        assert terms.currency == position.currency
        assert terms.notional == position.notional
        assert terms.quantity == position.quantity
        assert terms.strike == position.strike
        assert terms.option_maturity_years == position.option_maturity_years
        assert terms.swap_tenor_years == position.swap_tenor_years
        assert terms.option_type == position.option_type
        assert terms.payment_frequency_per_year == position.payment_frequency_per_year
    else:
        raise AssertionError(f"unhandled position family {type(position).__name__}")


@pytest.mark.parametrize(
    ("family", "factory", "terms_cls", "mark_fields", "_mark_update", "_econ_update"),
    _FAMILY_CASES,
    ids=[row[0] for row in _FAMILY_CASES],
)
def test_every_family_round_trips_economics_and_omits_marks(
    family, factory, terms_cls, mark_fields, _mark_update, _econ_update
):
    position = factory()
    terms = terms_from_position(position)

    assert isinstance(terms, terms_cls)
    assert isinstance(terms, InstrumentTerms)
    _assert_contractual_round_trip(position, terms)

    dumped = terms.model_dump()
    for field in mark_fields:
        assert field not in dumped
        assert field not in type(terms).model_fields
        # Phase B: live marks are gone from Position; duration remains as DV01 shortcut.
        if field == "duration":
            assert field in type(position).model_fields
        else:
            assert field not in type(position).model_fields


@pytest.mark.parametrize(
    ("family", "factory", "_terms_cls", "_mark_fields", "mark_update", "_econ_update"),
    _FAMILY_CASES,
    ids=[row[0] for row in _FAMILY_CASES],
)
def test_positions_reject_live_mark_updates(
    family, factory, _terms_cls, _mark_fields, mark_update, _econ_update
):
    from pydantic import ValidationError

    position = factory()
    # duration-only updates remain valid; live marks must raise on (re)construction.
    live = {k: v for k, v in mark_update.items() if k != "duration"}
    if live:
        payload = position.model_dump(mode="python")
        payload.update(live)
        with pytest.raises(ValidationError):
            type(position).model_validate(payload)
    if "duration" in mark_update:
        other = position.model_copy(update={"duration": mark_update["duration"]})
        assert terms_from_position(position) == terms_from_position(other)


@pytest.mark.parametrize(
    ("family", "factory", "_terms_cls", "_mark_fields", "_mark_update", "econ_update"),
    _FAMILY_CASES,
    ids=[row[0] for row in _FAMILY_CASES],
)
def test_positions_that_differ_in_strike_maturity_or_notional_produce_different_terms(
    family, factory, _terms_cls, _mark_fields, _mark_update, econ_update
):
    position = factory()
    other = position.model_copy(update=econ_update)
    assert terms_from_position(position) != terms_from_position(other)


def test_unknown_position_type_raises_type_error():
    class _UnknownPosition:
        type = "mystery"

        def model_dump(self, mode="json"):
            return {"id": "x", "price": 1.0}

    with pytest.raises(TypeError, match="no terms projection"):
        terms_from_position(_UnknownPosition())  # type: ignore[arg-type]
