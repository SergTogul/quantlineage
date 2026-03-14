"""Exact hand-computed historical VaR and Expected Shortfall goldens.

Methodology pinned by these tests:
- Loss = -P&L.
- ``numpy.quantile`` uses its default linear method: index = q * (n - 1).
- VaR and ES are floored at zero.
- Historical ES is the mean of losses greater than or equal to VaR.

The expected values below are literal hand calculations, not values captured
from the production engines.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.var import VaRAnalytics

ABS_TOL = 1e-12
PRICING = BuiltinPricingEngine()
UNIT_BOOK = Portfolio(
    id="unit",
    name="unit",
    positions=[
        EquityPosition(
            type="equity",
            id="unit",
            symbol="UNIT",
            quantity=1.0,
            price=1.0,
        )
    ],
)
UNIT_MARKET = MarketSnapshot(id="unit", equity_spots={"UNIT": 1.0})


def dataset_from_pnl(pnl: np.ndarray) -> ArrayHistoricalDataset:
    """Feed exact P&L through a unit-cash-delta equity in LINEAR mode."""
    pnl = np.asarray(pnl, dtype=float)
    zeros = np.zeros_like(pnl)
    return ArrayHistoricalDataset(
        FactorObservationSeries(
            equity_returns=pnl,
            vol_moves=zeros,
            rate_moves_bps=zeros,
            fx_returns=zeros,
        )
    )


def historical_result(pnl: np.ndarray) -> dict:
    return HistoricalRiskEngine(
        dataset=dataset_from_pnl(pnl),
        methodology=VaRMethodology.LINEAR,
    ).calculate(UNIT_BOOK, PRICING, market=UNIT_MARKET)


def historical_method(pnl: np.ndarray, confidence: float):
    report = VaRAnalytics(
        dataset=dataset_from_pnl(pnl),
        methodology=VaRMethodology.LINEAR,
    ).report(
        UNIT_BOOK,
        PRICING,
        confidence=confidence,
        methodology=VaRMethodology.LINEAR,
        market=UNIT_MARKET,
    )
    return next(method for method in report.methods if method.method == "historical")


@pytest.mark.parametrize(
    ("case", "pnl", "var95", "var99", "es95", "es99"),
    [
        # A: q95 index 18.05 -> 19.05; q99 index 18.81 -> 19.81.
        ("A", -np.arange(1.0, 21.0), 19.05, 19.81, 20.0, 20.0),
        # B: every loss quantile is negative, so VaR/ES floor to zero.
        ("B", np.arange(1.0, 21.0), 0.0, 0.0, 0.0, 0.0),
        ("C", np.zeros(10), 0.0, 0.0, 0.0, 0.0),
        # D: q95 index 3.8 -> 5 + 0.8 * 15; q99 index 3.96.
        ("D", np.array([10.0, 5.0, 0.0, -5.0, -20.0]), 17.0, 19.4, 20.0, 20.0),
        ("E", np.array([-10.0]), 10.0, 10.0, 10.0, 10.0),
        # F: q95 index 0.95 -> 1 + 0.95 * 99; q99 index 0.99.
        ("F", np.array([-1.0, -100.0]), 95.05, 99.01, 100.0, 100.0),
        # G: q95 index 2.85 -> 3.85; q99 index 2.97 -> 3.97.
        ("G", np.array([-1.0, -2.0, -3.0, -4.0]), 3.85, 3.97, 4.0, 4.0),
    ],
)
def test_exact_hand_computed_var_es_goldens(
    case: str,
    pnl: np.ndarray,
    var95: float,
    var99: float,
    es95: float,
    es99: float,
) -> None:
    result = historical_result(pnl)
    analytics95 = historical_method(pnl, 0.95)
    analytics99 = historical_method(pnl, 0.99)

    assert result["var_95"] == pytest.approx(var95, rel=0, abs=ABS_TOL), case
    assert result["var_99"] == pytest.approx(var99, rel=0, abs=ABS_TOL), case
    assert result["expected_shortfall_99"] == pytest.approx(es99, rel=0, abs=ABS_TOL), case
    assert analytics95.var == pytest.approx(var95, rel=0, abs=ABS_TOL), case
    assert analytics95.expected_shortfall == pytest.approx(es95, rel=0, abs=ABS_TOL), case
    assert analytics99.var == pytest.approx(var99, rel=0, abs=ABS_TOL), case
    assert analytics99.expected_shortfall == pytest.approx(es99, rel=0, abs=ABS_TOL), case

    # R0 requires explicit engine-to-analytics parity for cases A-D.
    if case in {"A", "B", "C", "D"}:
        assert result["var_95"] == pytest.approx(analytics95.var, rel=0, abs=ABS_TOL)
        assert result["var_99"] == pytest.approx(analytics99.var, rel=0, abs=ABS_TOL)
        assert result["expected_shortfall_99"] == pytest.approx(
            analytics99.expected_shortfall,
            rel=0,
            abs=ABS_TOL,
        )


def test_var95_golden_rejects_wrong_tail_index_and_sign() -> None:
    pnl = -np.arange(1.0, 21.0)
    losses = -pnl
    golden_var95 = 19.05

    wrong_tail = np.quantile(losses, 1.0 - 0.95)
    off_by_one = np.sort(losses)[int(0.95 * len(losses))]
    sign_flipped = np.quantile(pnl, 0.95)

    assert wrong_tail != pytest.approx(golden_var95, rel=0, abs=ABS_TOL)
    assert off_by_one != pytest.approx(golden_var95, rel=0, abs=ABS_TOL)
    assert sign_flipped != pytest.approx(golden_var95, rel=0, abs=ABS_TOL)


def test_es99_golden_rejects_best_observations_and_unconditional_mean() -> None:
    losses = np.arange(1.0, 21.0)
    golden_es99 = 20.0

    wrong_best_tail = np.mean(np.sort(losses)[:1])
    wrong_unconditional_mean = np.mean(losses)

    assert wrong_best_tail != pytest.approx(golden_es99, rel=0, abs=ABS_TOL)
    assert wrong_unconditional_mean != pytest.approx(golden_es99, rel=0, abs=ABS_TOL)


def test_es_tail_membership_includes_losses_equal_to_var() -> None:
    # With n=21 and q=.95, q*(n-1)=19 exactly, so VaR is the observed loss 19.
    # Current >= semantics average {19, 20} -> 19.5; strict > would return 20.
    pnl = -np.arange(0.0, 21.0)
    losses = -pnl
    golden_var95 = 19.0
    golden_es95 = 19.5

    analytics95 = historical_method(pnl, 0.95)
    strict_tail_es = float(losses[losses > golden_var95].mean())

    assert analytics95.var == golden_var95
    assert analytics95.expected_shortfall == golden_es95
    assert strict_tail_es != pytest.approx(golden_es95, rel=0, abs=ABS_TOL)


def test_historical_engine_es99_includes_var_threshold() -> None:
    """n=101 losses 0..100: q99 lands on 99. ES >= 99 is 99.5; strict > is 100.

    This is the engine-facing mutation that ``HistoricalRiskEngine`` must catch;
    VaRAnalytics 95% membership alone does not pin ``expected_shortfall_99``.
    """
    pnl = -np.arange(0.0, 101.0)
    result = historical_result(pnl)
    assert result["var_99"] == pytest.approx(99.0, rel=0, abs=ABS_TOL)
    assert result["expected_shortfall_99"] == pytest.approx(99.5, rel=0, abs=ABS_TOL)
    assert result["expected_shortfall_99"] != pytest.approx(100.0, rel=0, abs=ABS_TOL)
