"""Stage 10.1 — production demo history is a per-factor panel, not four-macro broadcast.

Quant contract:
- Shock unit: EquitySpot / FXSpot relative return (0.01 = +1%); EquityVol / FXVol
  relative vol-level change; RateZero basis points (1.0 = +1bp).
- Sensitivity unit: engine conventions (delta × relative return; vega × vol points
  after relative→absolute conversion; DV01 × bp).
- Sign: positive equity/FX return raises spot; positive rate bp raises the zero;
  positive vol move raises vol. Loss = −P&L. VaR/ES floored at 0.
- Currency/notional: position currency; FX pair EURUSD as existing FX adapters.
- Base market: bound MarketSnapshot (demo _DEMO_MARKETS / explicit test snapshots).
  Positions are contractual economics only.
- Reconciliation: hierarchy root var_99 equals direct HistoricalRiskEngine /
  PortfolioService.summary var_99 on the same book, snapshot, dataset, methodology
  (abs 1e-12).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_panel import PER_FACTOR_PANEL_PROJECTION, factor_panel_from_dataset
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero
from app.risk.historical import HistoricalRiskEngine, require_panel_covers_portfolio
from app.risk.historical_data import (
    FOUR_MACRO_DEMO_PROJECTION,
    create_historical_dataset,
    load_demo_historical_dataset,
)
from app.sample import (
    CROSS_ASSET_PORTFOLIO,
    EQUITY_VOL_PORTFOLIO,
    SAMPLE_PORTFOLIO,
)
from app.services.risk_factories import (
    DEFAULT_HISTORICAL_DATASET_VERSION,
    build_historical_risk_engine,
    build_portfolio_service,
    dataset_identity,
    resolve_run_spec,
)

# Brief-mandated production demo identity (synthetic replay, not observed data).
EXPECTED_DATASET_ID = "demo-multi-factor-history"
EXPECTED_DATASET_VERSION = "v1"

AAPL = EquitySpot("AAPL")
MSFT = EquitySpot("MSFT")
NVDA = EquitySpot("NVDA")
SPY = EquitySpot("SPY")
USD_2Y = RateZero("USD", "2Y")
USD_10Y = RateZero("USD", "10Y")

REQUIRED_PANEL_FACTORS: tuple = (
    EquitySpot("AAPL"),
    EquitySpot("MSFT"),
    EquitySpot("NVDA"),
    EquityVol(underlying="AAPL"),
    EquityVol(underlying="MSFT"),
    EquityVol(underlying="NVDA"),
    RateZero("USD", "2Y"),
    RateZero("USD", "5Y"),
    RateZero("USD", "10Y"),
    FXSpot("EURUSD"),
    FXVol(pair="EURUSD"),
    EquitySpot("SPY"),
    EquityVol(underlying="SPY"),
)


def _panel_ids(panel) -> set[tuple[str, str, str]]:
    return {(type(f).__name__, f.key, f.bucket) for f in panel.factors}


def _factor_ids(factors) -> set[tuple[str, str, str]]:
    return {(type(f).__name__, f.key, f.bucket) for f in factors}


def test_factory_default_dataset_is_per_factor_demo_panel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    engine = build_historical_risk_engine()
    panel = engine.factor_panel
    assert panel is not None
    assert panel.projection == PER_FACTOR_PANEL_PROJECTION
    assert panel.is_per_name_per_tenor_panel is True
    assert engine.dataset.projection == PER_FACTOR_PANEL_PROJECTION
    assert engine.dataset.projection != FOUR_MACRO_DEMO_PROJECTION
    assert engine.dataset.is_per_name_per_tenor_panel is True
    ds_id, ds_version = dataset_identity(engine.dataset)
    assert ds_id == EXPECTED_DATASET_ID
    assert ds_version == EXPECTED_DATASET_VERSION
    assert _factor_ids(REQUIRED_PANEL_FACTORS) <= _panel_ids(panel)


def test_aapl_and_msft_history_differ_on_production_panel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    panel = build_historical_risk_engine().factor_panel
    assert panel is not None
    assert any(panel.change(as_of, AAPL) != panel.change(as_of, MSFT) for as_of in panel.dates)
    # SPY must not be silently broadcast onto single-name equities.
    assert any(panel.change(as_of, SPY) != panel.change(as_of, AAPL) for as_of in panel.dates)
    assert any(panel.change(as_of, SPY) != panel.change(as_of, MSFT) for as_of in panel.dates)
    assert any(panel.change(as_of, NVDA) != panel.change(as_of, AAPL) for as_of in panel.dates)


def test_usd_2y_and_10y_history_differ_on_production_panel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    panel = build_historical_risk_engine().factor_panel
    assert panel is not None
    assert any(panel.change(as_of, USD_2Y) != panel.change(as_of, USD_10Y) for as_of in panel.dates)


def test_production_panel_dates_come_from_checked_in_file(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    engine = build_historical_risk_engine()
    panel = engine.factor_panel
    assert panel is not None
    csv_path = Path(engine.dataset.source_path)
    assert csv_path.is_file()
    raw_dates: list[date] = []
    with csv_path.open(encoding="utf-8") as fh:
        header = fh.readline()
        assert "date" in header.split(",")[0]
        for line in fh:
            if not line.strip():
                continue
            raw_dates.append(date.fromisoformat(line.split(",", 1)[0].strip()))
    assert tuple(raw_dates) == panel.dates
    # Must not invent a consecutive calendar that fills weekends the CSV skipped.
    invented = tuple(date(2022, 1, 3) + timedelta(days=i) for i in range(len(raw_dates)))
    if raw_dates != list(invented):
        assert panel.dates != invented


def test_same_length_per_factor_csvs_produce_different_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    n = 24
    dates = [date(2022, 1, 3) + timedelta(days=i) for i in range(n)]
    columns = [
        "EquitySpot:AAPL",
        "EquitySpot:MSFT",
        "EquitySpot:NVDA",
        "EquitySpot:SPY",
        "EquityVol:AAPL",
        "EquityVol:MSFT",
        "EquityVol:NVDA",
        "EquityVol:SPY",
        "RateZero:USD:0Y",
        "RateZero:USD:2Y",
        "RateZero:USD:5Y",
        "RateZero:USD:10Y",
        "FXSpot:EURUSD",
        "FXVol:EURUSD",
    ]
    path_a = tmp_path / "panel_a.csv"
    path_b = tmp_path / "panel_b.csv"

    def _write(path: Path, equity: float, rate: float) -> None:
        header = ",".join(["date", *columns])
        rows = [header]
        for as_of in dates:
            values = []
            for col in columns:
                if col.startswith("EquitySpot:") or col.startswith("FXSpot:"):
                    values.append(str(equity))
                elif col.startswith("EquityVol:") or col.startswith("FXVol:"):
                    values.append("0.01")
                else:
                    values.append(str(rate))
            rows.append(as_of.isoformat() + "," + ",".join(values))
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    _write(path_a, equity=0.04, rate=2.0)
    _write(path_b, equity=-0.05, rate=-8.0)

    engine_a = build_historical_risk_engine(historical_dataset_id=str(path_a))
    engine_b = build_historical_risk_engine(historical_dataset_id=str(path_b))
    panel_a = engine_a.factor_panel
    panel_b = engine_b.factor_panel
    assert panel_a is not None and panel_b is not None
    assert panel_a.n_observations == panel_b.n_observations == n
    assert panel_a.change(panel_a.dates[0], AAPL) == pytest.approx(0.04)
    assert panel_b.change(panel_b.dates[0], AAPL) == pytest.approx(-0.05)
    assert panel_a.projection == PER_FACTOR_PANEL_PROJECTION
    assert engine_a.dataset.projection == PER_FACTOR_PANEL_PROJECTION

    from app.sample import demo_market_snapshot

    pricing = BuiltinPricingEngine()
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    result_a = engine_a.calculate(SAMPLE_PORTFOLIO, pricing, market=market)
    result_b = engine_b.calculate(SAMPLE_PORTFOLIO, pricing, market=market)
    assert result_a.var_99 != result_b.var_99
    assert result_a.var_95 != result_b.var_95
    assert result_a.expected_shortfall_99 != result_b.expected_shortfall_99


def test_hierarchy_root_var_reconciles_with_direct_var(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    service = build_portfolio_service()
    summary = service.summary(SAMPLE_PORTFOLIO)
    root = service.hierarchy(SAMPLE_PORTFOLIO)
    assert summary.var_99 != 0.0
    assert root.var_99 == pytest.approx(summary.var_99, rel=0, abs=1e-12)
    engine = service.risk
    assert isinstance(engine, HistoricalRiskEngine)
    pricing = BuiltinPricingEngine()
    from app.sample import demo_market_snapshot

    direct = engine.calculate(
        SAMPLE_PORTFOLIO, pricing, market=demo_market_snapshot(SAMPLE_PORTFOLIO)
    )
    assert root.var_99 == pytest.approx(direct.var_99, rel=0, abs=1e-12)


def test_missing_required_factor_fails_closed_not_silent_zero(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    engine = build_historical_risk_engine()
    panel = engine.factor_panel
    assert panel is not None
    stripped = type(panel).from_pairs(
        dates=panel.dates[:2],
        rows=[
            [(f, obs.change(f)) for f in panel.factors if not (isinstance(f, EquitySpot) and f.symbol == "AAPL")]
            for obs in panel.observations[:2]
        ],
    )
    with pytest.raises(ValueError, match="missing required factor"):
        require_panel_covers_portfolio(SAMPLE_PORTFOLIO, stripped)
    pricing = BuiltinPricingEngine()
    from app.sample import demo_market_snapshot

    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    broken = HistoricalRiskEngine(
        dataset=engine.dataset,
        observations=stripped.n_observations,
        factor_panel=stripped,
    )
    with pytest.raises(ValueError, match="missing required factor"):
        broken.calculate(SAMPLE_PORTFOLIO, pricing, market=market)


def test_riskrun_dataset_identity_matches_series_used(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    service = build_portfolio_service()
    ds_id, ds_version = dataset_identity(service.risk.dataset)
    assert ds_id == EXPECTED_DATASET_ID
    assert ds_version == EXPECTED_DATASET_VERSION == DEFAULT_HISTORICAL_DATASET_VERSION
    spec = resolve_run_spec(risk_engine=service.risk)
    assert spec.historical_dataset_id == EXPECTED_DATASET_ID
    assert spec.historical_dataset_version == EXPECTED_DATASET_VERSION
    panel = service.risk.factor_panel
    assert panel is not None
    mapped = factor_panel_from_dataset(service.risk.dataset)
    assert mapped.dates == panel.dates
    as_of = panel.dates[0]
    for factor in REQUIRED_PANEL_FACTORS:
        assert mapped.change(as_of, factor) == pytest.approx(panel.change(as_of, factor))


def test_demo_books_include_aapl_and_msft():
    for book in (EQUITY_VOL_PORTFOLIO, CROSS_ASSET_PORTFOLIO, SAMPLE_PORTFOLIO):
        symbols = {getattr(p, "symbol", None) for p in book.positions}
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert "NVDA" in symbols


def test_four_macro_fixture_and_null_panel_path_still_exist():
    dataset = load_demo_historical_dataset()
    assert dataset.projection == FOUR_MACRO_DEMO_PROJECTION
    assert dataset.is_per_name_per_tenor_panel is False
    labeled = create_historical_dataset("demo")
    assert labeled.projection == FOUR_MACRO_DEMO_PROJECTION
    engine = HistoricalRiskEngine(dataset=dataset, factor_panel=None)
    assert engine.factor_panel is None
    from app.sample import demo_market_snapshot

    result = engine.calculate(
        SAMPLE_PORTFOLIO, BuiltinPricingEngine(), market=demo_market_snapshot(SAMPLE_PORTFOLIO)
    )
    assert result.var_99 >= 0.0
