from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from threading import RLock

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
    StressScenario,
    SwapPosition,
    Valuation,
)
from app.interfaces.pricing import PricingEngine
from app.pricing.curve_rates import continuous_zero, has_curve_or_key_rates, select_yield_curve
from app.pricing.surface_vol import option_vol_from_snapshot

try:
    import QuantLib as ql
except ImportError as exc:  # pragma: no cover - exercised only when dependency is absent
    ql = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class QuantLibUnavailableError(RuntimeError):
    pass


class QuantLibPricingEngine(PricingEngine):
    """QuantLib-backed valuation adapter.

    QuantLib's evaluation date is process-global.  The adapter owns that state and
    serializes pricing calls so callers never need to know about QuantLib globals.
    For high-throughput production use, run multiple worker processes or replace
    this adapter with a native C++ pricing service.
    """

    def __init__(self, evaluation_date: date | None = None):
        if ql is None:
            raise QuantLibUnavailableError(
                "QuantLib is not installed. Install backend requirements or run "
                "`pip install QuantLib`."
            ) from _IMPORT_ERROR
        self.evaluation_date = evaluation_date or date.today()
        self._lock = RLock()

    @contextmanager
    def _session(self):
        with self._lock:
            previous = ql.Settings.instance().evaluationDate
            ql.Settings.instance().evaluationDate = self._ql_date(self.evaluation_date)
            try:
                yield
            finally:
                ql.Settings.instance().evaluationDate = previous

    @staticmethod
    def _ql_date(value: date):
        return ql.Date(value.day, value.month, value.year)

    def _maturity_date(self, years: float):
        # Fractional years are intentionally represented as calendar days in this
        # MVP domain model.  A later trade-capture module can replace this with
        # explicit maturity dates and calendars without changing PricingEngine.
        # T→0 policy: domain maturities below ~1/365 clamp to 1 calendar day so
        # QuantLib always sees a positive exercise tenor (do not change silently).
        days = max(1, round(years * 365.0))
        return self._ql_date(self.evaluation_date + timedelta(days=days))

    def value(self, position: Position, market: MarketSnapshot | None = None) -> Valuation:
        if market is not None:
            # Convert immutable market snapshot values into the trade-local marks QuantLib consumes.
            updates = {}
            if isinstance(position, EquityPosition):
                updates["price"] = market.equity_spots.get(position.symbol, position.price)
            elif isinstance(position, EquityFuturePosition):
                updates = {
                    "spot": market.equity_spots.get(position.symbol, position.spot),
                    "risk_free_rate": market.rates.get("USD", position.risk_free_rate),
                }
            elif isinstance(position, EuropeanOptionPosition):
                spot = market.equity_spots.get(position.symbol, position.spot)
                fallback = market.equity_vols.get(position.symbol, position.volatility)
                updates = {
                    "spot": spot,
                    "volatility": option_vol_from_snapshot(
                        market,
                        name=position.symbol,
                        maturity_years=position.maturity_years,
                        strike=position.strike,
                        spot=spot,
                        fallback=fallback,
                    ),
                    "risk_free_rate": market.rates.get("USD", position.risk_free_rate),
                }
            elif isinstance(position, BondPosition):
                updates["yield_rate"] = continuous_zero(
                    market,
                    position.currency,
                    position.maturity_years,
                    fallback=position.yield_rate,
                )
            elif isinstance(position, SwapPosition):
                updates["market_swap_rate"] = continuous_zero(
                    market,
                    position.currency,
                    position.maturity_years,
                    fallback=position.market_swap_rate,
                )
            elif isinstance(position, InterestRateFuturePosition):
                updates["forward_rate"] = continuous_zero(
                    market,
                    position.currency,
                    position.maturity_years,
                    fallback=position.forward_rate,
                    prefer_projection=True,
                )
            elif isinstance(position, FXForwardPosition):
                updates = {
                    "spot": market.fx_spots.get(position.pair, position.spot),
                    "domestic_rate": market.rates.get(position.pair[-3:], position.domestic_rate),
                    "foreign_rate": market.rates.get(position.pair[:3], position.foreign_rate),
                }
            elif isinstance(position, FXOptionPosition):
                spot = market.fx_spots.get(position.pair, position.spot)
                fallback = market.fx_vols.get(position.pair, position.volatility)
                updates = {
                    "spot": spot,
                    "volatility": option_vol_from_snapshot(
                        market,
                        name=position.pair,
                        maturity_years=position.maturity_years,
                        strike=position.strike,
                        spot=spot,
                        fallback=fallback,
                    ),
                    "domestic_rate": market.rates.get(position.pair[-3:], position.domestic_rate),
                    "foreign_rate": market.rates.get(position.pair[:3], position.foreign_rate),
                }
            if updates:
                position = position.model_copy(update=updates)
        with self._session():
            if isinstance(position, EquityPosition):
                return Valuation(
                    position_id=position.id,
                    market_value=position.quantity * position.price,
                    delta=position.quantity * position.price,
                )
            if isinstance(position, EquityFuturePosition):
                return self._equity_future(position)
            if isinstance(position, EuropeanOptionPosition):
                return self._option(position)
            if isinstance(position, BondPosition):
                return self._bond(position, market)
            if isinstance(position, SwapPosition):
                return self._swap(position, market)
            if isinstance(position, InterestRateFuturePosition):
                return self._ir_future(position)
            if isinstance(position, FXForwardPosition):
                return self._fx_forward(position)
            if isinstance(position, FXOptionPosition):
                return self._fx_option(position)
        # Instruments not yet covered by native QuantLib adapter use the reference pricer.
        from app.pricing.builtin import BuiltinPricingEngine
        return BuiltinPricingEngine().value(position, market)

    def _flat_curve(self, rate: float):
        today = self._ql_date(self.evaluation_date)
        return ql.YieldTermStructureHandle(
            ql.FlatForward(today, rate, ql.Actual365Fixed(), ql.Continuous)
        )

    def _curve_handle(self, market: MarketSnapshot | None, currency: str, flat_rate: float):
        """Build a QL handle from snapshot curves/key_rates, else flat continuous."""
        if market is not None and has_curve_or_key_rates(market, currency):
            yc = select_yield_curve(market, currency)
            if yc is not None:
                return self._zero_curve_handle(yc)
        return self._flat_curve(flat_rate)

    def _zero_curve_handle(self, yc):
        """Piecewise-linear continuous zero curve (QuantLib types stay inside adapter)."""
        today = self._ql_date(self.evaluation_date)
        dates = [today]
        rates = [float(yc.nodes[0].zero_rate)]
        for node in yc.nodes:
            d = self._maturity_date(node.years)
            if d <= dates[-1]:
                d = dates[-1] + 1
            dates.append(d)
            rates.append(float(node.zero_rate))
        curve = ql.ZeroCurve(
            dates,
            rates,
            ql.Actual365Fixed(),
            ql.NullCalendar(),
            ql.Linear(),
            ql.Continuous,
            ql.Annual,
        )
        curve.enableExtrapolation()
        return ql.YieldTermStructureHandle(curve)

    def _option(self, p: EuropeanOptionPosition) -> Valuation:
        spot = ql.QuoteHandle(ql.SimpleQuote(p.spot))
        risk_free = self._flat_curve(p.risk_free_rate)
        dividend = self._flat_curve(p.dividend_yield)
        vol = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(
                self._ql_date(self.evaluation_date),
                ql.NullCalendar(),
                p.volatility,
                ql.Actual365Fixed(),
            )
        )
        process = ql.BlackScholesMertonProcess(spot, dividend, risk_free, vol)
        payoff = ql.PlainVanillaPayoff(
            ql.Option.Call if p.option_type == "call" else ql.Option.Put,
            p.strike,
        )
        instrument = ql.VanillaOption(
            payoff,
            ql.EuropeanExercise(self._maturity_date(p.maturity_years)),
        )
        instrument.setPricingEngine(ql.AnalyticEuropeanEngine(process))

        unit_price = instrument.NPV()
        unit_delta = instrument.delta()
        unit_gamma = instrument.gamma()
        unit_vega = instrument.vega()

        return Valuation(
            position_id=p.id,
            market_value=p.quantity * unit_price,
            delta=p.quantity * unit_delta * p.spot,
            gamma=p.quantity * unit_gamma * p.spot * p.spot,
            # QuantLib vega is dPV / d(vol=1.00), so convert to a 1-vol-point exposure.
            vega=p.quantity * unit_vega * 0.01,
        )

    def _bond_npv(self, p: BondPosition, yield_rate: float, curve_handle=None) -> float:
        settlement_days = 0
        calendar = ql.NullCalendar()
        bond = ql.ZeroCouponBond(
            settlement_days,
            calendar,
            p.face_value,
            self._maturity_date(p.maturity_years),
            ql.Unadjusted,
            100.0,
            self._ql_date(self.evaluation_date),
        )
        handle = curve_handle if curve_handle is not None else self._flat_curve(yield_rate)
        bond.setPricingEngine(ql.DiscountingBondEngine(handle))
        return p.quantity * bond.NPV()

    def _bond(self, p: BondPosition, market: MarketSnapshot | None = None) -> Valuation:
        curve = self._curve_handle(market, p.currency, p.yield_rate)
        pv = self._bond_npv(p, p.yield_rate, curve)
        # Analytic 1bp parallel on the trade yield for DV01 reporting
        bumped = self._bond_npv(p, p.yield_rate + 0.0001)
        return Valuation(position_id=p.id, market_value=pv, dv01=bumped - pv)


    def _seed_ibor_fixings(self, index, float_schedule, rate: float) -> None:
        eval_dt = self._ql_date(self.evaluation_date)
        for i in range(len(float_schedule) - 1):
            fixing_date = index.fixingDate(float_schedule[i])
            if fixing_date <= eval_dt:
                index.addFixing(fixing_date, rate, True)

    def _swap_npv(self, p: SwapPosition, market_rate: float, curve_handle=None) -> float:
        start = self._ql_date(self.evaluation_date)
        maturity = self._maturity_date(p.maturity_years)
        calendar = ql.NullCalendar()

        fixed_schedule = ql.Schedule(
            start,
            maturity,
            ql.Period(ql.Annual),
            calendar,
            ql.Unadjusted,
            ql.Unadjusted,
            ql.DateGeneration.Forward,
            False,
        )
        float_schedule = ql.Schedule(
            start,
            maturity,
            ql.Period(ql.Semiannual),
            calendar,
            ql.Unadjusted,
            ql.Unadjusted,
            ql.DateGeneration.Forward,
            False,
        )
        curve = curve_handle if curve_handle is not None else self._flat_curve(market_rate)
        index = ql.USDLibor(ql.Period(6, ql.Months), curve)
        self._seed_ibor_fixings(index, float_schedule, market_rate)
        swap_type = ql.VanillaSwap.Payer if p.pay_fixed else ql.VanillaSwap.Receiver
        swap = ql.VanillaSwap(
            swap_type,
            p.notional,
            fixed_schedule,
            p.fixed_rate,
            ql.Actual365Fixed(),
            float_schedule,
            index,
            0.0,
            ql.Actual360(),
        )
        swap.setPricingEngine(ql.DiscountingSwapEngine(curve))
        return swap.NPV()

    def _swap(self, p: SwapPosition, market: MarketSnapshot | None = None) -> Valuation:
        curve = self._curve_handle(market, p.currency, p.market_swap_rate)
        pv = self._swap_npv(p, p.market_swap_rate, curve)
        bumped = self._swap_npv(p, p.market_swap_rate + 0.0001)
        return Valuation(position_id=p.id, market_value=pv, dv01=bumped - pv)

    def _equity_future(self, p: EquityFuturePosition) -> Valuation:
        # CIP/carry via QL FlatForward DFs (not a QL Futures/ForwardTrade instrument).
        # F = S * DF_q / DF_r; Time(years) discount matches Builtin exactly.
        t = p.maturity_years
        df_r = self._flat_curve(p.risk_free_rate).discount(t)
        df_q = self._flat_curve(p.dividend_yield).discount(t)
        forward = p.spot * df_q / df_r
        mv = p.quantity * p.multiplier * forward
        # Match Builtin cash-delta and analytical 1bp carry sensitivity conventions.
        return Valuation(
            position_id=p.id,
            market_value=mv,
            delta=mv,
            dv01=mv * t * 0.0001,
        )

    def _fx_forward(self, p: FXForwardPosition) -> Valuation:
        # CIP parity via QL FlatForward DFs (not a QL ForwardTrade instrument):
        # N * (F - K) * DF_d with F = S * DF_f / DF_d; Time discount matches Builtin.
        t = p.maturity_years
        domestic = self._flat_curve(p.domestic_rate)
        foreign = self._flat_curve(p.foreign_rate)
        df_d = domestic.discount(t)
        df_f = foreign.discount(t)
        forward = p.spot * df_f / df_d
        pv = p.notional_base * (forward - p.strike) * df_d
        return Valuation(
            position_id=p.id,
            market_value=pv,
            fx_delta=p.notional_base * p.spot,
        )

    def _fx_option(self, p: FXOptionPosition) -> Valuation:
        # Garman–Kohlhagen ≡ Black–Scholes–Merton with foreign rate as dividend yield.
        # Exercise date from _maturity_date (T < ~1/365 clamps to 1 calendar day).
        spot = ql.QuoteHandle(ql.SimpleQuote(p.spot))
        domestic = self._flat_curve(p.domestic_rate)
        foreign = self._flat_curve(p.foreign_rate)
        vol = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(
                self._ql_date(self.evaluation_date),
                ql.NullCalendar(),
                p.volatility,
                ql.Actual365Fixed(),
            )
        )
        process = ql.BlackScholesMertonProcess(spot, foreign, domestic, vol)
        payoff = ql.PlainVanillaPayoff(
            ql.Option.Call if p.option_type == "call" else ql.Option.Put,
            p.strike,
        )
        instrument = ql.VanillaOption(
            payoff,
            ql.EuropeanExercise(self._maturity_date(p.maturity_years)),
        )
        instrument.setPricingEngine(ql.AnalyticEuropeanEngine(process))

        unit_price = instrument.NPV()
        unit_delta = instrument.delta()
        unit_gamma = instrument.gamma()
        unit_vega = instrument.vega()

        return Valuation(
            position_id=p.id,
            market_value=p.notional_base * unit_price,
            # Cash FX delta / gamma / 1-vol-point vega match Builtin conventions.
            fx_delta=p.notional_base * unit_delta * p.spot,
            gamma=p.notional_base * unit_gamma * p.spot * p.spot,
            vega=p.notional_base * unit_vega * 0.01,
        )

    def _ir_future(self, p: InterestRateFuturePosition) -> Valuation:
        # Algebraic STIR mark (same as Builtin). QuantLib Futures/ForwardRateAgreement
        # wiring waits on production curves (M1.4). Kept inside the QL adapter session
        # so evaluation-date locking stays consistent with other instruments.
        mv = p.quantity * p.pv01 * (p.quoted_rate - p.forward_rate) * 10000.0
        return Valuation(position_id=p.id, market_value=mv, dv01=-p.quantity * p.pv01)

    def shocked_value(self, position: Position, scenario: StressScenario, market: MarketSnapshot | None = None) -> float:
        return super().shocked_value(position, scenario, market)
