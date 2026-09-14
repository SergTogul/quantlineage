"""Wave B G1/G2 — historical analytics and canonical SPY relative risk.

Conventions (tested):
- Period returns are fractions (0.01 = 1%), ``pnl / market_value``.
- Wealth is an end-of-period index compounded from 1.0 before the first return.
- Drawdown is ``W_t / peak_{s<=t}(W_s) - 1`` with implicit ``W_0 = 1`` (≤ 0).
- Annualized return is CAGR: ``W_n ** (periods_per_year / n) - 1``.
- Annualized vol is sample std (ddof from convention) × sqrt(periods_per_year).
- Sharpe is ``(ann_return - rf) / ann_vol``; undefined when vol is 0.
- Portfolio VaR/ES come from ``HistoricalRiskEngine.calculate`` on the sliced
  panel (currency loss, ``max(0, quantile)``) — not a second quantile module.
- Canonical benchmark is Wave A ``equity:US:SPY`` / ``EquitySpot:SPY``.
- Alignment is calendar-date intersection (no positional zip, no ffill).
- Beta is ``cov(r_p, r_b) / var(r_b)`` (same sample ddof); fail closed if
  ``var(r_b)=0``. Tracking error is sample std of ``r_p - r_b`` × sqrt(ppy).
- Excess return is ``W_p - W_b`` (fraction). Relative drawdown is drawdown of
  ``W_p / W_b`` with implicit start 1 (≤ 0).
- Benchmark VaR/ES are engine numbers on a same-notional SPY book.
- DAILY missing weekdays: drop with note or fail closed; never silent ffill.
- Tolerances: 1e-12 for linear cash-equity identities; 1e-10 for CAGR/vol.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_panel import HistoricalFactorPanel
from app.risk.factor_types import EquitySpot
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_analytics import (
    WAVE_A_BENCHMARK_FACTOR,
    WAVE_A_BENCHMARK_INSTRUMENT_ID,
    AnalyticsFrequency,
    AnnualizationConvention,
    MissingDatePolicy,
    align_dated_series,
    compute_historical_analytics,
)

AAA = EquitySpot("AAA")
SPY = EquitySpot("SPY")
PRICING = BuiltinPricingEngine()
DATASET_ID = "test-frozen-history"
DATASET_VERSION = "v1"
ANN = AnnualizationConvention(
    periods_per_year=252,
    return_method="cagr",
    volatility_method="sqrt_time",
    sample_ddof=1,
)
TOL = 1e-12
TOL_ANN = 1e-10


def _weekdays(n: int, start: date = date(2024, 1, 2)) -> list[date]:
    out: list[date] = []
    day = start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def _equity_book(*, quantity: float = 10.0, spot: float = 100.0) -> tuple[Portfolio, MarketSnapshot]:
    book = Portfolio(
        id="eq-aaa",
        name="AAA cash equity",
        version=3,
        positions=[EquityPosition(type="equity", id="aaa", symbol="AAA", quantity=quantity)],
    )
    market = MarketSnapshot(
        id="snap-aaa",
        as_of=date(2024, 1, 2),
        equity_spots={"AAA": spot},
        rates={"USD": 0.04},
    )
    return book, market


def _panel(dates: list[date], returns: list[float]) -> HistoricalFactorPanel:
    return HistoricalFactorPanel.from_pairs(
        dates=dates,
        rows=[[(AAA, r)] for r in returns],
    )


def _analyze(
    dates: list[date],
    returns: list[float],
    *,
    start: date | None = None,
    end: date | None = None,
    rolling_window: int = 21,
    missing_date_policy: MissingDatePolicy = MissingDatePolicy.DROP_WITH_NOTE,
    methodology: VaRMethodology = VaRMethodology.LINEAR,
    risk_free_rate: float = 0.0,
    period_window: int = 1,
):
    book, market = _equity_book()
    panel = _panel(dates, returns)
    return compute_historical_analytics(
        portfolio=book,
        pricing_engine=PRICING,
        market=market,
        panel=panel,
        start=start or dates[0],
        end=end or dates[-1],
        frequency=AnalyticsFrequency.DAILY,
        methodology=methodology,
        annualization=ANN,
        historical_dataset_id=DATASET_ID,
        historical_dataset_version=DATASET_VERSION,
        rolling_window=rolling_window,
        risk_free_rate=risk_free_rate,
        missing_date_policy=missing_date_policy,
        period_window=period_window,
    )


def test_constant_returns_compound_wealth_and_cagr():
    dates = _weekdays(5)
    daily = 0.01
    result = _analyze(dates, [daily] * 5, rolling_window=21)

    wealth = [(1.0 + daily) ** (i + 1) for i in range(5)]
    assert [p.value for p in result.wealth] == pytest.approx(wealth, abs=TOL)
    assert [p.as_of for p in result.wealth] == dates
    assert result.cumulative_return == pytest.approx(wealth[-1] - 1.0, abs=TOL)
    expected_cagr = wealth[-1] ** (252 / 5) - 1.0
    assert result.annualized_return == pytest.approx(expected_cagr, abs=TOL_ANN)
    assert result.annualization.periods_per_year == 252
    assert result.annualization.return_method == "cagr"
    assert result.frequency is AnalyticsFrequency.DAILY
    assert result.methodology is VaRMethodology.LINEAR
    assert result.portfolio_id == "eq-aaa"
    assert result.portfolio_version == 3
    assert result.historical_dataset_id == DATASET_ID
    assert result.historical_dataset_version == DATASET_VERSION
    assert result.market_snapshot_id == "snap-aaa"
    assert result.start == dates[0]
    assert result.end == dates[-1]


def test_zero_vol_constant_returns_leaves_sharpe_undefined():
    dates = _weekdays(8)
    result = _analyze(dates, [0.002] * 8, rolling_window=21)
    assert result.annualized_volatility == pytest.approx(0.0, abs=TOL)
    assert result.sharpe is None
    assert any("zero_volatility" in n for n in result.notes)


def test_known_drawdown_uses_implicit_unit_nav_peak():
    dates = _weekdays(4)
    rets = [0.0, -0.10, -0.10, 0.05]
    result = _analyze(dates, rets, rolling_window=21)
    wealth = np.cumprod(1.0 + np.asarray(rets, dtype=float))
    peak = np.maximum.accumulate(np.concatenate([[1.0], wealth]))[1:]
    drawdown = wealth / peak - 1.0
    assert [p.value for p in result.drawdown] == pytest.approx(drawdown.tolist(), abs=TOL)
    assert result.max_drawdown == pytest.approx(float(drawdown.min()), abs=TOL)
    assert result.max_drawdown == pytest.approx(-0.19, abs=TOL)
    assert result.max_drawdown < 0.0


def test_known_sharpe_matches_cagr_over_sample_vol():
    dates = _weekdays(4)
    rets = np.array([0.01, 0.02, 0.015, 0.005], dtype=float)
    result = _analyze(dates, rets.tolist(), rolling_window=21)
    wealth = float(np.prod(1.0 + rets))
    ann_ret = wealth ** (252 / 4) - 1.0
    ann_vol = float(np.std(rets, ddof=1) * np.sqrt(252))
    sharpe = ann_ret / ann_vol
    assert result.annualized_return == pytest.approx(ann_ret, abs=TOL_ANN)
    assert result.annualized_volatility == pytest.approx(ann_vol, abs=TOL_ANN)
    assert result.sharpe == pytest.approx(sharpe, abs=TOL_ANN)
    assert result.risk_free_rate == pytest.approx(0.0, abs=TOL)


def test_var_es_tail_reuses_historical_risk_engine():
    dates = _weekdays(20)
    rets = [0.01] * 16 + [-0.04, -0.08, -0.12, 0.02]
    book, market = _equity_book()
    panel = _panel(dates, rets)
    result = compute_historical_analytics(
        portfolio=book,
        pricing_engine=PRICING,
        market=market,
        panel=panel,
        start=dates[0],
        end=dates[-1],
        frequency=AnalyticsFrequency.DAILY,
        methodology=VaRMethodology.LINEAR,
        annualization=ANN,
        historical_dataset_id=DATASET_ID,
        historical_dataset_version=DATASET_VERSION,
        rolling_window=5,
    )
    engine = HistoricalRiskEngine(
        factor_panel=panel,
        methodology=VaRMethodology.LINEAR,
        observations=panel.n_observations,
    )
    summary = engine.calculate(book, PRICING, methodology=VaRMethodology.LINEAR, market=market)
    assert result.var_95 == pytest.approx(summary.var_95, abs=TOL)
    assert result.var_99 == pytest.approx(summary.var_99, abs=TOL)
    assert result.expected_shortfall_99 == pytest.approx(summary.expected_shortfall_99, abs=TOL)
    assert result.var_99 >= result.var_95 >= 0.0
    assert result.expected_shortfall_99 >= result.var_99
    mv = 10.0 * 100.0
    pnl = mv * np.asarray(rets, dtype=float)
    losses = -pnl
    assert result.var_95 == pytest.approx(float(max(0.0, np.quantile(losses, 0.95))), abs=TOL)
    assert result.units["var_es"] == "currency_loss"


def test_short_window_one_observation_defines_return_not_sample_vol():
    dates = _weekdays(1)
    result = _analyze(dates, [0.02], rolling_window=21)
    assert result.cumulative_return == pytest.approx(0.02, abs=TOL)
    assert result.annualized_return == pytest.approx((1.02) ** 252 - 1.0, abs=TOL_ANN)
    assert result.annualized_volatility == pytest.approx(0.0, abs=TOL)
    assert result.sharpe is None
    assert result.rolling_volatility == []
    assert any("n_lt_2" in n for n in result.notes)
    assert len(result.wealth) == 1


def test_missing_weekday_drop_with_note_does_not_ffill():
    # 2024-01-02 Tue … 2024-01-05 Fri; skip Wednesday 2024-01-03.
    dates = [date(2024, 1, 2), date(2024, 1, 4), date(2024, 1, 5)]
    rets = [0.01, 0.02, 0.03]
    result = _analyze(
        dates,
        rets,
        start=date(2024, 1, 2),
        end=date(2024, 1, 5),
        missing_date_policy=MissingDatePolicy.DROP_WITH_NOTE,
        rolling_window=21,
    )
    assert [p.as_of for p in result.wealth] == dates
    assert date(2024, 1, 3) not in {p.as_of for p in result.wealth}
    assert date(2024, 1, 3) in result.dropped_dates
    assert result.period_returns[1].value == pytest.approx(0.02, abs=TOL)
    assert result.period_returns[1].as_of == date(2024, 1, 4)
    # No silent ffill: Wednesday is absent, Thursday keeps its own return.
    assert all(p.as_of != date(2024, 1, 3) for p in result.period_returns)


def test_missing_weekday_fail_closed():
    dates = [date(2024, 1, 2), date(2024, 1, 4), date(2024, 1, 5)]
    with pytest.raises(ValueError, match="missing"):
        _analyze(
            dates,
            [0.01, 0.02, 0.03],
            start=date(2024, 1, 2),
            end=date(2024, 1, 5),
            missing_date_policy=MissingDatePolicy.FAIL_CLOSED,
            rolling_window=21,
        )


def test_best_and_worst_periods_are_single_observation_windows():
    dates = _weekdays(4)
    rets = [0.01, -0.04, 0.03, 0.00]
    result = _analyze(dates, rets, rolling_window=21, period_window=1)
    assert result.best_period.start == dates[2]
    assert result.best_period.end == dates[2]
    assert result.best_period.return_fraction == pytest.approx(0.03, abs=TOL)
    assert result.worst_period.start == dates[1]
    assert result.worst_period.end == dates[1]
    assert result.worst_period.return_fraction == pytest.approx(-0.04, abs=TOL)


def test_rolling_vol_uses_sample_std_times_sqrt_periods_per_year():
    dates = _weekdays(4)
    rets = [0.01, 0.02, 0.03, 0.04]
    result = _analyze(dates, rets, rolling_window=3)
    expected = [
        float(np.std(rets[0:3], ddof=1) * np.sqrt(252)),
        float(np.std(rets[1:4], ddof=1) * np.sqrt(252)),
    ]
    assert [p.as_of for p in result.rolling_volatility] == dates[2:]
    assert [p.value for p in result.rolling_volatility] == pytest.approx(expected, abs=TOL_ANN)


def test_annualization_periods_per_year_scales_cagr_and_vol():
    dates = _weekdays(4)
    rets = [0.01, 0.02, 0.015, 0.005]
    book, market = _equity_book()
    monthly = AnnualizationConvention(
        periods_per_year=12,
        return_method="cagr",
        volatility_method="sqrt_time",
        sample_ddof=1,
    )
    result = compute_historical_analytics(
        portfolio=book,
        pricing_engine=PRICING,
        market=market,
        panel=_panel(dates, rets),
        start=dates[0],
        end=dates[-1],
        frequency=AnalyticsFrequency.DAILY,
        methodology=VaRMethodology.LINEAR,
        annualization=monthly,
        historical_dataset_id=DATASET_ID,
        historical_dataset_version=DATASET_VERSION,
        rolling_window=21,
    )
    arr = np.asarray(rets, dtype=float)
    wealth = float(np.prod(1.0 + arr))
    assert result.annualized_return == pytest.approx(wealth ** (12 / 4) - 1.0, abs=TOL_ANN)
    assert result.annualized_volatility == pytest.approx(
        float(np.std(arr, ddof=1) * np.sqrt(12)), abs=TOL_ANN
    )
    assert result.annualization.periods_per_year == 12


def test_api_echoes_frozen_identities_without_provider_http():
    from fastapi.testclient import TestClient
    from tests.market_fixtures import FixedMarketProvider, equity_spot_market

    from app.main import app
    from app.risk.historical_data import DEMO_MULTI_FACTOR_DATASET_ID
    from app.services.risk_factories import DEFAULT_HISTORICAL_DATASET_VERSION

    book = Portfolio(
        id="api-aaa",
        name="API AAA",
        version=2,
        positions=[EquityPosition(type="equity", id="nvda", symbol="NVDA", quantity=10)],
    )
    payload = {
        "portfolio": book.model_dump(mode="json"),
        "start": "2022-01-03",
        "end": "2022-01-07",
        "frequency": "DAILY",
        "methodology": "LINEAR",
        "annualization": {
            "periods_per_year": 252,
            "return_method": "cagr",
            "volatility_method": "sqrt_time",
            "sample_ddof": 1,
        },
        "historical_dataset_id": DEMO_MULTI_FACTOR_DATASET_ID,
        "historical_dataset_version": DEFAULT_HISTORICAL_DATASET_VERSION,
        "rolling_window": 21,
        "missing_date_policy": "drop_with_note",
    }
    with TestClient(app) as client:
        svc = client.app.state.portfolio_service
        previous = svc.market_data
        svc.market_data = FixedMarketProvider(
            equity_spot_market("NVDA", 190.0, market_id="snap-nvda")
        )
        try:
            resp = client.post("/api/v1/risk/historical-analytics", json=payload)
        finally:
            svc.market_data = previous
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["portfolio_id"] == "api-aaa"
    assert body["portfolio_version"] == 2
    assert body["historical_dataset_id"] == DEMO_MULTI_FACTOR_DATASET_ID
    assert body["historical_dataset_version"] == DEFAULT_HISTORICAL_DATASET_VERSION
    assert body["market_snapshot_id"] == "snap-nvda"
    assert body["start"] == "2022-01-03"
    assert body["end"] == "2022-01-07"
    assert body["frequency"] == "DAILY"
    assert body["methodology"] == "LINEAR"
    assert body["annualization"]["periods_per_year"] == 252
    assert body["annualization"]["return_method"] == "cagr"
    assert "wealth" in body and len(body["wealth"]) >= 1
    assert body["units"]["var_es"] == "currency_loss"
    assert body["data_source_label"].startswith("Synthetic replay")
    assert body.get("benchmark") is None


def test_api_canonical_spy_benchmark_without_provider_http():
    from fastapi.testclient import TestClient
    from tests.market_fixtures import FixedMarketProvider

    from app.domain.models import MarketSnapshot
    from app.main import app
    from app.risk.historical_data import DEMO_MULTI_FACTOR_DATASET_ID
    from app.services.risk_factories import DEFAULT_HISTORICAL_DATASET_VERSION

    book = Portfolio(
        id="api-aaa",
        name="API AAA",
        version=2,
        positions=[EquityPosition(type="equity", id="nvda", symbol="NVDA", quantity=10)],
    )
    payload = {
        "portfolio": book.model_dump(mode="json"),
        "start": "2022-01-03",
        "end": "2022-01-07",
        "frequency": "DAILY",
        "methodology": "LINEAR",
        "annualization": {
            "periods_per_year": 252,
            "return_method": "cagr",
            "volatility_method": "sqrt_time",
            "sample_ddof": 1,
        },
        "historical_dataset_id": DEMO_MULTI_FACTOR_DATASET_ID,
        "historical_dataset_version": DEFAULT_HISTORICAL_DATASET_VERSION,
        "rolling_window": 21,
        "missing_date_policy": "drop_with_note",
        "include_benchmark": True,
    }
    market = MarketSnapshot(
        id="snap-nvda-spy",
        as_of=date(2022, 1, 3),
        equity_spots={"NVDA": 190.0, "SPY": 400.0},
        rates={"USD": 0.04},
    )
    with TestClient(app) as client:
        svc = client.app.state.portfolio_service
        previous = svc.market_data
        svc.market_data = FixedMarketProvider(market)
        try:
            resp = client.post("/api/v1/risk/historical-analytics", json=payload)
        finally:
            svc.market_data = previous
    assert resp.status_code == 200, resp.text
    body = resp.json()
    bench = body["benchmark"]
    assert bench["instrument_id"] == "equity:US:SPY"
    assert bench["factor_column"] == "EquitySpot:SPY"
    assert bench["units"]["beta"] == "dimensionless"
    assert bench["units"]["tracking_error"] == "annualized_fraction"
    assert bench["units"]["excess_return"] == "fraction"
    assert bench["units"]["var_es"] == "currency_loss"
    assert bench["observation_count"] >= 2


def test_range_slice_does_not_mutate_source_panel():
    dates = _weekdays(5)
    panel = _panel(dates, [0.01] * 5)
    original = tuple(panel.dates)
    book, market = _equity_book()
    compute_historical_analytics(
        portfolio=book,
        pricing_engine=PRICING,
        market=market,
        panel=panel,
        start=dates[1],
        end=dates[3],
        frequency=AnalyticsFrequency.DAILY,
        methodology=VaRMethodology.LINEAR,
        annualization=ANN,
        historical_dataset_id=DATASET_ID,
        historical_dataset_version=DATASET_VERSION,
        rolling_window=21,
    )
    assert panel.dates == original
    assert len(panel.dates) == 5


def _equity_book_with_spy(
    *, quantity: float = 10.0, spot: float = 100.0, spy_spot: float = 400.0
) -> tuple[Portfolio, MarketSnapshot]:
    book = Portfolio(
        id="eq-aaa",
        name="AAA cash equity",
        version=3,
        positions=[EquityPosition(type="equity", id="aaa", symbol="AAA", quantity=quantity)],
    )
    market = MarketSnapshot(
        id="snap-aaa",
        as_of=date(2024, 1, 2),
        equity_spots={"AAA": spot, "SPY": spy_spot},
        rates={"USD": 0.04},
    )
    return book, market


def _panel_with_spy(
    dates: list[date], aaa_returns: list[float], spy_returns: list[float]
) -> HistoricalFactorPanel:
    return HistoricalFactorPanel.from_pairs(
        dates=dates,
        rows=[[(AAA, a), (SPY, s)] for a, s in zip(aaa_returns, spy_returns, strict=True)],
    )


def _analyze_vs_spy(
    dates: list[date],
    aaa_returns: list[float],
    spy_returns: list[float],
    *,
    start: date | None = None,
    end: date | None = None,
    rolling_window: int = 21,
    missing_date_policy: MissingDatePolicy = MissingDatePolicy.DROP_WITH_NOTE,
    methodology: VaRMethodology = VaRMethodology.LINEAR,
    include_benchmark: bool = True,
):
    book, market = _equity_book_with_spy()
    panel = _panel_with_spy(dates, aaa_returns, spy_returns)
    return compute_historical_analytics(
        portfolio=book,
        pricing_engine=PRICING,
        market=market,
        panel=panel,
        start=start or dates[0],
        end=end or dates[-1],
        frequency=AnalyticsFrequency.DAILY,
        methodology=methodology,
        annualization=ANN,
        historical_dataset_id=DATASET_ID,
        historical_dataset_version=DATASET_VERSION,
        rolling_window=rolling_window,
        missing_date_policy=missing_date_policy,
        include_benchmark=include_benchmark,
    )


def test_identical_series_beta_one_tracking_error_zero():
    dates = _weekdays(5)
    rets = [0.01, -0.02, 0.015, 0.005, 0.02]
    result = _analyze_vs_spy(dates, rets, rets)
    bench = result.benchmark
    assert bench is not None
    assert bench.instrument_id == WAVE_A_BENCHMARK_INSTRUMENT_ID
    assert bench.factor_column == "EquitySpot:SPY"
    assert WAVE_A_BENCHMARK_FACTOR == SPY
    assert bench.beta == pytest.approx(1.0, abs=TOL)
    assert bench.tracking_error == pytest.approx(0.0, abs=TOL)
    assert bench.correlation == pytest.approx(1.0, abs=TOL)
    assert bench.excess_return == pytest.approx(0.0, abs=TOL)
    assert bench.relative_drawdown == pytest.approx(0.0, abs=TOL)
    assert bench.cumulative_return == pytest.approx(result.cumulative_return, abs=TOL)


def test_uncorrelated_series_beta_near_zero():
    dates = _weekdays(4)
    aaa = [0.01, 0.01, -0.01, -0.01]
    spy = [0.01, -0.01, 0.01, -0.01]
    result = _analyze_vs_spy(dates, aaa, spy)
    assert result.benchmark is not None
    assert result.benchmark.beta == pytest.approx(0.0, abs=TOL)
    assert result.benchmark.correlation == pytest.approx(0.0, abs=TOL)


def test_shifted_dates_are_not_silently_matched():
    port_dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    port_rets = [0.10, 0.01, -0.05]
    bench_dates = [date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)]
    bench_rets = [0.10, 0.01, -0.05]
    # Positional zip of the raw series is identical (beta would be 1, TE 0).
    assert port_rets == bench_rets
    aligned_dates, r_p, r_b = align_dated_series(port_dates, port_rets, bench_dates, bench_rets)
    assert aligned_dates == [date(2024, 1, 3), date(2024, 1, 4)]
    assert list(r_p) == pytest.approx([0.01, -0.05], abs=TOL)
    assert list(r_b) == pytest.approx([0.10, 0.01], abs=TOL)
    var_b = float(np.var(r_b, ddof=1))
    cov = float(np.cov(r_p, r_b, ddof=1)[0, 1])
    beta = cov / var_b
    tracking_error = float(np.std(r_p - r_b, ddof=1) * np.sqrt(252))
    assert beta != pytest.approx(1.0, abs=1e-6)
    assert tracking_error != pytest.approx(0.0, abs=1e-6)


def test_insufficient_overlap_fails_closed():
    with pytest.raises(ValueError, match="insufficient"):
        align_dated_series(
            [date(2024, 1, 2), date(2024, 1, 3)],
            [0.01, 0.02],
            [date(2024, 1, 4), date(2024, 1, 5)],
            [0.03, 0.04],
        )
    dates = _weekdays(1)
    with pytest.raises(ValueError, match="insufficient"):
        _analyze_vs_spy(dates, [0.02], [0.01], rolling_window=21)


def test_missing_spy_factor_fails_closed():
    dates = _weekdays(4)
    book, market = _equity_book_with_spy()
    with pytest.raises(ValueError, match="EquitySpot:SPY"):
        compute_historical_analytics(
            portfolio=book,
            pricing_engine=PRICING,
            market=market,
            panel=_panel(dates, [0.01] * 4),
            start=dates[0],
            end=dates[-1],
            frequency=AnalyticsFrequency.DAILY,
            methodology=VaRMethodology.LINEAR,
            annualization=ANN,
            historical_dataset_id=DATASET_ID,
            historical_dataset_version=DATASET_VERSION,
            rolling_window=21,
            include_benchmark=True,
        )


def test_percent_fraction_units_beta_te_excess_not_scaled_by_100():
    dates = _weekdays(5)
    aaa = [0.01, 0.02, 0.015, 0.005, 0.012]
    spy = [0.00, 0.01, 0.005, -0.005, 0.002]
    result = _analyze_vs_spy(dates, aaa, spy)
    bench = result.benchmark
    assert bench is not None
    expected_excess = float(np.prod(1.0 + np.asarray(aaa)) - np.prod(1.0 + np.asarray(spy)))
    assert bench.excess_return == pytest.approx(expected_excess, abs=TOL)
    assert abs(bench.excess_return) < 1.0
    assert bench.units["beta"] == "dimensionless"
    assert bench.units["tracking_error"] == "annualized_fraction"
    assert bench.units["excess_return"] == "fraction"
    active = np.asarray(aaa, dtype=float) - np.asarray(spy, dtype=float)
    expected_te = float(np.std(active, ddof=1) * np.sqrt(252))
    assert bench.tracking_error == pytest.approx(expected_te, abs=TOL_ANN)
    assert bench.tracking_error < 1.0


def test_benchmark_var_es_reuses_historical_risk_engine_on_spy_book():
    dates = _weekdays(20)
    aaa = [0.01] * 16 + [-0.04, -0.08, -0.12, 0.02]
    spy = [0.005] * 16 + [-0.02, -0.03, -0.06, 0.01]
    book, market = _equity_book_with_spy()
    panel = _panel_with_spy(dates, aaa, spy)
    result = compute_historical_analytics(
        portfolio=book,
        pricing_engine=PRICING,
        market=market,
        panel=panel,
        start=dates[0],
        end=dates[-1],
        frequency=AnalyticsFrequency.DAILY,
        methodology=VaRMethodology.LINEAR,
        annualization=ANN,
        historical_dataset_id=DATASET_ID,
        historical_dataset_version=DATASET_VERSION,
        rolling_window=5,
        include_benchmark=True,
    )
    assert result.benchmark is not None
    spy_spot = float(market.equity_spots["SPY"])
    quantity = result.market_value / spy_spot
    spy_book = Portfolio(
        id="benchmark:equity:US:SPY",
        name="Wave A SPY benchmark",
        version=1,
        positions=[EquityPosition(type="equity", id="spy", symbol="SPY", quantity=quantity)],
    )
    engine = HistoricalRiskEngine(
        factor_panel=panel,
        methodology=VaRMethodology.LINEAR,
        observations=panel.n_observations,
    )
    summary = engine.calculate(spy_book, PRICING, methodology=VaRMethodology.LINEAR, market=market)
    assert result.benchmark.var_95 == pytest.approx(summary.var_95, abs=TOL)
    assert result.benchmark.var_99 == pytest.approx(summary.var_99, abs=TOL)
    assert result.benchmark.expected_shortfall_99 == pytest.approx(
        summary.expected_shortfall_99, abs=TOL
    )
    assert result.benchmark.var_99 >= result.benchmark.var_95 >= 0.0
    assert result.benchmark.units["var_es"] == "currency_loss"


def test_zero_benchmark_variance_fails_closed():
    dates = _weekdays(4)
    with pytest.raises(ValueError, match="var\\(r_b\\)|benchmark variance"):
        _analyze_vs_spy(dates, [0.01, -0.02, 0.03, 0.00], [0.0, 0.0, 0.0, 0.0])


def test_g1_without_benchmark_flag_leaves_nested_object_none():
    dates = _weekdays(5)
    result = _analyze(dates, [0.01] * 5, rolling_window=21)
    assert result.benchmark is None


def test_beta_denominator_is_cov_over_var_benchmark_not_inverted():
    """Hostile: beta = cov(r_p, r_b) / var(r_b). Doubled portfolio returns → 2, not 0.5."""
    dates = _weekdays(6)
    spy = [0.01, -0.02, 0.015, 0.005, -0.01, 0.02]
    aaa = [2.0 * x for x in spy]
    result = _analyze_vs_spy(dates, aaa, spy)
    bench = result.benchmark
    assert bench is not None
    r_p = np.asarray(aaa, dtype=float)
    r_b = np.asarray(spy, dtype=float)
    cov = float(np.cov(r_p, r_b, ddof=1)[0, 1])
    var_b = float(np.var(r_b, ddof=1))
    var_p = float(np.var(r_p, ddof=1))
    assert bench.beta == pytest.approx(2.0, abs=TOL)
    assert bench.beta == pytest.approx(cov / var_b, abs=TOL)
    inverted = cov / var_p
    assert inverted == pytest.approx(0.5, abs=TOL)
    assert bench.beta != pytest.approx(inverted, abs=1e-6)


def test_tracking_error_annualizes_std_times_sqrt_periods_per_year():
    """Hostile: TE is G1 sample std × sqrt(ppy), not × ppy and not stuck at 252."""
    dates = _weekdays(4)
    aaa = [0.02, 0.01, -0.01, 0.00]
    spy = [0.00, 0.01, 0.01, -0.01]
    book, market = _equity_book_with_spy()
    monthly = AnnualizationConvention(
        periods_per_year=12,
        return_method="cagr",
        volatility_method="sqrt_time",
        sample_ddof=1,
    )
    result = compute_historical_analytics(
        portfolio=book,
        pricing_engine=PRICING,
        market=market,
        panel=_panel_with_spy(dates, aaa, spy),
        start=dates[0],
        end=dates[-1],
        frequency=AnalyticsFrequency.DAILY,
        methodology=VaRMethodology.LINEAR,
        annualization=monthly,
        historical_dataset_id=DATASET_ID,
        historical_dataset_version=DATASET_VERSION,
        rolling_window=21,
        include_benchmark=True,
    )
    assert result.benchmark is not None
    active = np.asarray(aaa, dtype=float) - np.asarray(spy, dtype=float)
    expected_12 = float(np.std(active, ddof=1) * np.sqrt(12))
    expected_252 = float(np.std(active, ddof=1) * np.sqrt(252))
    wrong_linear = float(np.std(active, ddof=1) * 12)
    assert result.benchmark.tracking_error == pytest.approx(expected_12, abs=TOL_ANN)
    assert result.benchmark.tracking_error != pytest.approx(expected_252, abs=1e-6)
    assert result.benchmark.tracking_error != pytest.approx(wrong_linear, abs=1e-6)
    assert result.annualization.periods_per_year == 12
