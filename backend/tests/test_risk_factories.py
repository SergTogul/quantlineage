"""R0.5.3 leftover — production factory defaults to HistoricalFactorPanel.

Bare ``HistoricalRiskEngine()`` / ``factor_panel=None`` remains the labeled
four-macro path. Production default dataset is the per-factor demo panel.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.models import MarketSnapshot
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_panel import DEFAULT_PRODUCTION_PANEL_FACTORS, PER_FACTOR_PANEL_PROJECTION
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import load_demo_historical_dataset
from app.risk.scenarios import iter_panel_shocked_snapshots
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.risk_factories import (
    SYNTHETIC_HISTORICAL_DATASET_ID,
    build_historical_risk_engine,
    build_portfolio_service,
    resize_historical_risk_engine,
)

NVDA = EquitySpot("NVDA")
SPY = EquitySpot("SPY")
USD_2Y = RateZero("USD", "2Y")
USD_10Y = RateZero("USD", "10Y")


def test_build_historical_risk_engine_uses_per_factor_panel(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    engine = build_historical_risk_engine()
    assert engine.factor_panel is not None
    assert engine.factor_panel.is_per_name_per_tenor_panel is True
    assert engine.factor_panel.projection == PER_FACTOR_PANEL_PROJECTION
    assert engine.factor_panel.projection != "four_macro_demo"
    # Dataset identity is the per-factor demo panel (not four-macro broadcast).
    assert engine.dataset.projection == PER_FACTOR_PANEL_PROJECTION
    assert engine.dataset.is_per_name_per_tenor_panel is True
    assert len(engine.factor_panel.dates) == engine.dataset.n_observations
    panel_ids = {(type(f).__name__, f.key, f.bucket) for f in engine.factor_panel.factors}
    expected_ids = {(type(f).__name__, f.key, f.bucket) for f in DEFAULT_PRODUCTION_PANEL_FACTORS}
    assert panel_ids == expected_ids
    assert "NVDA" in {f.key for f in engine.factor_panel.factors if isinstance(f, EquitySpot)}
    assert "SPY" in {f.key for f in engine.factor_panel.factors if isinstance(f, EquitySpot)}
    assert "AAPL" in {f.key for f in engine.factor_panel.factors if isinstance(f, EquitySpot)}
    assert "MSFT" in {f.key for f in engine.factor_panel.factors if isinstance(f, EquitySpot)}


def test_production_panel_equities_and_tenors_move_independently(
    monkeypatch: pytest.MonkeyPatch,
):
    """RF-005 exit: two equities and two rate tenors differ in one observation.

    Independence is a synthetic-panel property. Demo/file CSVs broadcast the
    four macro columns onto each typed factor family, so NVDA and SPY match.
    """
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    engine = build_historical_risk_engine(
        historical_dataset_id=SYNTHETIC_HISTORICAL_DATASET_ID
    )
    panel = engine.factor_panel
    assert panel is not None

    equity_diff = any(
        panel.change(as_of, NVDA) != panel.change(as_of, SPY) for as_of in panel.dates
    )
    tenor_diff = any(
        panel.change(as_of, USD_2Y) != panel.change(as_of, USD_10Y) for as_of in panel.dates
    )
    assert equity_diff
    assert tenor_diff

    market = MarketSnapshot(
        id="factory-indep",
        equity_spots={"NVDA": 100.0, "SPY": 100.0},
        rates={"USD": 0.04},
        key_rates={"USD": {"2Y": 0.03, "10Y": 0.04}},
    )
    # Find an observation where both pairs differ, then prove shocked spots/tenors.
    for as_of in panel.dates:
        if panel.change(as_of, NVDA) == panel.change(as_of, SPY):
            continue
        if panel.change(as_of, USD_2Y) == panel.change(as_of, USD_10Y):
            continue
        single = type(panel).from_pairs(
            dates=[as_of],
            rows=[
                [
                    (NVDA, panel.change(as_of, NVDA)),
                    (SPY, panel.change(as_of, SPY)),
                    (USD_2Y, panel.change(as_of, USD_2Y)),
                    (USD_10Y, panel.change(as_of, USD_10Y)),
                ]
            ],
        )
        shocked = next(iter(iter_panel_shocked_snapshots(market, single)))
        assert shocked.equity_spots["NVDA"] != shocked.equity_spots["SPY"]
        assert shocked.key_rates["USD"]["2Y"] != shocked.key_rates["USD"]["10Y"]
        break
    else:
        pytest.fail("no observation with both equity and tenor independence")


def test_four_macro_path_still_available_without_panel(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    engine = HistoricalRiskEngine(dataset=load_demo_historical_dataset(), factor_panel=None)
    assert engine.factor_panel is None
    assert engine.dataset.projection == "four_macro_demo"
    assert engine.dataset.is_per_name_per_tenor_panel is False
    resized = resize_historical_risk_engine(engine, 40)
    assert resized.factor_panel is None
    assert resized.observations == 40


def test_build_portfolio_service_inherits_factory_panel(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    service = build_portfolio_service()
    assert isinstance(service.risk, HistoricalRiskEngine)
    assert service.risk.factor_panel is not None
    assert service.risk.factor_panel.is_per_name_per_tenor_panel is True


def test_demo_markets_cover_production_panel_rate_tenors():
    """FULL_REVAL applies every panel RateZero via MarketSnapshot.apply.

    Demo books must carry those pillars (incl. USD 0Y); otherwise /risk/es and
    /risk/var with methodology=FULL_REVALUATION fail closed with KeyError → 500.
    """
    from app.sample import DEMO_PORTFOLIOS, demo_market_snapshot

    panel_rate_tenors = {
        f.tenor for f in DEFAULT_PRODUCTION_PANEL_FACTORS if isinstance(f, RateZero)
    }
    assert "0Y" in panel_rate_tenors
    for book in DEMO_PORTFOLIOS:
        market = demo_market_snapshot(book)
        for factor in DEFAULT_PRODUCTION_PANEL_FACTORS:
            if not isinstance(factor, RateZero):
                continue
            assert factor.currency in market.rates
            pillars = market.key_rates.get(factor.currency) or {}
            assert factor.tenor in pillars, (
                f"{book.id} missing key_rates[{factor.currency!r}][{factor.tenor!r}] "
                f"required by DEFAULT_PRODUCTION_PANEL_FACTORS"
            )


def test_production_full_revaluation_es_on_sample_book(
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression: POST /risk/es?methodology=FULL_REVALUATION on global-macro."""
    from app.domain.models import VaRMethodology
    from app.sample import SAMPLE_PORTFOLIO

    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    service = build_portfolio_service(observations=8, seed=7)
    report = service.es_contributions(
        SAMPLE_PORTFOLIO, methodology=VaRMethodology.FULL_REVALUATION
    )
    assert report.methodology is VaRMethodology.FULL_REVALUATION
    assert report.portfolio_es >= 0.0
    assert report.by_position


def _write_factor_csv(path: Path, *, equity: list[float], vol: list[float], rate: list[float], fx: list[float]) -> None:
    lines = ["equity_return,vol_move,rate_move_bps,fx_return"]
    for e, v, r, x in zip(equity, vol, rate, fx, strict=True):
        lines.append(f"{e},{v},{r},{x}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_csv_dataset_owns_factor_panel_and_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Review Test A: two same-length CSVs must not share a synthetic panel."""
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    n = 24
    path_a = tmp_path / "hist_a.csv"
    path_b = tmp_path / "hist_b.csv"
    _write_factor_csv(
        path_a,
        equity=[0.04] * n,
        vol=[0.01] * n,
        rate=[2.0] * n,
        fx=[0.002] * n,
    )
    _write_factor_csv(
        path_b,
        equity=[-0.05] * n,
        vol=[-0.02] * n,
        rate=[-8.0] * n,
        fx=[-0.003] * n,
    )

    engine_a = build_historical_risk_engine(historical_dataset_id=str(path_a))
    engine_b = build_historical_risk_engine(historical_dataset_id=str(path_b))
    panel_a = engine_a.factor_panel
    panel_b = engine_b.factor_panel
    assert panel_a is not None and panel_b is not None
    assert panel_a.n_observations == n
    assert panel_b.n_observations == n

    first_a = panel_a.dates[0]
    first_b = panel_b.dates[0]
    for factor in panel_a.factors:
        if isinstance(factor, EquitySpot):
            assert panel_a.change(first_a, factor) == pytest.approx(0.04)
        elif isinstance(factor, (EquityVol, FXVol)):
            assert panel_a.change(first_a, factor) == pytest.approx(0.01)
        elif isinstance(factor, RateZero):
            assert panel_a.change(first_a, factor) == pytest.approx(2.0)
        elif isinstance(factor, FXSpot):
            assert panel_a.change(first_a, factor) == pytest.approx(0.002)
    for factor in panel_b.factors:
        if isinstance(factor, EquitySpot):
            assert panel_b.change(first_b, factor) == pytest.approx(-0.05)

    pricing = BuiltinPricingEngine()
    market = demo_market_snapshot(SAMPLE_PORTFOLIO)
    result_a = engine_a.calculate(SAMPLE_PORTFOLIO, pricing, market=market)
    result_b = engine_b.calculate(SAMPLE_PORTFOLIO, pricing, market=market)
    assert result_a.var_95 != result_b.var_95
    assert result_a.var_99 != result_b.var_99
    assert result_a.expected_shortfall_99 != result_b.expected_shortfall_99
