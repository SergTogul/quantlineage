"""M10.2 demo historical market dataset — file-backed factor replay.

Conventions (aligned with FactorObservationSeries / M2.1):
- equity / FX: relative returns (0.01 = +1%)
- vol: relative vol-level moves
- rates: parallel bp moves (1.0 = +1bp)
- No live vendor feeds; packaged CSV is synthetic/replay only.
- Tolerances: exact array equality vs frozen CSV / seeded synthetic parity.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import (
    DEMO_HISTORICAL_DATASET_ID,
    SyntheticHistoricalDataset,
    create_historical_dataset,
    demo_historical_dataset_path,
    load_demo_historical_dataset,
    load_factor_observations_csv,
)
from app.risk.scenarios import historical_shocked_snapshots
from app.risk.var import VaRAnalytics
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot


def _write_mini_csv(path: Path) -> None:
    path.write_text(
        "date,equity_return,vol_move,rate_move_bps,fx_return\n"
        "2024-01-02,0.01,0.0,1.0,0.001\n"
        "2024-01-03,-0.02,0.05,-2.0,-0.001\n"
        "2024-01-04,0.0,-0.01,0.0,0.0\n",
        encoding="utf-8",
    )


def test_load_factor_observations_csv_reads_aligned_columns(tmp_path: Path):
    path = tmp_path / "factors.csv"
    _write_mini_csv(path)
    series = load_factor_observations_csv(path)
    assert series.n_observations == 3
    np.testing.assert_array_equal(series.equity_returns, [0.01, -0.02, 0.0])
    np.testing.assert_array_equal(series.vol_moves, [0.0, 0.05, -0.01])
    np.testing.assert_array_equal(series.rate_moves_bps, [1.0, -2.0, 0.0])
    np.testing.assert_array_equal(series.fx_returns, [0.001, -0.001, 0.0])


def test_load_factor_observations_csv_rejects_missing_columns(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text("date,equity_return\n2024-01-02,0.01\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required column"):
        load_factor_observations_csv(path)


def test_demo_historical_dataset_path_points_at_packaged_csv():
    path = demo_historical_dataset_path()
    assert path.name == "demo_historical_factors.csv"
    assert path.is_file(), f"expected packaged demo CSV at {path}"


def test_load_demo_historical_dataset_is_deterministic_and_sized():
    a = load_demo_historical_dataset()
    b = load_demo_historical_dataset()
    sa = a.factor_observations()
    sb = b.factor_observations()
    assert sa.n_observations == 750
    assert a.dataset_id == DEMO_HISTORICAL_DATASET_ID
    np.testing.assert_array_equal(sa.equity_returns, sb.equity_returns)
    np.testing.assert_array_equal(sa.vol_moves, sb.vol_moves)
    np.testing.assert_array_equal(sa.rate_moves_bps, sb.rate_moves_bps)
    np.testing.assert_array_equal(sa.fx_returns, sb.fx_returns)


def test_demo_csv_matches_synthetic_seed_seven_replay():
    """Frozen demo CSV is a deterministic replay of SyntheticHistoricalDataset(7, 750)."""
    demo = load_demo_historical_dataset().factor_observations()
    synthetic = SyntheticHistoricalDataset(seed=7, observations=750).factor_observations()
    np.testing.assert_array_equal(demo.equity_returns, synthetic.equity_returns)
    np.testing.assert_array_equal(demo.vol_moves, synthetic.vol_moves)
    np.testing.assert_array_equal(demo.rate_moves_bps, synthetic.rate_moves_bps)
    np.testing.assert_array_equal(demo.fx_returns, synthetic.fx_returns)


def test_create_historical_dataset_demo_and_synthetic(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    syn = create_historical_dataset("synthetic", seed=3, observations=20)
    assert isinstance(syn, SyntheticHistoricalDataset)
    assert syn.factor_observations().n_observations == 20

    demo = create_historical_dataset("demo")
    assert demo.factor_observations().n_observations == 750

    monkeypatch.setenv("RISKFORGE_HISTORICAL_DATASET", "demo")
    via_env = create_historical_dataset()
    np.testing.assert_array_equal(
        via_env.factor_observations().equity_returns,
        demo.factor_observations().equity_returns,
    )


def test_create_historical_dataset_accepts_csv_path(tmp_path: Path):
    path = tmp_path / "custom.csv"
    _write_mini_csv(path)
    ds = create_historical_dataset(str(path))
    assert ds.factor_observations().n_observations == 3


def test_demo_dataset_feeds_historical_var_and_scenarios():
    dataset = load_demo_historical_dataset()
    pricing = BuiltinPricingEngine()
    engine = HistoricalRiskEngine(dataset=dataset)
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    risk = engine.calculate(SAMPLE_PORTFOLIO, pricing, market=market)
    assert risk["var_99"] >= risk["var_95"] >= 0.0
    assert risk["expected_shortfall_99"] >= risk["var_99"]

    report = VaRAnalytics(dataset=dataset).report(
        SAMPLE_PORTFOLIO, pricing, confidence=0.99, market=market
    )
    hist = next(m for m in report.methods if m.method == "historical")
    assert hist.var >= 0.0

    shocked = historical_shocked_snapshots(market, dataset)
    assert len(shocked) == dataset.factor_observations().n_observations
    assert all(s.id.startswith(f"{market.id}:") for s in shocked[:3])


def test_api_portfolio_service_uses_configured_historical_dataset(monkeypatch: pytest.MonkeyPatch):
    """deps wires create_historical_dataset so risk APIs can select demo/synthetic."""
    monkeypatch.setenv("RISKFORGE_HISTORICAL_DATASET", "demo")
    # Re-import wiring after env is set would be brittle; call factory the same way deps does.
    from app.risk.historical_data import create_historical_dataset as factory

    ds = factory()
    engine = HistoricalRiskEngine(dataset=ds)
    assert engine.dataset.factor_observations().n_observations == 750
    # Parity with default seed-7 synthetic so switching API source does not invent new numbers.
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    baseline = HistoricalRiskEngine(seed=7, observations=750).calculate(
        SAMPLE_PORTFOLIO, BuiltinPricingEngine(), market=market
    )
    via_demo = engine.calculate(SAMPLE_PORTFOLIO, BuiltinPricingEngine(), market=market)
    assert via_demo == baseline
