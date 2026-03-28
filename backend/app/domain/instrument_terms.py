"""Typed contractual instrument terms (economics only; no live market marks).

Compatibility ``*Position`` DTOs in ``app.domain.models`` still carry marks.
This module extracts the production terms projection; it does not strip those
DTO fields or rewire pricing / cache identity.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, TypeAdapter

from app.domain.models import (
    BondPosition,
    CapFloorPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FiniteFloat,
    FiniteInputMixin,
    FXForwardPosition,
    FXOptionPosition,
    FxPair,
    InterestRateFuturePosition,
    Position,
    SwapPosition,
    SwaptionPosition,
)

# Equity cash/derivative Positions have no currency field; settlement is USD.
_EQUITY_SETTLEMENT_CURRENCY = "USD"


class InstrumentTermsBase(FiniteInputMixin):
    """Frozen contractual header shared by every family."""

    model_config = ConfigDict(frozen=True)

    id: str
    desk: str | None = None
    strategy: str | None = None


class EquityTerms(InstrumentTermsBase):
    type: Literal["equity"]
    symbol: str
    quantity: FiniteFloat
    currency: str = _EQUITY_SETTLEMENT_CURRENCY
    sector: str = "Other"
    book: str = "Equity"


class EquityFutureTerms(InstrumentTermsBase):
    type: Literal["equity_future"]
    symbol: str
    quantity: FiniteFloat
    multiplier: FiniteFloat = 50.0
    maturity_years: FiniteFloat = Field(default=0.25, gt=0)
    currency: str = _EQUITY_SETTLEMENT_CURRENCY
    sector: str = "Index"
    book: str = "Equity Derivatives"


class EuropeanOptionTerms(InstrumentTermsBase):
    type: Literal["european_option"]
    symbol: str
    quantity: FiniteFloat
    strike: FiniteFloat
    maturity_years: FiniteFloat = Field(gt=0)
    option_type: Literal["call", "put"]
    currency: str = _EQUITY_SETTLEMENT_CURRENCY
    sector: str = "Other"
    book: str = "Equity Derivatives"


class BondTerms(InstrumentTermsBase):
    type: Literal["bond"]
    issuer: str
    face_value: FiniteFloat = Field(gt=0)
    quantity: FiniteFloat = 1.0
    maturity_years: FiniteFloat = Field(gt=0)
    currency: str = "USD"
    book: str = "Rates"


class SwapTerms(InstrumentTermsBase):
    type: Literal["swap"]
    currency: str = "USD"
    notional: FiniteFloat = Field(gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    fixed_rate: FiniteFloat
    pay_fixed: bool = True
    book: str = "Rates Derivatives"


class FXForwardTerms(InstrumentTermsBase):
    type: Literal["fx_forward"]
    pair: FxPair
    notional_base: FiniteFloat
    strike: FiniteFloat = Field(gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    book: str = "FX"


class FXOptionTerms(InstrumentTermsBase):
    type: Literal["fx_option"]
    pair: FxPair
    notional_base: FiniteFloat
    strike: FiniteFloat = Field(gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    option_type: Literal["call", "put"]
    book: str = "FX Derivatives"


class InterestRateFutureTerms(InstrumentTermsBase):
    type: Literal["ir_future"]
    currency: str = "USD"
    quantity: FiniteFloat
    pv01: FiniteFloat = Field(default=25.0, gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    book: str = "Rates Derivatives"


class CapFloorTerms(InstrumentTermsBase):
    type: Literal["cap_floor"]
    currency: str = "USD"
    notional: FiniteFloat = Field(gt=0)
    quantity: FiniteFloat = 1.0
    strike: FiniteFloat = Field(gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    option_type: Literal["cap", "floor"]
    payment_frequency_per_year: int = Field(default=2, ge=1, le=12)
    book: str = "Rates Derivatives"


class SwaptionTerms(InstrumentTermsBase):
    type: Literal["swaption"]
    currency: str = "USD"
    notional: FiniteFloat = Field(gt=0)
    quantity: FiniteFloat = 1.0
    strike: FiniteFloat = Field(gt=0)
    option_maturity_years: FiniteFloat = Field(gt=0)
    swap_tenor_years: FiniteFloat = Field(gt=0)
    option_type: Literal["payer", "receiver"]
    payment_frequency_per_year: int = Field(default=2, ge=1, le=12)
    book: str = "Rates Derivatives"


InstrumentTerms = (
    EquityTerms
    | EquityFutureTerms
    | EuropeanOptionTerms
    | BondTerms
    | SwapTerms
    | FXForwardTerms
    | FXOptionTerms
    | InterestRateFutureTerms
    | CapFloorTerms
    | SwaptionTerms
)

# Wire/validation form; family is selected by the Literal ``type`` tag.
InstrumentTermsAdapter = TypeAdapter(
    Annotated[InstrumentTerms, Field(discriminator="type")]
)


def _equity_currency(position: EquityPosition | EquityFuturePosition | EuropeanOptionPosition) -> str:
    return getattr(position, "currency", None) or _EQUITY_SETTLEMENT_CURRENCY


def terms_from_position(position: Position) -> InstrumentTerms:
    """Project a compatibility Position DTO onto contractual terms only.

    Live observables already excluded by ``trade_cache_key`` (price, spot, vol,
    yield, market swap rate, quoted/forward/discount rates, duration) are not
    copied. Unknown families fail closed.
    """
    if isinstance(position, EquityPosition):
        return EquityTerms(
            type="equity",
            id=position.id,
            symbol=position.symbol,
            quantity=position.quantity,
            currency=_equity_currency(position),
            sector=position.sector,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, EquityFuturePosition):
        return EquityFutureTerms(
            type="equity_future",
            id=position.id,
            symbol=position.symbol,
            quantity=position.quantity,
            multiplier=position.multiplier,
            maturity_years=position.maturity_years,
            currency=_equity_currency(position),
            sector=position.sector,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, EuropeanOptionPosition):
        return EuropeanOptionTerms(
            type="european_option",
            id=position.id,
            symbol=position.symbol,
            quantity=position.quantity,
            strike=position.strike,
            maturity_years=position.maturity_years,
            option_type=position.option_type,
            currency=_equity_currency(position),
            sector=position.sector,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, BondPosition):
        return BondTerms(
            type="bond",
            id=position.id,
            issuer=position.issuer,
            face_value=position.face_value,
            quantity=position.quantity,
            maturity_years=position.maturity_years,
            currency=position.currency,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, SwapPosition):
        return SwapTerms(
            type="swap",
            id=position.id,
            currency=position.currency,
            notional=position.notional,
            maturity_years=position.maturity_years,
            fixed_rate=position.fixed_rate,
            pay_fixed=position.pay_fixed,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, FXForwardPosition):
        return FXForwardTerms(
            type="fx_forward",
            id=position.id,
            pair=position.pair,
            notional_base=position.notional_base,
            strike=position.strike,
            maturity_years=position.maturity_years,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, FXOptionPosition):
        return FXOptionTerms(
            type="fx_option",
            id=position.id,
            pair=position.pair,
            notional_base=position.notional_base,
            strike=position.strike,
            maturity_years=position.maturity_years,
            option_type=position.option_type,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, InterestRateFuturePosition):
        return InterestRateFutureTerms(
            type="ir_future",
            id=position.id,
            currency=position.currency,
            quantity=position.quantity,
            pv01=position.pv01,
            maturity_years=position.maturity_years,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, CapFloorPosition):
        return CapFloorTerms(
            type="cap_floor",
            id=position.id,
            currency=position.currency,
            notional=position.notional,
            quantity=position.quantity,
            strike=position.strike,
            maturity_years=position.maturity_years,
            option_type=position.option_type,
            payment_frequency_per_year=position.payment_frequency_per_year,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    if isinstance(position, SwaptionPosition):
        return SwaptionTerms(
            type="swaption",
            id=position.id,
            currency=position.currency,
            notional=position.notional,
            quantity=position.quantity,
            strike=position.strike,
            option_maturity_years=position.option_maturity_years,
            swap_tenor_years=position.swap_tenor_years,
            option_type=position.option_type,
            payment_frequency_per_year=position.payment_frequency_per_year,
            book=position.book,
            desk=position.desk,
            strategy=position.strategy,
        )
    raise TypeError(
        f"terms_from_position has no terms projection for {type(position).__name__}"
    )
