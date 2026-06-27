"""M2.4 — VaR methodology comparison (Linear / Δ-Γ / Full revaluation)."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio, VaRMethodology
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_panel import HistoricalFactorPanel, panel_factor_identity
from app.risk.historical import HistoricalRiskEngine
from app.risk.var_compare import DEFAULT_COMPARE_METHODOLOGIES, compare_methodologies
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService
from app.services.risk_factories import (
    SYNTHETIC_HISTORICAL_DATASET_ID,
    build_portfolio_service,
    dataset_identity,
)

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)

# Small path length keeps FULL_REVALUATION tests fast while preserving quantile shape.
_OBS = 40
_SEED = 11
_TOL = 1e-9


def _engine() -> HistoricalRiskEngine:
    return HistoricalRiskEngine(seed=_SEED, observations=_OBS)


def test_compare_returns_all_three_methodologies():
    report = compare_methodologies(
        SAMPLE_PORTFOLIO, BuiltinPricingEngine(), risk_engine=_engine(), market=SAMPLE_MARKET
    )
    assert report.portfolio_id == SAMPLE_PORTFOLIO.id
    assert report.observations == _OBS
    assert [r.methodology for r in report.results] == list(DEFAULT_COMPARE_METHODOLOGIES)


def test_compare_metrics_match_direct_engine_calculate():
    pricing = BuiltinPricingEngine()
    engine = _engine()
    report = compare_methodologies(
        SAMPLE_PORTFOLIO, pricing, risk_engine=engine, market=SAMPLE_MARKET
    )
    for row in report.results:
        direct = engine.calculate(
            SAMPLE_PORTFOLIO, pricing, methodology=row.methodology, market=SAMPLE_MARKET
        )
        assert math.isclose(row.var_95, direct.var_95, rel_tol=0.0, abs_tol=_TOL)
        assert math.isclose(row.var_99, direct.var_99, rel_tol=0.0, abs_tol=_TOL)
        assert math.isclose(
            row.expected_shortfall_99,
            direct.expected_shortfall_99,
            rel_tol=0.0,
            abs_tol=_TOL,
        )
        assert row.runtime_ms >= 0.0


def test_compare_var_es_ordering_per_methodology():
    report = compare_methodologies(
        SAMPLE_PORTFOLIO, BuiltinPricingEngine(), risk_engine=_engine(), market=SAMPLE_MARKET
    )
    for row in report.results:
        assert row.var_99 >= row.var_95 >= 0.0
        assert row.expected_shortfall_99 >= row.var_99


def test_compare_zero_positions_zero_risk():
    empty = Portfolio(id="empty", name="Empty", base_currency="USD", positions=[])
    report = compare_methodologies(
        empty,
        BuiltinPricingEngine(),
        risk_engine=_engine(),
        market=MarketSnapshot(id="empty"),
    )
    for row in report.results:
        assert row.var_95 == 0.0
        assert row.var_99 == 0.0
        assert row.expected_shortfall_99 == 0.0


def test_linear_equals_delta_gamma_when_gamma_zero():
    """LINEAR and DELTA_GAMMA share first-order terms; differ only by ½γ r²."""
    equity_only = Portfolio(
        id="eq",
        name="Equity only",
        base_currency="USD",
        positions=[
            p for p in SAMPLE_PORTFOLIO.positions if isinstance(p, EquityPosition)
        ][:1],
    )
    pricing = BuiltinPricingEngine()
    engine = _engine()
    market = SAMPLE_MARKET
    greeks = engine.calculate(
        equity_only, pricing, methodology=VaRMethodology.LINEAR, market=market
    )
    assert abs(greeks.gamma) < 1e-12
    report = compare_methodologies(
        equity_only,
        pricing,
        risk_engine=engine,
        methodologies=(VaRMethodology.LINEAR, VaRMethodology.DELTA_GAMMA),
        market=market,
    )
    linear, dg = report.results
    assert math.isclose(linear.var_95, dg.var_95, rel_tol=0.0, abs_tol=_TOL)
    assert math.isclose(linear.var_99, dg.var_99, rel_tol=0.0, abs_tol=_TOL)
    assert math.isclose(
        linear.expected_shortfall_99,
        dg.expected_shortfall_99,
        rel_tol=0.0,
        abs_tol=_TOL,
    )


def test_service_compare_var_methodologies():
    svc = PortfolioService(BuiltinPricingEngine(), _engine())
    report = svc.compare_var_methodologies(SAMPLE_PORTFOLIO)
    assert len(report.results) == 3
    assert {r.methodology for r in report.results} == set(DEFAULT_COMPARE_METHODOLOGIES)


def test_var_compare_api():
    with TestClient(app) as client:
        portfolio = client.get("/portfolio").json()
        response = client.post(f"/risk/var/compare?observations={_OBS}", json=portfolio)
        assert response.status_code == 200
        payload = response.json()
        assert payload["portfolio_id"] == portfolio["id"]
        assert payload["observations"] == _OBS
        assert [r["methodology"] for r in payload["results"]] == [
            "LINEAR",
            "DELTA_GAMMA",
            "FULL_REVALUATION",
        ]
        for row in payload["results"]:
            assert row["var_99"] >= row["var_95"] >= 0.0
            assert row["expected_shortfall_99"] >= row["var_99"]
            assert row["runtime_ms"] >= 0.0


def test_compare_var_keeps_panel_dataset_and_market_identity():
    """Review Test E: shrinking observations must not switch to four-macro synthetic."""
    service = build_portfolio_service(
        historical_dataset_id=SYNTHETIC_HISTORICAL_DATASET_ID,
        observations=_OBS,
        seed=_SEED,
    )
    panel = service.risk.factor_panel
    assert panel is not None
    original_factors = tuple(panel_factor_identity(f) for f in panel.factors)
    original_dataset = dataset_identity(service.risk.dataset)
    market = service.market_snapshot(SAMPLE_PORTFOLIO)

    default_report = service.compare_var_methodologies(SAMPLE_PORTFOLIO)
    custom_report = service.compare_var_methodologies(SAMPLE_PORTFOLIO, observations=10)

    assert tuple(panel_factor_identity(f) for f in service.risk.factor_panel.factors) == original_factors
    assert dataset_identity(service.risk.dataset) == original_dataset
    assert service.market_snapshot(SAMPLE_PORTFOLIO) is market
    assert default_report.observations == _OBS
    assert custom_report.observations == 10
    assert default_report.portfolio_id == custom_report.portfolio_id == SAMPLE_PORTFOLIO.id

    truncated = HistoricalFactorPanel.from_pairs(
        dates=panel.dates[:10],
        rows=[
            [(factor, obs.change(factor)) for factor in panel.factors]
            for obs in panel.observations[:10]
        ],
    )
    resized = HistoricalRiskEngine(
        seed=service.risk.seed,
        observations=10,
        dataset=service.risk.dataset,
        methodology=service.risk.methodology,
        scenario_kernel=service.risk.scenario_kernel,
        scenario_backend=service.risk.scenario_backend,
        factor_panel=truncated,
    )
    assert tuple(panel_factor_identity(f) for f in resized.factor_panel.factors) == original_factors
    assert dataset_identity(resized.dataset) == original_dataset

    expected = resized.calculate(
        SAMPLE_PORTFOLIO,
        service.pricing,
        methodology=VaRMethodology.DELTA_GAMMA,
        market=market,
    )
    custom_dg = next(r for r in custom_report.results if r.methodology is VaRMethodology.DELTA_GAMMA)
    assert math.isclose(custom_dg.var_99, expected.var_99, rel_tol=0.0, abs_tol=_TOL)
    assert math.isclose(custom_dg.var_95, expected.var_95, rel_tol=0.0, abs_tol=_TOL)
    assert math.isclose(
        custom_dg.expected_shortfall_99,
        expected.expected_shortfall_99,
        rel_tol=0.0,
        abs_tol=_TOL,
    )

    bare = HistoricalRiskEngine(seed=_SEED, observations=10)
    bare_result = bare.calculate(
        SAMPLE_PORTFOLIO,
        service.pricing,
        methodology=VaRMethodology.DELTA_GAMMA,
        market=market,
    )
    assert custom_dg.var_99 != bare_result.var_99


def test_compare_var_rejects_observations_beyond_file_dataset(tmp_path):
    path = tmp_path / "short_hist.csv"
    path.write_text(
        "equity_return,vol_move,rate_move_bps,fx_return\n"
        "0.01,0.0,1.0,0.001\n"
        "-0.02,0.05,-2.0,-0.001\n"
        "0.0,-0.01,0.0,0.0\n",
        encoding="utf-8",
    )
    service = build_portfolio_service(historical_dataset_id=str(path))
    with pytest.raises(ValueError, match="observation"):
        service.compare_var_methodologies(SAMPLE_PORTFOLIO, observations=10)
