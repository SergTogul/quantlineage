from __future__ import annotations

import math
from statistics import NormalDist

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
    EuropeanOptionPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    Position,
    SwapPosition,
    SwaptionPosition,
    Valuation,
)
from app.interfaces.pricing import PricingEngine
from app.market.demo_snapshot import MissingMarketDataError
from app.pricing.curve_rates import (
    discount_factor,
    required_continuous_zero,
    required_ir_future_quote,
)
from app.risk.historical import require_explicit_market
from app.pricing.surface_vol import (
    required_equity_option_vol,
    required_fx_option_vol,
    required_ir_option_vol,
)

_N = NormalDist()
def _cdf(x: float) -> float: return _N.cdf(x)
def _pdf(x: float) -> float: return math.exp(-0.5*x*x)/math.sqrt(2*math.pi)


def _required_equity_spot(market: MarketSnapshot, symbol: str) -> float:
    try:
        return market.equity_spots[symbol]
    except KeyError:
        raise MissingMarketDataError(f"equity_spots[{symbol}]") from None


def _equity_settlement_currency(position) -> str:
    currency = getattr(position, "currency", None)
    return str(currency) if currency else "USD"


def _required_settlement_rate(market: MarketSnapshot, currency: str) -> float:
    try:
        return market.rates[currency]
    except KeyError:
        raise MissingMarketDataError(f"rates[{currency}]") from None


def _required_dividend_yield(market: MarketSnapshot, symbol: str) -> float:
    try:
        return market.dividend_yields[symbol]
    except KeyError:
        raise MissingMarketDataError(f"dividend_yields[{symbol}]") from None


def _required_fx_spot(market: MarketSnapshot, pair: str) -> float:
    try:
        return market.fx_spots[pair]
    except KeyError:
        raise MissingMarketDataError(f"fx_spots[{pair}]") from None


def _economics_from_terms(position: Position, terms: InstrumentTerms) -> dict:
    """Copy contractual terms onto Position field names (marks stay off terms)."""
    fields = type(position).model_fields
    return {name: value for name, value in terms.model_dump().items() if name in fields}


def _snapshot_marks_from_terms(terms: InstrumentTerms, market: MarketSnapshot) -> dict:
    """Resolve live marks from the explicit snapshot using terms keys only."""
    if isinstance(terms, EquityTerms):
        return {"price": _required_equity_spot(market, terms.symbol)}
    if isinstance(terms, EquityFutureTerms):
        return {
            "spot": _required_equity_spot(market, terms.symbol),
            "risk_free_rate": _required_settlement_rate(market, terms.currency),
            "dividend_yield": _required_dividend_yield(market, terms.symbol),
        }
    if isinstance(terms, EuropeanOptionTerms):
        spot = _required_equity_spot(market, terms.symbol)
        return {
            "spot": spot,
            "volatility": required_equity_option_vol(
                market,
                name=terms.symbol,
                maturity_years=terms.maturity_years,
                strike=terms.strike,
                spot=spot,
            ),
            "risk_free_rate": _required_settlement_rate(market, terms.currency),
            "dividend_yield": _required_dividend_yield(market, terms.symbol),
        }
    if isinstance(terms, BondTerms):
        return {
            "yield_rate": required_continuous_zero(
                market,
                terms.currency,
                terms.maturity_years,
            )
        }
    if isinstance(terms, SwapTerms):
        return {
            "market_swap_rate": required_continuous_zero(
                market,
                terms.currency,
                terms.maturity_years,
            )
        }
    if isinstance(terms, InterestRateFutureTerms):
        return {
            "forward_rate": required_continuous_zero(
                market,
                terms.currency,
                terms.maturity_years,
                prefer_projection=True,
            ),
            "quoted_rate": required_ir_future_quote(market, terms.currency),
        }
    if isinstance(terms, CapFloorTerms):
        forward = required_continuous_zero(
            market,
            terms.currency,
            terms.maturity_years,
            prefer_projection=True,
        )
        return {
            "forward_rate": forward,
            "discount_rate": required_continuous_zero(
                market,
                terms.currency,
                terms.maturity_years,
            ),
            "volatility": required_ir_option_vol(
                market,
                name=terms.currency,
                maturity_years=terms.maturity_years,
                strike=terms.strike,
                forward=forward,
            ),
        }
    if isinstance(terms, SwaptionTerms):
        forward = required_continuous_zero(
            market,
            terms.currency,
            terms.option_maturity_years,
            prefer_projection=True,
        )
        return {
            "forward_swap_rate": forward,
            "discount_rate": required_continuous_zero(
                market,
                terms.currency,
                terms.option_maturity_years + terms.swap_tenor_years,
            ),
            "volatility": required_ir_option_vol(
                market,
                name=terms.currency,
                maturity_years=terms.option_maturity_years,
                strike=terms.strike,
                forward=forward,
            ),
        }
    if isinstance(terms, FXForwardTerms):
        return {
            "spot": _required_fx_spot(market, terms.pair),
            "domestic_rate": _required_settlement_rate(market, terms.pair[-3:]),
            "foreign_rate": _required_settlement_rate(market, terms.pair[:3]),
        }
    if isinstance(terms, FXOptionTerms):
        spot = _required_fx_spot(market, terms.pair)
        return {
            "spot": spot,
            "volatility": required_fx_option_vol(
                market,
                name=terms.pair,
                maturity_years=terms.maturity_years,
                strike=terms.strike,
                spot=spot,
            ),
            "domestic_rate": _required_settlement_rate(market, terms.pair[-3:]),
            "foreign_rate": _required_settlement_rate(market, terms.pair[:3]),
        }
    return {}


def _act365_fixed_years(maturity_years: float) -> float:
    """Actual/365 Fixed year fraction matching QuantLib ZeroCouponBond.

    Mirrors ``QuantLibPricingEngine._maturity_date``: NullCalendar advance of
    ``max(1, round(T * 365))`` days, then ``days / 365`` (Actual365Fixed).
    """
    return max(1, round(float(maturity_years) * 365.0)) / 365.0


class BuiltinPricingEngine(PricingEngine):
    """Deterministic reference pricer used for tests and cross-validation.

    Bonds / swaps / IR futures revalue from ``MarketSnapshot.curves`` and
    ``key_rates`` when present (continuous zeros). Scalar bond fallback (no
    curve) uses continuous compounding on Actual365Fixed year fraction —
    same convention as QuantLib ``FlatForward`` + ``ZeroCouponBond``.
    """

    def value(self, position: Position, market: MarketSnapshot | None = None) -> Valuation:
        market = require_explicit_market(market)
        try:
            terms = terms_from_position(position)
        except TypeError:
            raise TypeError(f"Unsupported position: {type(position)!r}") from None

        # Snapshot is the sole mark authority; leftover DTO marks are ignored.
        updates = _economics_from_terms(position, terms)
        updates.update(_snapshot_marks_from_terms(terms, market))
        working = position.model_copy(update=updates)

        if isinstance(terms, EquityTerms):
            return Valuation(
                position_id=terms.id,
                market_value=terms.quantity * working.price,
                delta=terms.quantity * working.price,
            )
        if isinstance(terms, EquityFutureTerms):
            s = _required_equity_spot(market, terms.symbol)
            r = _required_settlement_rate(market, terms.currency)
            q = _required_dividend_yield(market, terms.symbol)
            f = s * math.exp((r - q) * terms.maturity_years)
            mv = terms.quantity * terms.multiplier * f
            return Valuation(
                position_id=terms.id,
                market_value=mv,
                delta=mv,
                dv01=mv * terms.maturity_years * 0.0001,
            )
        if isinstance(terms, EuropeanOptionTerms):
            return self._equity_option(working, market)
        if isinstance(terms, BondTerms):
            return self._bond(working, market)
        if isinstance(terms, SwapTerms):
            return self._swap(working, market)
        if isinstance(terms, FXForwardTerms):
            s = _required_fx_spot(market, terms.pair)
            rd = _required_settlement_rate(market, terms.pair[-3:])
            rf = _required_settlement_rate(market, terms.pair[:3])
            forward = s * math.exp((rd - rf) * terms.maturity_years)
            pv = terms.notional_base * (forward - terms.strike) * math.exp(-rd * terms.maturity_years)
            return Valuation(
                position_id=terms.id,
                market_value=pv,
                fx_delta=terms.notional_base * s,
            )
        if isinstance(terms, FXOptionTerms):
            return self._fx_option(working, market)
        if isinstance(terms, InterestRateFutureTerms):
            return self._ir_future(working, market)
        if isinstance(terms, CapFloorTerms):
            return self._cap_floor(working, market)
        if isinstance(terms, SwaptionTerms):
            return self._swaption(working, market)
        raise TypeError(f"Unsupported position: {type(working)!r}")

    def _bond(self, p: BondPosition, market: MarketSnapshot) -> Valuation:
        df = discount_factor(
            market, p.currency, p.maturity_years, fallback_yield=p.yield_rate
        )
        if df is not None:
            # Curve path: continuous DF at domain ``maturity_years`` (pillar T).
            pv = p.face_value * p.quantity * df
        else:
            # Scalar path: continuous Actual365Fixed (QL ZeroCouponBond parity).
            y = required_continuous_zero(market, p.currency, p.maturity_years)
            t = _act365_fixed_years(p.maturity_years)
            pv = p.face_value * p.quantity * math.exp(-y * t)
        return Valuation(position_id=p.id, market_value=pv, dv01=-p.duration * pv * 0.0001)

    def _swap(self, p: SwapPosition, market: MarketSnapshot) -> Valuation:
        # pay_fixed=True → standard payer: PV rises when the market swap rate rises.
        # Curve / key-rate zeros at maturity mark the floating/par rate when attached.
        m = required_continuous_zero(market, p.currency, p.maturity_years)
        sign = 1.0 if p.pay_fixed else -1.0
        annuity = p.notional * p.duration
        pv = sign * (m - p.fixed_rate) * annuity
        return Valuation(position_id=p.id, market_value=pv, dv01=sign * annuity * 0.0001)

    def _equity_option(self, p: EuropeanOptionPosition, market: MarketSnapshot) -> Valuation:
        s = _required_equity_spot(market, p.symbol)
        sigma = required_equity_option_vol(
            market,
            name=p.symbol,
            maturity_years=p.maturity_years,
            strike=p.strike,
            spot=s,
        )
        currency = _equity_settlement_currency(p)
        r = _required_settlement_rate(market, currency)
        q = _required_dividend_yield(market, p.symbol)
        k,t = p.strike,p.maturity_years
        sqrt_t=math.sqrt(t); d1=(math.log(s/k)+(r-q+0.5*sigma*sigma)*t)/(sigma*sqrt_t); d2=d1-sigma*sqrt_t
        dr,dq=math.exp(-r*t),math.exp(-q*t)
        if p.option_type=="call": price=s*dq*_cdf(d1)-k*dr*_cdf(d2); delta=dq*_cdf(d1)
        else: price=k*dr*_cdf(-d2)-s*dq*_cdf(-d1); delta=dq*(_cdf(d1)-1)
        gamma=dq*_pdf(d1)/(s*sigma*sqrt_t); vega=s*dq*_pdf(d1)*sqrt_t
        return Valuation(position_id=p.id,market_value=p.quantity*price,delta=p.quantity*delta*s,gamma=p.quantity*gamma*s*s,vega=p.quantity*vega*0.01)

    def _fx_option(self, p: FXOptionPosition, market: MarketSnapshot) -> Valuation:
        s = _required_fx_spot(market, p.pair)
        sigma = required_fx_option_vol(
            market,
            name=p.pair,
            maturity_years=p.maturity_years,
            strike=p.strike,
            spot=s,
        )
        rd = _required_settlement_rate(market, p.pair[-3:])
        rf = _required_settlement_rate(market, p.pair[:3])
        t,k=p.maturity_years,p.strike; sqrt_t=math.sqrt(t)
        d1=(math.log(s/k)+(rd-rf+0.5*sigma*sigma)*t)/(sigma*sqrt_t); d2=d1-sigma*sqrt_t
        if p.option_type=="call": unit=s*math.exp(-rf*t)*_cdf(d1)-k*math.exp(-rd*t)*_cdf(d2); d=math.exp(-rf*t)*_cdf(d1)
        else: unit=k*math.exp(-rd*t)*_cdf(-d2)-s*math.exp(-rf*t)*_cdf(-d1); d=math.exp(-rf*t)*(_cdf(d1)-1)
        gamma=math.exp(-rf*t)*_pdf(d1)/(s*sigma*sqrt_t); vega=s*math.exp(-rf*t)*_pdf(d1)*sqrt_t
        return Valuation(position_id=p.id,market_value=p.notional_base*unit,fx_delta=p.notional_base*d*s,gamma=p.notional_base*gamma*s*s,vega=p.notional_base*vega*0.01)

    def _ir_future(self, p: InterestRateFuturePosition, market: MarketSnapshot) -> Valuation:
        # Long STIR future: profits when the forward rate falls vs the quoted futures rate.
        # Units: pv01 is $ per contract per 1bp; rates are decimals.
        # Prefer projection curve / key rates at maturity when attached.
        fwd = required_continuous_zero(
            market,
            p.currency,
            p.maturity_years,
            prefer_projection=True,
        )
        quoted = required_ir_future_quote(market, p.currency)
        mv = p.quantity * p.pv01 * (quoted - fwd) * 10000.0
        return Valuation(position_id=p.id, market_value=mv, dv01=-p.quantity * p.pv01)

    def _cap_floor_components(
        self,
        p: CapFloorPosition,
        market: MarketSnapshot,
        *,
        rate_shift: float = 0.0,
        vol_shift: float = 0.0,
    ) -> tuple[float, float]:
        periods = max(1, round(p.maturity_years * p.payment_frequency_per_year))
        accrual = p.maturity_years / periods
        sigma = max(
            1e-8,
            required_ir_option_vol(
                market,
                name=p.currency,
                maturity_years=p.maturity_years,
                strike=p.strike,
                forward=p.forward_rate,
            )
            + vol_shift,
        )
        unit_pv = 0.0
        unit_vega = 0.0

        for i in range(1, periods + 1):
            payment_time = i * accrual
            # Spot-start approximation: first reset/exercise is clamped to one
            # calendar day, matching the adapter's existing short-option policy.
            option_expiry = max(1.0 / 365.0, payment_time - accrual)
            forward = required_continuous_zero(
                market,
                p.currency,
                option_expiry,
                prefer_projection=True,
            ) + rate_shift
            discount_rate = required_continuous_zero(
                market,
                p.currency,
                payment_time,
            ) + rate_shift
            if forward <= 0.0:
                raise ValueError("Black cap/floor pricing requires a positive forward rate")
            df = math.exp(-discount_rate * payment_time)
            sqrt_t = math.sqrt(option_expiry)
            d1 = (math.log(forward / p.strike) + 0.5 * sigma * sigma * option_expiry) / (
                sigma * sqrt_t
            )
            d2 = d1 - sigma * sqrt_t
            if p.option_type == "cap":
                optionlet = forward * _cdf(d1) - p.strike * _cdf(d2)
            else:
                optionlet = p.strike * _cdf(-d2) - forward * _cdf(-d1)
            unit_pv += df * accrual * optionlet
            unit_vega += df * accrual * forward * _pdf(d1) * sqrt_t

        scale = p.quantity * p.notional
        return scale * unit_pv, scale * unit_vega * 0.01

    def _cap_floor(self, p: CapFloorPosition, market: MarketSnapshot) -> Valuation:
        pv, vega = self._cap_floor_components(p, market)
        bumped, _ = self._cap_floor_components(p, market, rate_shift=0.0001)
        return Valuation(position_id=p.id, market_value=pv, vega=vega, dv01=bumped - pv)

    def _swaption_components(
        self,
        p: SwaptionPosition,
        market: MarketSnapshot,
        *,
        rate_shift: float = 0.0,
        vol_shift: float = 0.0,
    ) -> tuple[float, float]:
        periods = max(1, round(p.swap_tenor_years * p.payment_frequency_per_year))
        accrual = p.swap_tenor_years / periods
        sigma = max(
            1e-8,
            required_ir_option_vol(
                market,
                name=p.currency,
                maturity_years=p.option_maturity_years,
                strike=p.strike,
                forward=p.forward_swap_rate,
            )
            + vol_shift,
        )
        forward = (
            required_continuous_zero(
                market,
                p.currency,
                p.option_maturity_years,
                prefer_projection=True,
            )
            + rate_shift
        )
        discount_rate = (
            required_continuous_zero(
                market,
                p.currency,
                p.option_maturity_years + p.swap_tenor_years,
            )
            + rate_shift
        )
        if forward <= 0.0:
            raise ValueError("Black swaption pricing requires a positive forward swap rate")

        annuity = sum(
            accrual * math.exp(-discount_rate * (p.option_maturity_years + i * accrual))
            for i in range(1, periods + 1)
        )
        expiry = p.option_maturity_years
        sqrt_t = math.sqrt(expiry)
        d1 = (math.log(forward / p.strike) + 0.5 * sigma * sigma * expiry) / (
            sigma * sqrt_t
        )
        d2 = d1 - sigma * sqrt_t
        if p.option_type == "payer":
            unit = forward * _cdf(d1) - p.strike * _cdf(d2)
        else:
            unit = p.strike * _cdf(-d2) - forward * _cdf(-d1)

        scale = p.quantity * p.notional
        pv = scale * annuity * unit
        vega = scale * annuity * forward * _pdf(d1) * sqrt_t * 0.01
        return pv, vega

    def _swaption(self, p: SwaptionPosition, market: MarketSnapshot) -> Valuation:
        pv, vega = self._swaption_components(p, market)
        bumped, _ = self._swaption_components(p, market, rate_shift=0.0001)
        return Valuation(position_id=p.id, market_value=pv, vega=vega, dv01=bumped - pv)
