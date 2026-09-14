"""Deterministic historical analytics from a frozen factor panel (Wave B G1/G2).

Period P&L uses the same panel approximations as ``HistoricalRiskEngine``.
Portfolio VaR/ES are the engine's ``calculate()`` numbers on the sliced
window — this module does not reimplement quantile / tail math.

Canonical benchmark (G2) is Wave A ``equity:US:SPY`` / ``EquitySpot:SPY`` on
the same frozen panel. Relative analytics, not allocation advice (AD-B4).
Benchmark VaR/ES is ``HistoricalRiskEngine.calculate()`` on a same-notional
SPY book. Beta denominator is ``cov(r_p, r_b) / var(r_b)``.

Units:
- period / cumulative / annualized / excess returns: fraction (0.01 = 1%)
- drawdown / relative drawdown: fraction of peak, ≤ 0, implicit start NAV = 1
- volatility / tracking error / Sharpe: annualized fraction
- beta / correlation: dimensionless
- VaR / ES: currency loss (≥ 0), HistoricalRiskEngine convention
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    EquityPosition,
    FiniteFloat,
    FiniteInputMixin,
    MarketSnapshot,
    Portfolio,
    VaRMethodology,
)
from app.interfaces.pricing import PricingEngine
from app.market.history.data_mode import data_source_label
from app.market.history.spec import WAVE_A_FACTOR_MAPPINGS
from app.risk.factor_panel import HistoricalFactorPanel, panel_factor_identity
from app.risk.factor_types import RiskFactor, factor_column_id, parse_factor_column_id
from app.risk.historical import (
    HistoricalRiskEngine,
    approximate_pnl_from_panel,
    full_revaluation_pnl_from_panel,
)

_SPY_MAPPING = next(item for item in WAVE_A_FACTOR_MAPPINGS if item.instrument_id == "equity:US:SPY")
WAVE_A_BENCHMARK_INSTRUMENT_ID = _SPY_MAPPING.instrument_id
WAVE_A_BENCHMARK_FACTOR = parse_factor_column_id(_SPY_MAPPING.factor_column)
_MIN_BENCHMARK_OVERLAP = 2

_NOTE_ZERO_VOL = "sharpe_undefined_zero_volatility"
_NOTE_SHORT_VOL = "sample_volatility_undefined_n_lt_2"
_NOTE_ROLLING = "rolling_volatility_window_exceeds_sample"
_NOTE_DROPPED = "dropped_missing_weekdays"


class AnalyticsFrequency(StrEnum):
    DAILY = "DAILY"


class MissingDatePolicy(StrEnum):
    DROP_WITH_NOTE = "drop_with_note"
    FAIL_CLOSED = "fail_closed"


class AnnualizationConvention(BaseModel):
    """Explicit annualization knobs (AD-B9). Defaults are trading-day 252."""

    model_config = ConfigDict(extra="forbid")

    periods_per_year: int = Field(default=252, ge=1, le=366)
    return_method: Literal["cagr"] = "cagr"
    volatility_method: Literal["sqrt_time"] = "sqrt_time"
    sample_ddof: Literal[0, 1] = 1


class DatedValue(BaseModel):
    as_of: date
    value: float


class PeriodWindow(BaseModel):
    start: date
    end: date
    return_fraction: float


class HistoricalAnalyticsRequest(FiniteInputMixin):
    """HTTP / service request. Range changes do not mutate the frozen panel."""

    model_config = ConfigDict(extra="forbid")

    portfolio: Portfolio
    start: date
    end: date
    frequency: AnalyticsFrequency = AnalyticsFrequency.DAILY
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA
    annualization: AnnualizationConvention = Field(default_factory=AnnualizationConvention)
    historical_dataset_id: str | None = Field(default=None, min_length=1)
    historical_dataset_version: str | None = Field(default=None, min_length=1)
    market_snapshot_id: str | None = Field(default=None, min_length=1)
    rolling_window: int = Field(default=21, ge=2, le=5000)
    risk_free_rate: FiniteFloat = 0.0
    missing_date_policy: MissingDatePolicy = MissingDatePolicy.DROP_WITH_NOTE
    period_window: int = Field(default=1, ge=1, le=5000)
    include_benchmark: bool = False


class BenchmarkRelativeRisk(BaseModel):
    """Canonical Wave A SPY relative analytics nested on the G1 result (AD-B3)."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    factor_column: str
    observation_count: int
    cumulative_return: float
    excess_return: float
    correlation: float
    beta: float
    tracking_error: float
    relative_drawdown: float
    var_95: float
    var_99: float
    expected_shortfall_99: float
    wealth: list[DatedValue]
    relative_drawdown_series: list[DatedValue]
    aligned_start: date
    aligned_end: date
    units: dict[str, str]


class HistoricalAnalyticsResult(BaseModel):
    """One canonical result for summary metrics and time series (AD-B3)."""

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str
    portfolio_version: int
    historical_dataset_id: str
    historical_dataset_version: str
    market_snapshot_id: str | None
    start: date
    end: date
    frequency: AnalyticsFrequency
    methodology: VaRMethodology
    annualization: AnnualizationConvention
    risk_free_rate: float
    market_value: float
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    sharpe: float | None
    var_95: float
    var_99: float
    expected_shortfall_99: float
    wealth: list[DatedValue]
    cumulative: list[DatedValue]
    drawdown: list[DatedValue]
    period_returns: list[DatedValue]
    rolling_volatility: list[DatedValue]
    best_period: PeriodWindow
    worst_period: PeriodWindow
    notes: list[str]
    dropped_dates: list[date]
    observation_count: int
    units: dict[str, str]
    data_source_label: str
    benchmark: BenchmarkRelativeRisk | None = None


def align_dated_series(
    left_dates: Sequence[date],
    left_values: Sequence[float],
    right_dates: Sequence[date],
    right_values: Sequence[float],
    *,
    min_overlap: int = _MIN_BENCHMARK_OVERLAP,
) -> tuple[list[date], np.ndarray, np.ndarray]:
    """Intersect two dated series by calendar date. No positional zip, no ffill."""
    if len(left_dates) != len(left_values):
        raise ValueError("left dates/values length mismatch")
    if len(right_dates) != len(right_values):
        raise ValueError("right dates/values length mismatch")
    left_map: dict[date, float] = {}
    for as_of, value in zip(left_dates, left_values, strict=True):
        if as_of in left_map:
            raise ValueError(f"duplicate left date: {as_of.isoformat()}")
        left_map[as_of] = float(value)
    right_map: dict[date, float] = {}
    for as_of, value in zip(right_dates, right_values, strict=True):
        if as_of in right_map:
            raise ValueError(f"duplicate right date: {as_of.isoformat()}")
        right_map[as_of] = float(value)
    overlap = sorted(set(left_map) & set(right_map))
    if len(overlap) < min_overlap:
        raise ValueError(
            f"insufficient overlapping dates for benchmark alignment: "
            f"{len(overlap)} < {min_overlap}"
        )
    left = np.asarray([left_map[day] for day in overlap], dtype=float)
    right = np.asarray([right_map[day] for day in overlap], dtype=float)
    return overlap, left, right


def _weekdays_inclusive(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _slice_panel(panel: HistoricalFactorPanel, start: date, end: date) -> HistoricalFactorPanel:
    if start > end:
        raise ValueError("start must be on or before end")
    dates: list[date] = []
    rows: list[list[tuple[RiskFactor, float]]] = []
    for obs in panel.observations:
        if start <= obs.as_of <= end:
            dates.append(obs.as_of)
            rows.append([(factor, obs.change(factor)) for factor in panel.factors])
    if not dates:
        raise ValueError(
            f"no factor observations in range [{start.isoformat()}, {end.isoformat()}]"
        )
    return HistoricalFactorPanel.from_pairs(dates, rows)


def _period_pnl(
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    market: MarketSnapshot,
    panel: HistoricalFactorPanel,
    methodology: VaRMethodology,
) -> np.ndarray:
    if methodology is VaRMethodology.FULL_REVALUATION:
        return full_revaluation_pnl_from_panel(portfolio, pricing_engine, market, panel)
    return approximate_pnl_from_panel(
        portfolio,
        pricing_engine,
        market,
        panel,
        methodology=methodology,
    )


def _window_compound(returns: np.ndarray, start: int, length: int) -> float:
    return float(np.prod(1.0 + returns[start : start + length]) - 1.0)


def _panel_factor(panel: HistoricalFactorPanel, factor: RiskFactor) -> RiskFactor | None:
    identity = panel_factor_identity(factor)
    for stored in panel.factors:
        if panel_factor_identity(stored) == identity:
            return stored
    return None


def _dated_factor_returns(
    panel: HistoricalFactorPanel, factor: RiskFactor
) -> tuple[list[date], np.ndarray]:
    dates = list(panel.dates)
    values = np.asarray([obs.change(factor) for obs in panel.observations], dtype=float)
    return dates, values


def _panel_on_dates(panel: HistoricalFactorPanel, dates: Sequence[date]) -> HistoricalFactorPanel:
    wanted = set(dates)
    kept_dates: list[date] = []
    rows: list[list[tuple[RiskFactor, float]]] = []
    for obs in panel.observations:
        if obs.as_of in wanted:
            kept_dates.append(obs.as_of)
            rows.append([(factor, obs.change(factor)) for factor in panel.factors])
    if not kept_dates:
        raise ValueError("no factor observations on aligned benchmark dates")
    return HistoricalFactorPanel.from_pairs(kept_dates, rows)


def _spy_benchmark_book(market_value: float, spy_spot: float) -> Portfolio:
    quantity = market_value / spy_spot
    return Portfolio(
        id="benchmark:equity:US:SPY",
        name="Wave A SPY benchmark",
        version=1,
        positions=[
            EquityPosition(type="equity", id="spy-benchmark", symbol="SPY", quantity=quantity)
        ],
    )


def _canonical_benchmark_relative_risk(
    *,
    sliced: HistoricalFactorPanel,
    portfolio_dates: Sequence[date],
    portfolio_returns: np.ndarray,
    portfolio_market_value: float,
    pricing_engine: PricingEngine,
    market: MarketSnapshot,
    methodology: VaRMethodology,
    convention: AnnualizationConvention,
) -> BenchmarkRelativeRisk:
    stored = _panel_factor(sliced, WAVE_A_BENCHMARK_FACTOR)
    if stored is None:
        raise ValueError(
            "canonical benchmark factor EquitySpot:SPY is missing from the sliced panel; "
            "no silent substitute"
        )
    spy_dates, spy_returns = _dated_factor_returns(sliced, stored)
    aligned_dates, r_p, r_b = align_dated_series(
        portfolio_dates, portfolio_returns, spy_dates, spy_returns
    )
    ddof = convention.sample_ddof
    ppy = float(convention.periods_per_year)
    var_b = float(np.var(r_b, ddof=ddof))
    if var_b == 0.0 or not math.isfinite(var_b):
        raise ValueError("benchmark variance is zero; beta denominator var(r_b) is undefined")
    cov = float(np.cov(r_p, r_b, ddof=ddof)[0, 1])
    beta = cov / var_b
    corr = float(np.corrcoef(r_p, r_b)[0, 1])
    if not math.isfinite(corr):
        raise ValueError("benchmark correlation is undefined")
    tracking_error = float(np.std(r_p - r_b, ddof=ddof) * math.sqrt(ppy))

    wealth_p = np.cumprod(1.0 + r_p)
    wealth_b = np.cumprod(1.0 + r_b)
    if float(np.min(wealth_b)) <= 0.0:
        raise ValueError("benchmark wealth must stay positive")
    excess_return = float(wealth_p[-1] - wealth_b[-1])
    cumulative_return = float(wealth_b[-1] - 1.0)
    relative_wealth = wealth_p / wealth_b
    peak = np.maximum.accumulate(np.concatenate([[1.0], relative_wealth]))[1:]
    relative_dd = relative_wealth / peak - 1.0

    spy_spot = market.equity_spots.get("SPY")
    if spy_spot is None or float(spy_spot) == 0.0 or not math.isfinite(float(spy_spot)):
        raise ValueError(
            "market snapshot missing non-zero SPY spot for canonical benchmark equity:US:SPY"
        )
    spy_book = _spy_benchmark_book(portfolio_market_value, float(spy_spot))
    aligned_panel = _panel_on_dates(sliced, aligned_dates)
    engine = HistoricalRiskEngine(
        factor_panel=aligned_panel,
        methodology=methodology,
        observations=aligned_panel.n_observations,
    )
    summary = engine.calculate(
        spy_book,
        pricing_engine,
        methodology=methodology,
        market=market,
    )

    def _series(values: np.ndarray) -> list[DatedValue]:
        return [
            DatedValue(as_of=as_of, value=float(value))
            for as_of, value in zip(aligned_dates, values, strict=True)
        ]

    return BenchmarkRelativeRisk(
        instrument_id=WAVE_A_BENCHMARK_INSTRUMENT_ID,
        factor_column=factor_column_id(WAVE_A_BENCHMARK_FACTOR),
        observation_count=len(aligned_dates),
        cumulative_return=cumulative_return,
        excess_return=excess_return,
        correlation=corr,
        beta=float(beta),
        tracking_error=tracking_error,
        relative_drawdown=float(relative_dd.min()),
        var_95=float(summary.var_95),
        var_99=float(summary.var_99),
        expected_shortfall_99=float(summary.expected_shortfall_99),
        wealth=_series(wealth_b),
        relative_drawdown_series=_series(relative_dd),
        aligned_start=aligned_dates[0],
        aligned_end=aligned_dates[-1],
        units={
            "returns": "fraction",
            "excess_return": "fraction",
            "beta": "dimensionless",
            "correlation": "dimensionless",
            "tracking_error": "annualized_fraction",
            "relative_drawdown": "fraction_of_peak_relative_wealth_negative",
            "var_es": "currency_loss",
            "wealth": "end_of_period_index",
        },
    )


def compute_historical_analytics(
    *,
    portfolio: Portfolio,
    pricing_engine: PricingEngine,
    market: MarketSnapshot,
    panel: HistoricalFactorPanel,
    start: date,
    end: date,
    frequency: AnalyticsFrequency = AnalyticsFrequency.DAILY,
    methodology: VaRMethodology = VaRMethodology.LINEAR,
    annualization: AnnualizationConvention | None = None,
    historical_dataset_id: str,
    historical_dataset_version: str,
    rolling_window: int = 21,
    risk_free_rate: float = 0.0,
    missing_date_policy: MissingDatePolicy = MissingDatePolicy.DROP_WITH_NOTE,
    period_window: int = 1,
    include_benchmark: bool = False,
) -> HistoricalAnalyticsResult:
    """Build wealth, risk, and identity fields from a frozen panel slice."""
    if frequency is not AnalyticsFrequency.DAILY:
        raise ValueError(f"unsupported frequency: {frequency}")
    if rolling_window < 2:
        raise ValueError("rolling_window must be >= 2")
    if period_window < 1:
        raise ValueError("period_window must be >= 1")
    convention = annualization if annualization is not None else AnnualizationConvention()
    if convention.return_method != "cagr":
        raise ValueError("only CAGR annualization is supported")
    if convention.volatility_method != "sqrt_time":
        raise ValueError("only sqrt_time volatility annualization is supported")

    sliced = _slice_panel(panel, start, end)
    notes: list[str] = []
    expected = _weekdays_inclusive(start, end)
    present = set(sliced.dates)
    missing = [day for day in expected if day not in present]
    if missing:
        if missing_date_policy is MissingDatePolicy.FAIL_CLOSED:
            listed = ", ".join(d.isoformat() for d in missing)
            raise ValueError(f"missing weekday observation(s): {listed}")
        notes.append(_NOTE_DROPPED)

    valuations = pricing_engine.value_portfolio(portfolio, market)
    market_value = float(sum(v.market_value for v in valuations))
    if market_value == 0.0 or not math.isfinite(market_value):
        raise ValueError("market_value must be a non-zero finite number")

    pnl = _period_pnl(portfolio, pricing_engine, market, sliced, methodology)
    if len(pnl) != sliced.n_observations:
        raise ValueError("P&L length does not match sliced panel")
    returns = np.asarray(pnl, dtype=float) / market_value
    n = int(returns.size)
    dates = list(sliced.dates)
    wealth = np.cumprod(1.0 + returns)
    terminal = float(wealth[-1])
    if terminal <= 0.0:
        raise ValueError("terminal wealth must be positive to annualize via CAGR")

    ppy = float(convention.periods_per_year)
    cumulative_return = terminal - 1.0
    annualized_return = terminal ** (ppy / n) - 1.0

    if n < 2:
        annualized_volatility = 0.0
        notes.append(_NOTE_SHORT_VOL)
    else:
        annualized_volatility = float(
            np.std(returns, ddof=convention.sample_ddof) * math.sqrt(ppy)
        )

    if annualized_volatility == 0.0 or not math.isfinite(annualized_volatility):
        sharpe = None
        notes.append(_NOTE_ZERO_VOL)
    else:
        sharpe = (annualized_return - float(risk_free_rate)) / annualized_volatility

    peak = np.maximum.accumulate(np.concatenate([[1.0], wealth]))[1:]
    drawdown = wealth / peak - 1.0
    max_drawdown = float(drawdown.min())

    if n >= rolling_window:
        rolling = [
            DatedValue(
                as_of=dates[i],
                value=float(
                    np.std(returns[i - rolling_window + 1 : i + 1], ddof=convention.sample_ddof)
                    * math.sqrt(ppy)
                ),
            )
            for i in range(rolling_window - 1, n)
        ]
    else:
        rolling = []
        notes.append(_NOTE_ROLLING)

    window = min(period_window, n)
    scored = [
        PeriodWindow(
            start=dates[i],
            end=dates[i + window - 1],
            return_fraction=_window_compound(returns, i, window),
        )
        for i in range(n - window + 1)
    ]
    best = max(scored, key=lambda item: item.return_fraction)
    worst = min(scored, key=lambda item: item.return_fraction)

    engine = HistoricalRiskEngine(
        factor_panel=sliced,
        methodology=methodology,
        observations=sliced.n_observations,
    )
    summary = engine.calculate(
        portfolio,
        pricing_engine,
        methodology=methodology,
        market=market,
    )

    def _series(values: np.ndarray) -> list[DatedValue]:
        return [DatedValue(as_of=as_of, value=float(value)) for as_of, value in zip(dates, values)]

    benchmark = None
    if include_benchmark:
        benchmark = _canonical_benchmark_relative_risk(
            sliced=sliced,
            portfolio_dates=dates,
            portfolio_returns=returns,
            portfolio_market_value=market_value,
            pricing_engine=pricing_engine,
            market=market,
            methodology=methodology,
            convention=convention,
        )

    return HistoricalAnalyticsResult(
        portfolio_id=portfolio.id,
        portfolio_version=portfolio.version,
        historical_dataset_id=historical_dataset_id,
        historical_dataset_version=historical_dataset_version,
        market_snapshot_id=market.id,
        start=start,
        end=end,
        frequency=frequency,
        methodology=methodology,
        annualization=convention,
        risk_free_rate=float(risk_free_rate),
        market_value=market_value,
        cumulative_return=float(cumulative_return),
        annualized_return=float(annualized_return),
        annualized_volatility=float(annualized_volatility),
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        var_95=float(summary.var_95),
        var_99=float(summary.var_99),
        expected_shortfall_99=float(summary.expected_shortfall_99),
        wealth=_series(wealth),
        cumulative=_series(wealth - 1.0),
        drawdown=_series(drawdown),
        period_returns=_series(returns),
        rolling_volatility=rolling,
        best_period=best,
        worst_period=worst,
        notes=notes,
        dropped_dates=missing,
        observation_count=n,
        units={
            "returns": "fraction",
            "drawdown": "fraction_of_peak_negative",
            "volatility": "annualized_fraction",
            "var_es": "currency_loss",
            "wealth": "end_of_period_index",
        },
        data_source_label=data_source_label(
            historical_dataset_id, historical_dataset_version
        )
        or f"Synthetic replay · {historical_dataset_id}/{historical_dataset_version}",
        benchmark=benchmark,
    )
