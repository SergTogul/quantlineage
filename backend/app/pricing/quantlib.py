from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
import math
from threading import RLock

from app.domain.models import (
    BondPosition,
    EquityPosition,
    EuropeanOptionPosition,
    MarketSnapshot,
    Position,
    StressScenario,
    SwapPosition,
    Valuation,
)
from app.interfaces.pricing import PricingEngine

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
        days = max(1, round(years * 365.0))
        return self._ql_date(self.evaluation_date + timedelta(days=days))

    def value(self, position: Position, market: MarketSnapshot | None = None) -> Valuation:
        if market is not None:
            # Convert immutable market snapshot values into the trade-local marks QuantLib consumes.
            updates = {}
            if isinstance(position, EquityPosition): updates["price"] = market.equity_spots.get(position.symbol, position.price)
            elif isinstance(position, EuropeanOptionPosition):
                updates = {"spot": market.equity_spots.get(position.symbol, position.spot), "volatility": market.equity_vols.get(position.symbol, position.volatility), "risk_free_rate": market.rates.get("USD", position.risk_free_rate)}
            elif isinstance(position, BondPosition): updates["yield_rate"] = market.rates.get(position.currency, position.yield_rate)
            elif isinstance(position, SwapPosition): updates["market_swap_rate"] = market.rates.get(position.currency, position.market_swap_rate)
            if updates: position = position.model_copy(update=updates)
        with self._session():
            if isinstance(position, EquityPosition):
                return Valuation(
                    position_id=position.id,
                    market_value=position.quantity * position.price,
                    delta=position.quantity * position.price,
                )
            if isinstance(position, EuropeanOptionPosition):
                return self._option(position)
            if isinstance(position, BondPosition):
                return self._bond(position)
            if isinstance(position, SwapPosition):
                return self._swap(position)
        # New MVP instruments not yet covered by native QuantLib adapter use the reference pricer.
        from app.pricing.builtin import BuiltinPricingEngine
        return BuiltinPricingEngine().value(position, market)

    def _flat_curve(self, rate: float):
        today = self._ql_date(self.evaluation_date)
        return ql.YieldTermStructureHandle(
            ql.FlatForward(today, rate, ql.Actual365Fixed(), ql.Continuous)
        )

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

    def _bond_npv(self, p: BondPosition, yield_rate: float) -> float:
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
        bond.setPricingEngine(ql.DiscountingBondEngine(self._flat_curve(yield_rate)))
        return p.quantity * bond.NPV()

    def _bond(self, p: BondPosition) -> Valuation:
        pv = self._bond_npv(p, p.yield_rate)
        bumped = self._bond_npv(p, p.yield_rate + 0.0001)
        return Valuation(position_id=p.id, market_value=pv, dv01=bumped - pv)


    def _seed_ibor_fixings(self, index, float_schedule, rate: float) -> None:
        eval_dt = self._ql_date(self.evaluation_date)
        for i in range(len(float_schedule) - 1):
            fixing_date = index.fixingDate(float_schedule[i])
            if fixing_date <= eval_dt:
                index.addFixing(fixing_date, rate, True)

    def _swap_npv(self, p: SwapPosition, market_rate: float) -> float:
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
        curve = self._flat_curve(market_rate)
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

    def _swap(self, p: SwapPosition) -> Valuation:
        pv = self._swap_npv(p, p.market_swap_rate)
        bumped = self._swap_npv(p, p.market_swap_rate + 0.0001)
        return Valuation(position_id=p.id, market_value=pv, dv01=bumped - pv)

    def shocked_value(self, position: Position, scenario: StressScenario, market: MarketSnapshot | None = None) -> float:
        return super().shocked_value(position, scenario, market)
