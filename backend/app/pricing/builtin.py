from __future__ import annotations

import math
from statistics import NormalDist

from app.domain.models import (
    BondPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    Position,
    SwapPosition,
    Valuation,
)
from app.interfaces.pricing import PricingEngine
from app.pricing.curve_rates import continuous_zero, discount_factor
from app.pricing.surface_vol import option_vol_from_snapshot

_N = NormalDist()
def _cdf(x: float) -> float: return _N.cdf(x)
def _pdf(x: float) -> float: return math.exp(-0.5*x*x)/math.sqrt(2*math.pi)


class BuiltinPricingEngine(PricingEngine):
    """Deterministic reference pricer used for tests and cross-validation.

    Bonds / swaps / IR futures revalue from ``MarketSnapshot.curves`` and
    ``key_rates`` when present (continuous zeros); otherwise fall back to
    scalar ``rates[ccy]`` and annual bond compounding.
    """

    def value(self, position: Position, market: MarketSnapshot | None = None) -> Valuation:
        if isinstance(position, EquityPosition):
            spot = market.equity_spots.get(position.symbol, position.price) if market else position.price
            return Valuation(position_id=position.id, market_value=position.quantity*spot, delta=position.quantity*spot)
        if isinstance(position, EquityFuturePosition):
            s = market.equity_spots.get(position.symbol, position.spot) if market else position.spot
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
        raise TypeError(f"Unsupported position: {type(position)!r}")

    def _bond(self, p: BondPosition, market: MarketSnapshot | None) -> Valuation:
        df = discount_factor(
            market, p.currency, p.maturity_years, fallback_yield=p.yield_rate
        )
        if df is not None:
            pv = p.face_value * p.quantity * df
        else:
            y = market.rates.get(p.currency, p.yield_rate) if market else p.yield_rate
            pv = p.face_value * p.quantity / ((1 + y) ** p.maturity_years)
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
        s = market.equity_spots.get(p.symbol,p.spot) if market else p.spot
        fallback = market.equity_vols.get(p.symbol, p.volatility) if market else p.volatility
        sigma = (
            option_vol_from_snapshot(
                market,
                name=p.symbol,
                maturity_years=p.maturity_years,
                strike=p.strike,
                spot=s,
                fallback=fallback,
            )
            if market
            else fallback
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
