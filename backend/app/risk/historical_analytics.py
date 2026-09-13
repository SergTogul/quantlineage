"""Deterministic historical analytics from a frozen factor panel (Wave B G1).

Period P&L uses the same panel approximations as ``HistoricalRiskEngine``.
Portfolio VaR/ES are the engine's ``calculate()`` numbers on the sliced
window — this module does not reimplement quantile / tail math.

Units:
- period / cumulative / annualized returns: fraction (0.01 = 1%)
- drawdown: fraction of peak, ≤ 0, with implicit start NAV = 1
- volatility / Sharpe: annualized fraction; Sharpe undefined at zero vol
- VaR / ES: currency loss (≥ 0), HistoricalRiskEngine convention
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    FiniteFloat,
    FiniteInputMixin,
    MarketSnapshot,
    Portfolio,
    VaRMethodology,
)
from app.interfaces.pricing import PricingEngine
from app.risk.factor_panel import HistoricalFactorPanel
from app.risk.factor_types import RiskFactor
from app.risk.historical import (
    HistoricalRiskEngine,
    approximate_pnl_from_panel,
    full_revaluation_pnl_from_panel,
)

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
    )
