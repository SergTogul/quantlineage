"""M10.1: themed demo portfolios (Equity Vol / Rates Macro / Cross-Asset)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.models import (
    BondPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    SwapPosition,
)
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import SqlAlchemyPortfolioRepository
from app.pricing.builtin import BuiltinPricingEngine
from app.sample import (
    CROSS_ASSET_PORTFOLIO,
    DEMO_PORTFOLIOS,
    DEMO_PORTFOLIOS_BY_ID,
    EQUITY_VOL_PORTFOLIO,
    RATES_MACRO_PORTFOLIO,
    SAMPLE_PORTFOLIO,
    demo_market_snapshot,
    demo_portfolio_summaries,
    get_demo_portfolio,
)


def _position_types(portfolio) -> set[str]:
    return {p.type for p in portfolio.positions}


def test_demo_catalog_has_three_themes_and_stable_default():
    assert len(DEMO_PORTFOLIOS) == 3
    assert {p.id for p in DEMO_PORTFOLIOS} == {"equity-vol", "rates-macro", "global-macro"}
    assert SAMPLE_PORTFOLIO is CROSS_ASSET_PORTFOLIO
    assert SAMPLE_PORTFOLIO.id == "global-macro"
    assert SAMPLE_PORTFOLIO.name == "Global Macro Demo"

    summaries = demo_portfolio_summaries()
    assert [s.theme for s in summaries] == ["equity_vol", "rates_macro", "cross_asset"]
    assert [s.id for s in summaries] == ["equity-vol", "rates-macro", "global-macro"]
    for summary, portfolio in zip(summaries, DEMO_PORTFOLIOS, strict=True):
        assert summary.position_count == len(portfolio.positions)
        assert summary.name == portfolio.name


def test_get_demo_portfolio_lookup():
    assert get_demo_portfolio("equity-vol") is EQUITY_VOL_PORTFOLIO
    assert get_demo_portfolio("rates-macro") is RATES_MACRO_PORTFOLIO
    assert get_demo_portfolio("global-macro") is CROSS_ASSET_PORTFOLIO
    assert get_demo_portfolio("missing") is None
    assert set(DEMO_PORTFOLIOS_BY_ID) == {p.id for p in DEMO_PORTFOLIOS}


def test_equity_vol_theme_composition():
    types = _position_types(EQUITY_VOL_PORTFOLIO)
    assert types <= {"equity", "european_option", "equity_future"}
    assert "equity" in types and "european_option" in types
    assert not any(
        isinstance(p, (BondPosition, SwapPosition, FXForwardPosition, FXOptionPosition, InterestRateFuturePosition))
        for p in EQUITY_VOL_PORTFOLIO.positions
    )
    assert EQUITY_VOL_PORTFOLIO.desk == "Equity Derivatives"
    assert EQUITY_VOL_PORTFOLIO.strategy == "Vol Trading"


def test_rates_macro_theme_composition():
    types = _position_types(RATES_MACRO_PORTFOLIO)
    assert types <= {"bond", "swap", "ir_future"}
    assert "bond" in types and "swap" in types and "ir_future" in types
    assert not any(
        isinstance(
            p,
            (
                EquityPosition,
                EquityFuturePosition,
                EuropeanOptionPosition,
                FXForwardPosition,
                FXOptionPosition,
            ),
        )
        for p in RATES_MACRO_PORTFOLIO.positions
    )
    assert RATES_MACRO_PORTFOLIO.desk == "Rates"
    assert RATES_MACRO_PORTFOLIO.strategy == "Macro Rates"


def test_cross_asset_theme_spans_equity_rates_fx():
    types = _position_types(CROSS_ASSET_PORTFOLIO)
    assert {"equity", "european_option", "bond", "swap", "fx_forward", "fx_option"} <= types


def test_demo_position_ids_unique_within_and_marks_priceable():
    pricing = BuiltinPricingEngine()
    for portfolio in DEMO_PORTFOLIOS:
        ids = [p.id for p in portfolio.positions]
        assert len(ids) == len(set(ids))
        market = demo_market_snapshot(portfolio)
        values = [pricing.value(p, market).market_value for p in portfolio.positions]
        assert all(isinstance(v, float) for v in values)
        assert abs(sum(values)) > 0.0


def test_list_and_get_demo_portfolio_api(clear_db_url):
    from app.main import app

    with TestClient(app) as client:
        listed = client.get("/api/v1/portfolios")
        assert listed.status_code == 200
        body = listed.json()
        assert len(body) == 3
        assert [row["id"] for row in body] == ["equity-vol", "rates-macro", "global-macro"]
        assert [row["theme"] for row in body] == ["equity_vol", "rates_macro", "cross_asset"]

        legacy = client.get("/portfolios")
        assert legacy.status_code == 200
        assert legacy.json() == body
        assert "Deprecation" in legacy.headers

        for portfolio_id in ("equity-vol", "rates-macro", "global-macro"):
            resp = client.get(f"/api/v1/portfolios/{portfolio_id}")
            assert resp.status_code == 200
            assert resp.json()["id"] == portfolio_id
            assert len(resp.json()["positions"]) == len(DEMO_PORTFOLIOS_BY_ID[portfolio_id].positions)

        missing = client.get("/api/v1/portfolios/does-not-exist")
        assert missing.status_code == 404
        err = missing.json()
        assert err["code"] == "demo_portfolio_not_found"
        assert err["details"]["portfolio_id"] == "does-not-exist"

        # Default GET /portfolio still serves Cross-Asset sample.
        default = client.get("/api/v1/portfolio")
        assert default.status_code == 200
        assert default.json()["id"] == SAMPLE_PORTFOLIO.id


def test_sqlalchemy_seed_includes_all_demo_portfolios(monkeypatch, tmp_path, clear_db_url):
    db_path = tmp_path / "m101_demos.db"
    monkeypatch.setenv("RISKFORGE_DATABASE_URL", f"sqlite:///{db_path}")

    from app.main import app

    with TestClient(app) as client:
        assert client.app.state.persistence_enabled is True
        with session_scope(client.app.state.session_factory) as session:
            repo = SqlAlchemyPortfolioRepository(session)
            ids = repo.list_ids()
            assert set(ids) >= {p.id for p in DEMO_PORTFOLIOS}
            for portfolio in DEMO_PORTFOLIOS:
                stored = repo.get(portfolio.id)
                assert stored is not None
                assert stored.name == portfolio.name
                assert len(stored.positions) == len(portfolio.positions)


@pytest.fixture
def clear_db_url(monkeypatch):
    monkeypatch.delenv("RISKFORGE_DATABASE_URL", raising=False)
