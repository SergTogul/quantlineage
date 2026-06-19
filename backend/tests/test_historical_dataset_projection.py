"""Labeled four-macro fixture vs production per-factor demo history.

Four-column demo/synthetic sources stay ``projection="four_macro_demo"``.
Production factory default is the per-factor panel (Stage 10.1).
"""

from __future__ import annotations

from app.risk.historical_data import (
    FOUR_MACRO_DEMO_PROJECTION,
    MVP_AGGREGATE_FACTORS,
    HistoricalDatasetProjection,
    SyntheticHistoricalDataset,
    create_historical_dataset,
    load_demo_historical_dataset,
)


def test_demo_dataset_reports_four_macro_demo_projection():
    dataset = load_demo_historical_dataset()
    assert dataset.projection == HistoricalDatasetProjection.FOUR_MACRO_DEMO
    assert dataset.projection == FOUR_MACRO_DEMO_PROJECTION
    assert dataset.projection == "four_macro_demo"
    assert dataset.is_per_name_per_tenor_panel is False


def test_synthetic_dataset_reports_four_macro_demo_projection():
    dataset = SyntheticHistoricalDataset()
    assert dataset.projection == HistoricalDatasetProjection.FOUR_MACRO_DEMO
    assert dataset.projection == "four_macro_demo"
    assert dataset.is_per_name_per_tenor_panel is False


def test_create_historical_dataset_demo_exposes_projection():
    dataset = create_historical_dataset("demo")
    assert dataset.projection == HistoricalDatasetProjection.FOUR_MACRO_DEMO
    assert dataset.projection == "four_macro_demo"
    assert dataset.is_per_name_per_tenor_panel is False


def test_create_historical_dataset_multi_factor_exposes_per_factor_projection():
    dataset = create_historical_dataset("demo-multi-factor-history")
    assert dataset.projection == HistoricalDatasetProjection.PER_FACTOR
    assert dataset.projection == "per_factor"
    assert dataset.is_per_name_per_tenor_panel is True


def test_four_columns_are_mvp_aggregates_not_a_factor_panel():
    """Equity/vol/rate/fx only — not advertised as a per-name/per-tenor panel."""
    demo = load_demo_historical_dataset()
    synthetic = SyntheticHistoricalDataset()
    assert MVP_AGGREGATE_FACTORS == ("equity", "vol", "rate", "fx")
    for dataset in (demo, synthetic, create_historical_dataset("demo")):
        assert dataset.aggregate_factors == MVP_AGGREGATE_FACTORS
        assert dataset.projection == "four_macro_demo"
        assert dataset.is_per_name_per_tenor_panel is False
        series = dataset.factor_observations()
        assert series.aggregate_factors == MVP_AGGREGATE_FACTORS
        assert hasattr(series, "equity_returns")
        assert hasattr(series, "vol_moves")
        assert hasattr(series, "rate_moves_bps")
        assert hasattr(series, "fx_returns")
        assert not hasattr(series, "per_name")
        assert not hasattr(series, "per_tenor")
        assert not hasattr(series, "risk_factor_keys")
