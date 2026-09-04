from __future__ import annotations

import math
from contextlib import contextmanager
from datetime import date, timedelta
from threading import RLock

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
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    Position,
    StressScenario,
    SwapPosition,
    SwaptionPosition,
    Valuation,
    calendar_as_of,
)
from app.interfaces.pricing import PricingEngine
from app.market.demo_snapshot import MissingMarketDataError
from app.market.vol_surfaces import vol_surface_from_dict
from app.pricing.curve_rates import (
    continuous_zero,
    has_curve_or_key_rates,
    required_continuous_zero,
    required_ir_future_quote,
    select_yield_curve,
)
from app.pricing.surface_vol import (
    required_equity_option_vol,
    required_fx_option_vol,
    required_ir_option_vol,
)
from app.risk.historical import require_explicit_market

try:
    import QuantLib as ql
except ImportError as exc:  # pragma: no cover - exercised only when dependency is absent
    ql = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

# Process-owned QuantLib session. Settings.evaluationDate and IndexManager
# histories are process-global; this lock is the only serialization boundary.
# Engine instances bind it — they must not allocate a private RLock.
_QL_PROCESS_LOCK = RLock()
_QL_SESSION_DEPTH = 0


class QuantLibUnavailableError(RuntimeError):
    pass


def _parse_snapshot_as_of(as_of: object) -> date | None:
    """Return a calendar date from snapshot ``as_of``, or None for engine labels."""
    return calendar_as_of(as_of)


def _required_equity_spot(market: MarketSnapshot, symbol: str) -> float:
    try:
        return market.equity_spots[symbol]
    except KeyError:
        raise MissingMarketDataError(f"equity_spots[{symbol}]") from None


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


class QuantLibPricingEngine(PricingEngine):
    """QuantLib-backed valuation adapter.

    QuantLib Settings and IndexManager state are process-global.  All access is
    serialized by the module-level ``_QL_PROCESS_LOCK`` (shared by every engine
    instance).  A calendar ``MarketSnapshot.as_of`` (``date`` or ISO
    ``YYYY-MM-DD``) drives the evaluation date for a valuation; engine labels
    (``current`` / ``t0``) keep ``evaluation_date``.
    IndexManager histories are cleared on the outermost session exit so one
    valuation cannot leave fixings for the next.

    In-process callers are serialized.  Parallel full revaluation should use
    separate processes (R0.3.5), not additional in-process QuantLib engines.
    """

    _process_lock = _QL_PROCESS_LOCK

    def __init__(self, evaluation_date: date | None = None):
        if ql is None:
            raise QuantLibUnavailableError(
                "QuantLib is not installed. Install backend requirements or run "
                "`pip install QuantLib`."
            ) from _IMPORT_ERROR
        self.evaluation_date = evaluation_date or date.today()
        # Bind the process lock; do not allocate a per-instance RLock.
        self._lock = _QL_PROCESS_LOCK

    @contextmanager
    def _session(self, evaluation_date: date | None = None):
        global _QL_SESSION_DEPTH
        eval_date = evaluation_date or self.evaluation_date
        with self._lock:
            previous_settings = ql.Settings.instance().evaluationDate
            previous_engine_date = self.evaluation_date
            outermost = _QL_SESSION_DEPTH == 0
            if outermost:
                ql.IndexManager.instance().clearHistories()
            _QL_SESSION_DEPTH += 1
            self.evaluation_date = eval_date
            ql.Settings.instance().evaluationDate = self._ql_date(eval_date)
            try:
                yield
            finally:
                _QL_SESSION_DEPTH -= 1
                self.evaluation_date = previous_engine_date
                ql.Settings.instance().evaluationDate = previous_settings
                if _QL_SESSION_DEPTH == 0:
                    ql.IndexManager.instance().clearHistories()

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
        market = require_explicit_market(market)
        try:
            terms = terms_from_position(position)
        except TypeError:
            raise TypeError(
                f"unsupported instrument for QuantLib production pricing: "
                f"{type(position).__name__}"
            ) from None

        session_date = self.evaluation_date
        parsed_as_of = _parse_snapshot_as_of(market.as_of)
        if parsed_as_of is not None:
            session_date = parsed_as_of
        # Snapshot is the sole mark authority; leftover DTO marks are ignored.
        updates = _economics_from_terms(position, terms)
        updates.update(_snapshot_marks_from_terms(terms, market))
        working = position.model_copy(update=updates)

        with self._session(evaluation_date=session_date):
            if isinstance(terms, EquityTerms):
                return Valuation(
                    position_id=terms.id,
                    market_value=terms.quantity * working.price,
                    delta=terms.quantity * working.price,
                )
            if isinstance(terms, EquityFutureTerms):
                return self._equity_future(working)
            if isinstance(terms, EuropeanOptionTerms):
                return self._option(working, market)
            if isinstance(terms, BondTerms):
                return self._bond(working, market)
            if isinstance(terms, SwapTerms):
                return self._swap(working, market)
            if isinstance(terms, InterestRateFutureTerms):
                return self._ir_future(working)
            if isinstance(terms, CapFloorTerms):
                return self._cap_floor(working, market)
            if isinstance(terms, SwaptionTerms):
                return self._swaption(working, market)
            if isinstance(terms, FXForwardTerms):
                return self._fx_forward(working)
            if isinstance(terms, FXOptionTerms):
                return self._fx_option(working, market)
            raise TypeError(
                f"unsupported instrument for QuantLib production pricing: "
                f"{type(working).__name__}"
            )

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

    def _black_vol_handle(
        self,
        market: MarketSnapshot | None,
        *,
        name: str,
        asset_class: str,
        spot: float,
        flat_vol: float,
    ):
        """Build a QL vol term structure from an attached grid, else flat scalar vol."""
        raw = (market.vol_surfaces.get(name) if market is not None else None) or None
        if raw is not None and spot > 0.0 and str(raw.get("asset_class", "")).lower() == asset_class:
            surface = vol_surface_from_dict(raw, default_name=name)
            return self._black_surface_handle(surface, spot)
        return ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(
                self._ql_date(self.evaluation_date),
                ql.NullCalendar(),
                flat_vol,
                ql.Actual365Fixed(),
            )
        )

    def _black_surface_handle(self, surface, spot: float):
        expiries = sorted({p.expiry_years for p in surface.points})
        moneynesses = sorted({p.moneyness for p in surface.points})
        dates = [self._maturity_date(t) for t in expiries]
        strikes = [spot * m for m in moneynesses]
        vols = ql.Matrix(len(strikes), len(dates))
        for row, strike in enumerate(strikes):
            moneyness = strike / spot
            for col, expiry in enumerate(expiries):
                vols[row][col] = surface.vol(expiry, moneyness)
        ql_surface = ql.BlackVarianceSurface(
            self._ql_date(self.evaluation_date),
            ql.NullCalendar(),
            dates,
            strikes,
            vols,
            ql.Actual365Fixed(),
        )
        ql_surface.enableExtrapolation()
        return ql.BlackVolTermStructureHandle(ql_surface)

    def _option(self, p: EuropeanOptionPosition, market: MarketSnapshot | None = None) -> Valuation:
        spot = ql.QuoteHandle(ql.SimpleQuote(p.spot))
        risk_free = self._flat_curve(p.risk_free_rate)
        dividend = self._flat_curve(p.dividend_yield)
        vol = self._black_vol_handle(
            market,
            name=p.symbol,
            asset_class="equity",
            spot=p.spot,
            flat_vol=p.volatility,
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

    def _fx_option(self, p: FXOptionPosition, market: MarketSnapshot | None = None) -> Valuation:
        # Garman–Kohlhagen ≡ Black–Scholes–Merton with foreign rate as dividend yield.
        # Exercise date from _maturity_date (T < ~1/365 clamps to 1 calendar day).
        spot = ql.QuoteHandle(ql.SimpleQuote(p.spot))
        domestic = self._flat_curve(p.domestic_rate)
        foreign = self._flat_curve(p.foreign_rate)
        vol = self._black_vol_handle(
            market,
            name=p.pair,
            asset_class="fx",
            spot=p.spot,
            flat_vol=p.volatility,
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
        option_type = ql.Option.Call if p.option_type == "cap" else ql.Option.Put
        unit_pv = 0.0
        unit_vega = 0.0

        for i in range(1, periods + 1):
            payment_time = i * accrual
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
            stddev = sigma * math.sqrt(option_expiry)
            discount = df * accrual
            unit_pv += ql.blackFormula(option_type, p.strike, forward, stddev, discount)
            d1 = (math.log(forward / p.strike) + 0.5 * sigma * sigma * option_expiry) / stddev
            unit_vega += (
                df
                * accrual
                * forward
                * math.exp(-0.5 * d1 * d1)
                / math.sqrt(2.0 * math.pi)
                * math.sqrt(option_expiry)
            )

        scale = p.quantity * p.notional
        return scale * unit_pv, scale * unit_vega * 0.01

    def _cap_floor(self, p: CapFloorPosition, market: MarketSnapshot | None) -> Valuation:
        # Native QuantLib Black formula per optionlet; no QuantLib objects leave this adapter.
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
        stddev = sigma * math.sqrt(expiry)
        option_type = ql.Option.Call if p.option_type == "payer" else ql.Option.Put
        scale = p.quantity * p.notional
        pv = scale * ql.blackFormula(option_type, p.strike, forward, stddev, annuity)
        d1 = (math.log(forward / p.strike) + 0.5 * sigma * sigma * expiry) / stddev
        vega = (
            scale
            * annuity
            * forward
            * math.exp(-0.5 * d1 * d1)
            / math.sqrt(2.0 * math.pi)
            * math.sqrt(expiry)
            * 0.01
        )
        return pv, vega

    def _swaption(self, p: SwaptionPosition, market: MarketSnapshot | None) -> Valuation:
        # Native QuantLib Black formula on a deterministic flat par-swap annuity.
        pv, vega = self._swaption_components(p, market)
        bumped, _ = self._swaption_components(p, market, rate_shift=0.0001)
        return Valuation(position_id=p.id, market_value=pv, vega=vega, dv01=bumped - pv)

    def shocked_value(self, position: Position, scenario: StressScenario, market: MarketSnapshot | None = None) -> float:
        return super().shocked_value(position, scenario, market)
