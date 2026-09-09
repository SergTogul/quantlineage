"""R0.5.3 leftover — production factory defaults to HistoricalFactorPanel.

Bare ``HistoricalRiskEngine()`` / ``factor_panel=None`` remains the labeled
four-macro path. Demo/synthetic datasets stay ``projection="four_macro_demo"``.
"""

from __future__ import annotations

import pytest

from app.domain.models import MarketSnapshot
from app.risk.factor_panel import DEFAULT_PRODUCTION_PANEL_FACTORS, PER_FACTOR_PANEL_PROJECTION
from app.risk.factor_types import EquitySpot, RateZero
from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import create_historical_dataset
from app.risk.scenarios import iter_panel_shocked_snapshots
from app.services.risk_factories import build_historical_risk_engine, build_portfolio_service

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
    # Dataset identity stays for run-spec / compat; labeled four-macro fixture.
    assert engine.dataset.projection == "four_macro_demo"
    assert engine.dataset.is_per_name_per_tenor_panel is False
    assert len(engine.factor_panel.dates) == len(engine.dataset.factor_observations().equity_returns)
    panel_ids = {(type(f).__name__, f.key, f.bucket) for f in engine.factor_panel.factors}
    expected_ids = {(type(f).__name__, f.key, f.bucket) for f in DEFAULT_PRODUCTION_PANEL_FACTORS}
    assert panel_ids == expected_ids
    assert "NVDA" in {f.key for f in engine.factor_panel.factors if isinstance(f, EquitySpot)}
    assert "SPY" in {f.key for f in engine.factor_panel.factors if isinstance(f, EquitySpot)}


def test_production_panel_equities_and_tenors_move_independently(
    monkeypatch: pytest.MonkeyPatch,
):
    """RF-005 exit: two equities and two rate tenors differ in one observation."""
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    engine = build_historical_risk_engine()
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
    engine = HistoricalRiskEngine(dataset=create_historical_dataset(), factor_panel=None)
    assert engine.factor_panel is None
    assert engine.dataset.projection == "four_macro_demo"
    assert engine.dataset.is_per_name_per_tenor_panel is False


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
