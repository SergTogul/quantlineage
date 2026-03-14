"""M2.1 historical market dataset abstraction tests.

Conventions:
- equity / FX: relative returns
- vol: relative vol-level moves
- rates: parallel bp moves (not key-rate / tenor-specific)
- Tolerances: exact array equality for seeded synthetic; abs 1e-12 for VaR parity
"""

from __future__ import annotations

import numpy as np
import pytest

from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import (
    ArrayHistoricalDataset,
    FactorObservationSeries,
    SyntheticHistoricalDataset,
)
from app.risk.var import VaRAnalytics
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)


def test_factor_observation_series_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="vol_moves"):
        FactorObservationSeries(
            equity_returns=np.zeros(3),
            vol_moves=np.zeros(2),
            rate_moves_bps=np.zeros(3),
            fx_returns=np.zeros(3),
        )


def test_factor_observation_series_rejects_empty():
    with pytest.raises(ValueError, match="at least one"):
        FactorObservationSeries(
            equity_returns=np.array([]),
            vol_moves=np.array([]),
            rate_moves_bps=np.array([]),
            fx_returns=np.array([]),
        )


def test_synthetic_dataset_is_deterministic():
    a = SyntheticHistoricalDataset(seed=42, observations=50).factor_observations()
    b = SyntheticHistoricalDataset(seed=42, observations=50).factor_observations()
    assert a.n_observations == 50
    np.testing.assert_array_equal(a.equity_returns, b.equity_returns)
    np.testing.assert_array_equal(a.vol_moves, b.vol_moves)
    np.testing.assert_array_equal(a.rate_moves_bps, b.rate_moves_bps)
    np.testing.assert_array_equal(a.fx_returns, b.fx_returns)


def test_synthetic_matches_legacy_rng_sequence():
    """Guard numerical continuity with pre-abstraction HistoricalRiskEngine RNG."""
    seed, n = 7, 750
    obs = SyntheticHistoricalDataset(seed=seed, observations=n).factor_observations()
    rng = np.random.default_rng(seed)
    np.testing.assert_array_equal(obs.equity_returns, rng.normal(0.0002, 0.013, n))
    np.testing.assert_array_equal(obs.vol_moves, rng.normal(0.0, 0.07, n))
    np.testing.assert_array_equal(obs.rate_moves_bps, rng.normal(0.0, 7.0, n))
    np.testing.assert_array_equal(obs.fx_returns, rng.normal(0.0, 0.006, n))


def test_array_dataset_feeds_historical_engine():
    series = FactorObservationSeries(
        equity_returns=np.array([0.01, -0.02, 0.0]),
        vol_moves=np.array([0.0, 0.05, -0.01]),
        rate_moves_bps=np.array([1.0, -2.0, 0.0]),
        fx_returns=np.array([0.001, -0.001, 0.0]),
    )
    engine = HistoricalRiskEngine(dataset=ArrayHistoricalDataset(series))
    pricing = BuiltinPricingEngine()
    r = engine.calculate(SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET)
    assert r["var_99"] >= r["var_95"] >= 0.0
    assert r["expected_shortfall_99"] >= r["var_99"]


def test_historical_engine_default_matches_seeded_synthetic():
    pricing = BuiltinPricingEngine()
    via_seed = HistoricalRiskEngine(seed=1).calculate(
        SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET
    )
    via_dataset = HistoricalRiskEngine(
        dataset=SyntheticHistoricalDataset(seed=1, observations=750)
    ).calculate(SAMPLE_PORTFOLIO, pricing, market=SAMPLE_MARKET)
    assert via_seed == via_dataset


def test_var_analytics_uses_dataset_without_key_rates():
    """M2.1 stays on aggregate factors — no key_rates dependency."""
    series = FactorObservationSeries(
        equity_returns=np.linspace(-0.02, 0.02, 40),
        vol_moves=np.zeros(40),
        rate_moves_bps=np.zeros(40),
        fx_returns=np.zeros(40),
    )
    report = VaRAnalytics(dataset=ArrayHistoricalDataset(series)).report(
        SAMPLE_PORTFOLIO, BuiltinPricingEngine(), confidence=0.95, market=SAMPLE_MARKET
    )
    assert {m.method for m in report.methods} == {"historical", "parametric"}
    hist = next(m for m in report.methods if m.method == "historical")
    assert hist.var >= 0.0
    assert hist.expected_shortfall >= hist.var
