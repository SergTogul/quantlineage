from __future__ import annotations

import math
from statistics import NormalDist

from app.domain.models import (
    BondPosition,
    CapFloorPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
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
from app.pricing.curve_rates import continuous_zero, discount_factor
from app.pricing.surface_vol import option_vol_from_snapshot, required_equity_option_vol

_N = NormalDist()
def _cdf(x: float) -> float: return _N.cdf(x)
def _pdf(x: float) -> float: return math.exp(-0.5*x*x)/math.sqrt(2*math.pi)


def _required_equity_spot(market: MarketSnapshot, symbol: str) -> float:
    try:
        return market.equity_spots[symbol]
    except KeyError:
        raise MissingMarketDataError(f"equity_spots[{symbol}]") from None


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
        if isinstance(position, EquityPosition):
            spot = (
                position.price
                if market is None
                else _required_equity_spot(market, position.symbol)
            )
            return Valuation(position_id=position.id, market_value=position.quantity*spot, delta=position.quantity*spot)
        if isinstance(position, EquityFuturePosition):
            s = (
                position.spot
                if market is None
                else _required_equity_spot(market, position.symbol)
            )
            r = market.rates.get("USD", position.risk_free_rate) if market else position.risk_free_rate
            f = s * math.exp((r-position.dividend_yield)*position.maturity_years)
            mv = position.quantity*position.multiplier*f
            return Valuation(position_id=position.id, market_value=mv, delta=mv, dv01=mv*position.maturity_years*0.0001)
        if isinstance(position, EuropeanOptionPosition):
            return self._equity_option(position, market)
        if isinstance(position, BondPosition):
            return self._bond(position, market)
        if isinstance(position, SwapPosition):
            return self._swap(position, market)
        if isinstance(position, FXForwardPosition):
            s = market.fx_spots.get(position.pair, position.spot) if market else position.spot
            rd = market.rates.get(position.pair[-3:], position.domestic_rate) if market else position.domestic_rate
            rf = market.rates.get(position.pair[:3], position.foreign_rate) if market else position.foreign_rate
            forward = s*math.exp((rd-rf)*position.maturity_years)
            pv = position.notional_base*(forward-position.strike)*math.exp(-rd*position.maturity_years)
            return Valuation(position_id=position.id, market_value=pv, fx_delta=position.notional_base*s)
        if isinstance(position, FXOptionPosition):
            return self._fx_option(position, market)
        if isinstance(position, InterestRateFuturePosition):
            return self._ir_future(position, market)
        if isinstance(position, CapFloorPosition):
            return self._cap_floor(position, market)
        if isinstance(position, SwaptionPosition):
            return self._swaption(position, market)
        raise TypeError(f"Unsupported position: {type(position)!r}")

    def _bond(self, p: BondPosition, market: MarketSnapshot | None) -> Valuation:
        df = discount_factor(
            market, p.currency, p.maturity_years, fallback_yield=p.yield_rate
        )
        if df is not None:
            # Curve path: continuous DF at domain ``maturity_years`` (pillar T).
            pv = p.face_value * p.quantity * df
        else:
            # Scalar path: continuous Actual365Fixed (QL ZeroCouponBond parity).
            y = market.rates.get(p.currency, p.yield_rate) if market else p.yield_rate
            t = _act365_fixed_years(p.maturity_years)
            pv = p.face_value * p.quantity * math.exp(-y * t)
        return Valuation(position_id=p.id, market_value=pv, dv01=-p.duration * pv * 0.0001)

    def _swap(self, p: SwapPosition, market: MarketSnapshot | None) -> Valuation:
        # pay_fixed=True → standard payer: PV rises when the market swap rate rises.
        # Curve / key-rate zeros at maturity mark the floating/par rate when attached.
        m = continuous_zero(
            market,
            p.currency,
            p.maturity_years,
            fallback=p.market_swap_rate,
        )
        sign = 1.0 if p.pay_fixed else -1.0
        annuity = p.notional * p.duration
        pv = sign * (m - p.fixed_rate) * annuity
        return Valuation(position_id=p.id, market_value=pv, dv01=sign * annuity * 0.0001)

    def _equity_option(self, p: EuropeanOptionPosition, market: MarketSnapshot | None) -> Valuation:
        s = p.spot if market is None else _required_equity_spot(market, p.symbol)
        sigma = (
            p.volatility
            if market is None
            else required_equity_option_vol(
                market,
                name=p.symbol,
                maturity_years=p.maturity_years,
                strike=p.strike,
                spot=s,
            )
        )
        r = market.rates.get("USD",p.risk_free_rate) if market else p.risk_free_rate
        k,t,q = p.strike,p.maturity_years,p.dividend_yield
        sqrt_t=math.sqrt(t); d1=(math.log(s/k)+(r-q+0.5*sigma*sigma)*t)/(sigma*sqrt_t); d2=d1-sigma*sqrt_t
        dr,dq=math.exp(-r*t),math.exp(-q*t)
        if p.option_type=="call": price=s*dq*_cdf(d1)-k*dr*_cdf(d2); delta=dq*_cdf(d1)
        else: price=k*dr*_cdf(-d2)-s*dq*_cdf(-d1); delta=dq*(_cdf(d1)-1)
        gamma=dq*_pdf(d1)/(s*sigma*sqrt_t); vega=s*dq*_pdf(d1)*sqrt_t
        return Valuation(position_id=p.id,market_value=p.quantity*price,delta=p.quantity*delta*s,gamma=p.quantity*gamma*s*s,vega=p.quantity*vega*0.01)

    def _fx_option(self, p: FXOptionPosition, market: MarketSnapshot | None) -> Valuation:
        s = market.fx_spots.get(p.pair,p.spot) if market else p.spot
        fallback = market.fx_vols.get(p.pair, p.volatility) if market else p.volatility
        sigma = (
            option_vol_from_snapshot(
                market,
                name=p.pair,
                maturity_years=p.maturity_years,
                strike=p.strike,
                spot=s,
                fallback=fallback,
            )
            if market
            else fallback
        )
        rd = market.rates.get(p.pair[-3:],p.domestic_rate) if market else p.domestic_rate
        rf = market.rates.get(p.pair[:3],p.foreign_rate) if market else p.foreign_rate
        t,k=p.maturity_years,p.strike; sqrt_t=math.sqrt(t)
        d1=(math.log(s/k)+(rd-rf+0.5*sigma*sigma)*t)/(sigma*sqrt_t); d2=d1-sigma*sqrt_t
        if p.option_type=="call": unit=s*math.exp(-rf*t)*_cdf(d1)-k*math.exp(-rd*t)*_cdf(d2); d=math.exp(-rf*t)*_cdf(d1)
        else: unit=k*math.exp(-rd*t)*_cdf(-d2)-s*math.exp(-rf*t)*_cdf(-d1); d=math.exp(-rf*t)*(_cdf(d1)-1)
        gamma=math.exp(-rf*t)*_pdf(d1)/(s*sigma*sqrt_t); vega=s*math.exp(-rf*t)*_pdf(d1)*sqrt_t
        return Valuation(position_id=p.id,market_value=p.notional_base*unit,fx_delta=p.notional_base*d*s,gamma=p.notional_base*gamma*s*s,vega=p.notional_base*vega*0.01)

    def _ir_future(self, p: InterestRateFuturePosition, market: MarketSnapshot | None) -> Valuation:
        # Long STIR future: profits when the forward rate falls vs the quoted futures rate.
        # Units: pv01 is $ per contract per 1bp; rates are decimals.
        # Prefer projection curve / key rates at maturity when attached.
        fwd = continuous_zero(
            market,
            p.currency,
            p.maturity_years,
            fallback=p.forward_rate,
            prefer_projection=True,
        )
        mv = p.quantity * p.pv01 * (p.quoted_rate - fwd) * 10000.0
        return Valuation(position_id=p.id, market_value=mv, dv01=-p.quantity * p.pv01)

    def _cap_floor_components(
        self,
        p: CapFloorPosition,
        market: MarketSnapshot | None,
        *,
        rate_shift: float = 0.0,
        vol_shift: float = 0.0,
    ) -> tuple[float, float]:
        periods = max(1, round(p.maturity_years * p.payment_frequency_per_year))
        accrual = p.maturity_years / periods
        sigma = max(1e-8, p.volatility + vol_shift)
        unit_pv = 0.0
        unit_vega = 0.0

        for i in range(1, periods + 1):
            payment_time = i * accrual
            # Spot-start approximation: first reset/exercise is clamped to one
            # calendar day, matching the adapter's existing short-option policy.
            option_expiry = max(1.0 / 365.0, payment_time - accrual)
            forward = continuous_zero(
                market,
                p.currency,
                option_expiry,
                fallback=p.forward_rate,
                prefer_projection=True,
            ) + rate_shift
            discount_rate = continuous_zero(
                market,
                p.currency,
                payment_time,
                fallback=p.discount_rate,
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

    def _cap_floor(self, p: CapFloorPosition, market: MarketSnapshot | None) -> Valuation:
        pv, vega = self._cap_floor_components(p, market)
        bumped, _ = self._cap_floor_components(p, market, rate_shift=0.0001)
        return Valuation(position_id=p.id, market_value=pv, vega=vega, dv01=bumped - pv)

    def _swaption_components(
        self,
        p: SwaptionPosition,
        market: MarketSnapshot | None,
        *,
        rate_shift: float = 0.0,
        vol_shift: float = 0.0,
    ) -> tuple[float, float]:
        periods = max(1, round(p.swap_tenor_years * p.payment_frequency_per_year))
        accrual = p.swap_tenor_years / periods
        sigma = max(1e-8, p.volatility + vol_shift)
        forward = (
            continuous_zero(
                market,
                p.currency,
                p.option_maturity_years,
                fallback=p.forward_swap_rate,
                prefer_projection=True,
            )
            + rate_shift
        )
        discount_rate = (
            continuous_zero(
                market,
                p.currency,
                p.option_maturity_years + p.swap_tenor_years,
                fallback=p.discount_rate,
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

    def _swaption(self, p: SwaptionPosition, market: MarketSnapshot | None) -> Valuation:
        pv, vega = self._swaption_components(p, market)
        bumped, _ = self._swaption_components(p, market, rate_shift=0.0001)
        return Valuation(position_id=p.id, market_value=pv, vega=vega, dv01=bumped - pv)
