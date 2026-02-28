"""Unified bump-and-revalue sensitivity engine (M1.7).

Computes portfolio / factor sensitivities by shocking an immutable
``MarketSnapshot`` (via ``model_copy``) and revaluing through
:class:`~app.interfaces.pricing.PricingEngine` only — no QuantLib types
in the risk layer.

Conventions (aligned with Builtin / Valuation field meanings):
- **delta / fx_delta** — cash delta: ``S * ∂V/∂S`` (relative spot bump ``h``).
- **gamma** — dollar gamma: ``S² * ∂²V/∂S²``.
- **vega** — P&L per 1 absolute vol point (``0.01``). Engine vol bumps
  add an absolute decimal to ``equity_vols`` / ``fx_vols`` (default
  ``vol_bump=0.01`` = +1 vol point). This differs from
  :meth:`MarketSnapshot.bump` for ``EquityVol`` / ``FXVol``, which applies a
  *relative* vol change (``0.25`` = +25% of the current vol level).
- **dv01 / key_rate_dv01** — P&L for a +1bp rate move
  (central difference scaled to 1bp).

Key-rate DV01:
Pricing adapters revalue bonds/swaps/IR futures from ``curves`` / ``key_rates``
when attached. When :data:`KEY_RATE_CURVES_CONSUMED_BY_PRICING` is True and the
tenor exists under ``key_rates`` / ``curves``, the engine bumps that pillar only
(via :meth:`MarketSnapshot.bump`) so curve-aware pricing sees true tenor
isolation. Otherwise it falls back to a parallel shock and tags
``method="bump_revalue_parallel_fallback"``.

Extension points for vanna / volga / cross-gamma are reserved
(:data:`FUTURE_MEASURES`); calling them raises ``NotImplementedError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, Sequence

from app.domain.models import MarketSnapshot, Portfolio, Position
from app.interfaces.pricing import PricingEngine
from app.market.snapshot import MarketDataProvider
from app.risk.factor_types import (
    EquitySpot,
    EquityVol,
    FXSpot,
    FXVol,
    RateZero,
    RiskFactor,
    factor_sort_key,
)
from app.risk.factors import RiskFactorEngine
from app.sample import DemoPortfolioMarketDataProvider

MeasureName = Literal[
    "delta",
    "gamma",
    "vega",
    "dv01",
    "key_rate_dv01",
    "fx_delta",
    "vanna",
    "volga",
    "cross_gamma",
]

SUPPORTED_MEASURES: frozenset[str] = frozenset(
    {"delta", "gamma", "vega", "dv01", "key_rate_dv01", "fx_delta"}
)
FUTURE_MEASURES: frozenset[str] = frozenset({"vanna", "volga", "cross_gamma"})

DEFAULT_MEASURES: tuple[MeasureName, ...] = (
    "delta",
    "gamma",
    "vega",
    "dv01",
    "key_rate_dv01",
    "fx_delta",
)

# True: PricingEngine adapters revalue IR products from ``key_rates`` / ``curves``.
KEY_RATE_CURVES_CONSUMED_BY_PRICING: bool = True

METHOD_BUMP_REVALUE = "bump_revalue"
METHOD_PARALLEL_FALLBACK = "bump_revalue_parallel_fallback"


def _tenor_in_curves(market: MarketSnapshot, currency: str, tenor: str) -> bool:
    ccy = currency.upper()
    for payload in market.curves.values():
        if not isinstance(payload, Mapping):
            continue
        if str(payload.get("currency", "")).upper() != ccy:
            continue
        zeros = payload.get("zeros") or {}
        if tenor in zeros:
            return True
    return False


def _key_rate_tenor_available(market: MarketSnapshot, currency: str, tenor: str) -> bool:
    nested = market.key_rates.get(currency) or {}
    return tenor in nested or _tenor_in_curves(market, currency, tenor)


@dataclass(frozen=True, slots=True)
class SensitivityMeasure:
    """One bump-and-revalue sensitivity result."""

    name: MeasureName
    factor: RiskFactor
    value: float
    unit: str
    bump_size: float
    method: str = METHOD_BUMP_REVALUE


def _portfolio_pv(portfolio: Portfolio, pricing: PricingEngine, market: MarketSnapshot) -> float:
    return sum(v.market_value for v in pricing.value_portfolio(portfolio, market))


class SensitivityEngine:
    """Finite-difference sensitivities via market bumps + revaluation."""

    def __init__(
        self,
        market_data: MarketDataProvider | None = None,
        *,
        spot_bump: float = 0.01,
        vol_bump: float = 0.01,
        rate_bump_bps: float = 1.0,
    ):
        if spot_bump <= 0 or vol_bump <= 0 or rate_bump_bps <= 0:
            raise ValueError("bump sizes must be positive")
        self.market_data = market_data or DemoPortfolioMarketDataProvider()
        self.spot_bump = spot_bump
        self.vol_bump = vol_bump
        self.rate_bump_bps = rate_bump_bps
        self._factors = RiskFactorEngine(self.market_data)

    # --- snapshot shocks (local copies; does not require M1.3 bump API) ---

    @staticmethod
    def _bump_equity_spot(market: MarketSnapshot, symbol: str, relative: float) -> MarketSnapshot:
        spots = dict(market.equity_spots)
        if symbol not in spots:
            return market
        spots[symbol] = spots[symbol] * (1.0 + relative)
        return market.model_copy(update={"id": f"{market.id}:eq:{symbol}:{relative}", "equity_spots": spots})

    @staticmethod
    def _bump_fx_spot(market: MarketSnapshot, pair: str, relative: float) -> MarketSnapshot:
        spots = dict(market.fx_spots)
        if pair not in spots:
            return market
        spots[pair] = spots[pair] * (1.0 + relative)
        return market.model_copy(update={"id": f"{market.id}:fx:{pair}:{relative}", "fx_spots": spots})

    @staticmethod
    def _bump_equity_vol(market: MarketSnapshot, underlying: str, absolute: float) -> MarketSnapshot:
        vols = dict(market.equity_vols)
        if underlying not in vols:
            return market
        vols[underlying] = max(1e-8, vols[underlying] + absolute)
        return market.model_copy(update={"id": f"{market.id}:eqvol:{underlying}:{absolute}", "equity_vols": vols})

    @staticmethod
    def _bump_fx_vol(market: MarketSnapshot, pair: str, absolute: float) -> MarketSnapshot:
        vols = dict(market.fx_vols)
        if pair not in vols:
            return market
        vols[pair] = max(1e-8, vols[pair] + absolute)
        return market.model_copy(update={"id": f"{market.id}:fxvol:{pair}:{absolute}", "fx_vols": vols})

    @staticmethod
    def _bump_parallel_rate(market: MarketSnapshot, currency: str, bps: float) -> MarketSnapshot:
        """Parallel +1bp-style shock: scalar rates + key_rates + matching curve zeros."""
        if currency not in market.rates:
            return market
        amount = bps / 10_000.0
        return market.bump(RateZero(currency=currency, tenor="PARALLEL"), amount)

    @staticmethod
    def _bump_key_rate(market: MarketSnapshot, currency: str, tenor: str, bps: float) -> MarketSnapshot:
        """Shock used for ``key_rate_dv01``.

        When :data:`KEY_RATE_CURVES_CONSUMED_BY_PRICING` is True and the tenor
        exists under ``key_rates`` / ``curves``, bump that pillar only (does not
        touch scalar ``rates[ccy]``). Otherwise fall back to parallel.
        """
        if KEY_RATE_CURVES_CONSUMED_BY_PRICING and _key_rate_tenor_available(market, currency, tenor):
            return market.bump(RateZero(currency=currency, tenor=tenor), bps / 10_000.0)
        return SensitivityEngine._bump_parallel_rate(market, currency, bps)

    @staticmethod
    def _key_rate_method(market: MarketSnapshot, currency: str, tenor: str) -> str:
        if KEY_RATE_CURVES_CONSUMED_BY_PRICING and _key_rate_tenor_available(market, currency, tenor):
            return METHOD_BUMP_REVALUE
        return METHOD_PARALLEL_FALLBACK

    # --- FD kernels ---

    def _cash_delta(
        self,
        pv0: float,
        bump_up,
        bump_down,
        h: float,
    ) -> float:
        # (V(S(1+h)) - V(S(1-h))) / (2h) ≈ S ∂V/∂S
        del pv0  # base unused for central first derivative
        return (bump_up - bump_down) / (2.0 * h)

    def _dollar_gamma(self, pv0: float, bump_up: float, bump_down: float, h: float) -> float:
        # (V_up - 2 V0 + V_down) / h² ≈ S² ∂²V/∂S²
        return (bump_up - 2.0 * pv0 + bump_down) / (h * h)

    def _central_scaled(self, bump_up: float, bump_down: float, half_span: float, scale: float) -> float:
        """Central difference ∂V/∂x * scale, where bumps are ±half_span in x-units."""
        return (bump_up - bump_down) / (2.0 * half_span) * scale

    # --- public API ---

    def calculate(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        measures: Sequence[MeasureName] | None = None,
        market: MarketSnapshot | None = None,
    ) -> list[SensitivityMeasure]:
        """Portfolio-level factor sensitivities for the requested measures."""
        requested = tuple(measures) if measures is not None else DEFAULT_MEASURES
        self._validate_measures(requested)
        market = market or self.market_data.snapshot(portfolio)
        factors = [
            f
            for f, _ in self._factors.calculate_typed(
                portfolio, pricing, market
            )
        ]
        return self._compute(portfolio, pricing, market, factors, requested, scope="portfolio")

    def calculate_position(
        self,
        position: Position,
        pricing: PricingEngine,
        measures: Sequence[MeasureName] | None = None,
        market: MarketSnapshot | None = None,
    ) -> list[SensitivityMeasure]:
        """Single-position sensitivities (same conventions as portfolio)."""
        portfolio = Portfolio(id="single", name="single", positions=[position])
        requested = tuple(measures) if measures is not None else DEFAULT_MEASURES
        self._validate_measures(requested)
        market = market or self.market_data.snapshot(portfolio)
        factors = [
            f
            for f, _ in self._factors.calculate_typed(
                portfolio, pricing, market
            )
        ]
        return self._compute(portfolio, pricing, market, factors, requested, scope="position")

    def _validate_measures(self, measures: Iterable[str]) -> None:
        for name in measures:
            if name in FUTURE_MEASURES:
                raise NotImplementedError(
                    f"{name!r} is reserved for joint-bump extension (vanna/volga/cross-gamma); "
                    "not implemented in M1.7"
                )
            if name not in SUPPORTED_MEASURES:
                raise ValueError(f"unknown sensitivity measure: {name!r}")

    def _compute(
        self,
        portfolio: Portfolio,
        pricing: PricingEngine,
        market: MarketSnapshot,
        factors: Sequence[RiskFactor],
        measures: Sequence[MeasureName],
        *,
        scope: str,
    ) -> list[SensitivityMeasure]:
        del scope
        pv0 = _portfolio_pv(portfolio, pricing, market)
        h = self.spot_bump
        vol_h = self.vol_bump
        bp = self.rate_bump_bps
        out: list[SensitivityMeasure] = []
        measure_set = set(measures)
        # Parallel DV01 once per currency (tenors share the same flat rate today).
        dv01_currencies: set[str] = set()

        for factor in sorted(factors, key=factor_sort_key):
            if isinstance(factor, EquitySpot) and factor.key in market.equity_spots:
                up = _portfolio_pv(portfolio, pricing, self._bump_equity_spot(market, factor.symbol, h))
                down = _portfolio_pv(portfolio, pricing, self._bump_equity_spot(market, factor.symbol, -h))
                if "delta" in measure_set:
                    out.append(
                        SensitivityMeasure(
                            name="delta",
                            factor=factor,
                            value=self._cash_delta(pv0, up, down, h),
                            unit="cash_delta",
                            bump_size=h,
                        )
                    )
                if "gamma" in measure_set:
                    out.append(
                        SensitivityMeasure(
                            name="gamma",
                            factor=factor,
                            value=self._dollar_gamma(pv0, up, down, h),
                            unit="dollar_gamma",
                            bump_size=h,
                        )
                    )

            elif isinstance(factor, FXSpot) and factor.key in market.fx_spots:
                up = _portfolio_pv(portfolio, pricing, self._bump_fx_spot(market, factor.pair, h))
                down = _portfolio_pv(portfolio, pricing, self._bump_fx_spot(market, factor.pair, -h))
                if "fx_delta" in measure_set:
                    out.append(
                        SensitivityMeasure(
                            name="fx_delta",
                            factor=factor,
                            value=self._cash_delta(pv0, up, down, h),
                            unit="cash_fx_delta",
                            bump_size=h,
                        )
                    )
                if "gamma" in measure_set:
                    out.append(
                        SensitivityMeasure(
                            name="gamma",
                            factor=factor,
                            value=self._dollar_gamma(pv0, up, down, h),
                            unit="dollar_gamma",
                            bump_size=h,
                        )
                    )

            elif isinstance(factor, EquityVol) and factor.underlying in market.equity_vols:
                if "vega" in measure_set:
                    up = _portfolio_pv(
                        portfolio, pricing, self._bump_equity_vol(market, factor.underlying, vol_h)
                    )
                    down = _portfolio_pv(
                        portfolio, pricing, self._bump_equity_vol(market, factor.underlying, -vol_h)
                    )
                    # scale to 1 vol point P&L
                    value = self._central_scaled(up, down, vol_h, 0.01)
                    out.append(
                        SensitivityMeasure(
                            name="vega",
                            factor=factor,
                            value=value,
                            unit="per_vol_point",
                            bump_size=vol_h,
                        )
                    )

            elif isinstance(factor, FXVol) and factor.pair in market.fx_vols:
                if "vega" in measure_set:
                    up = _portfolio_pv(portfolio, pricing, self._bump_fx_vol(market, factor.pair, vol_h))
                    down = _portfolio_pv(portfolio, pricing, self._bump_fx_vol(market, factor.pair, -vol_h))
                    value = self._central_scaled(up, down, vol_h, 0.01)
                    out.append(
                        SensitivityMeasure(
                            name="vega",
                            factor=factor,
                            value=value,
                            unit="per_vol_point",
                            bump_size=vol_h,
                        )
                    )

            elif isinstance(factor, RateZero) and factor.currency in market.rates:
                if "dv01" in measure_set and factor.currency not in dv01_currencies:
                    dv01_currencies.add(factor.currency)
                    up = _portfolio_pv(
                        portfolio, pricing, self._bump_parallel_rate(market, factor.currency, bp)
                    )
                    down = _portfolio_pv(
                        portfolio, pricing, self._bump_parallel_rate(market, factor.currency, -bp)
                    )
                    # P&L for +1bp ≈ ∂V/∂r * 1bp; central over ±bp then scale to 1bp
                    value = self._central_scaled(up, down, bp, 1.0)
                    out.append(
                        SensitivityMeasure(
                            name="dv01",
                            factor=RateZero(currency=factor.currency, tenor="PARALLEL"),
                            value=value,
                            unit="per_bp",
                            bump_size=bp,
                        )
                    )
                if "key_rate_dv01" in measure_set:
                    up = _portfolio_pv(
                        portfolio,
                        pricing,
                        self._bump_key_rate(market, factor.currency, factor.tenor, bp),
                    )
                    down = _portfolio_pv(
                        portfolio,
                        pricing,
                        self._bump_key_rate(market, factor.currency, factor.tenor, -bp),
                    )
                    value = self._central_scaled(up, down, bp, 1.0)
                    out.append(
                        SensitivityMeasure(
                            name="key_rate_dv01",
                            factor=factor,
                            value=value,
                            unit="per_bp",
                            bump_size=bp,
                            method=self._key_rate_method(market, factor.currency, factor.tenor),
                        )
                    )

        return out
