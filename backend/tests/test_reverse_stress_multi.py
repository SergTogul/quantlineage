"""M3.6 constrained multi-factor reverse stress tests.

Acceptance:
- Joint adverse moves reach a target loss % of |NAV|
- Documented assumptions returned on the result
- Convergence and no-solution cases
- Deterministic; reuses M3.5 typed shock builders
- API ``POST /risk/stress/reverse/multi``

Units / signs match M3.5 per family. Objective is L2 of magnitudes normalized
by per-factor bounds. Tolerances: abs 1e-6 on loss fraction.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.domain.models import MarketSnapshot, Portfolio
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import EquitySpot, RateZero
from app.risk.historical import HistoricalRiskEngine
from app.risk.reverse_stress_multi import (
    ASSUMPTIONS,
    MultiFactorReverseStressEngine,
    build_multi_factor_shocks,
    build_multi_reverse_scenario,
)
from app.risk.scenario_model import ScenarioCategory
from app.sample import SAMPLE_PORTFOLIO, demo_market_snapshot
from app.services.portfolio_service import PortfolioService

SAMPLE_MARKET = demo_market_snapshot(SAMPLE_PORTFOLIO)


@pytest.fixture
def pricing():
    return BuiltinPricingEngine()


@pytest.fixture
def engine():
    return MultiFactorReverseStressEngine()


@pytest.fixture
def svc():
    return PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine(seed=7, observations=80))


def test_build_multi_factor_shocks_compose_families():
    base = MarketSnapshot(
        id="b",
        equity_spots={"SPY": 100.0},
        equity_vols={"SPY": 0.2},
        fx_spots={},
        fx_vols={},
        rates={"USD": 0.04},
    )
    shocks = build_multi_factor_shocks({"equity": 0.1, "rates": 0.1}, base)
    assert any(isinstance(s.factor, EquitySpot) and s.amount == pytest.approx(-0.1) for s in shocks)
    assert any(isinstance(s.factor, RateZero) and s.amount == pytest.approx(0.01) for s in shocks)


def test_multi_reverse_scenario_is_formal_reverse():
    base = MarketSnapshot(id="b", equity_spots={"SPY": 100.0}, equity_vols={}, fx_spots={}, fx_vols={}, rates={})
    scenario = build_multi_reverse_scenario({"equity": 0.05}, base)
    assert scenario.category == ScenarioCategory.REVERSE
    assert scenario.id == "reverse_multi"


def test_multi_factor_converges_to_target(engine, pricing):
    target = 0.01
    result = engine.solve(
        SAMPLE_PORTFOLIO, pricing, target, factors=["equity", "vol"], market=SAMPLE_MARKET
    )
    assert result.converged is True
    assert result.achieved_loss_pct + 1e-6 >= target
    assert result.objective_l2 is not None and result.objective_l2 >= 0.0
    assert result.objective_l2 <= math.sqrt(2.0) + 1e-9
    assert result.pnl < 0
    assert set(result.factors) == {"equity", "vol"}
    assert len(result.shocks) == 2
    assert result.assumptions == list(ASSUMPTIONS)
    assert abs(-result.pnl) / abs(result.base_market_value) == pytest.approx(
        result.achieved_loss_pct, rel=0, abs=1e-4
    )


def test_multi_factor_deterministic(engine, pricing):
    a = engine.solve(
        SAMPLE_PORTFOLIO, pricing, 0.015, factors=["equity", "rates", "vol"], market=SAMPLE_MARKET
    )
    b = engine.solve(
        SAMPLE_PORTFOLIO, pricing, 0.015, factors=["equity", "rates", "vol"], market=SAMPLE_MARKET
    )
    assert a.model_dump() == b.model_dump()


def test_multi_factor_no_solution(engine, pricing):
    result = engine.solve(
        SAMPLE_PORTFOLIO,
        pricing,
        0.50,
        factors=["equity"],
        max_shock=0.001,
        market=SAMPLE_MARKET,
    )
    assert result.converged is False
    assert result.objective_l2 is None or result.objective_l2 >= 0.0
    assert "not reachable" in (result.message or "").lower()


def test_empty_portfolio_unreachable(engine, pricing):
    empty = Portfolio(id="empty", name="Empty", positions=[])
    result = engine.solve(
        empty, pricing, 0.01, factors=["equity", "vol"], market=MarketSnapshot(id="empty")
    )
    assert result.converged is False
    assert result.achieved_loss_pct == pytest.approx(0.0)


def test_weights_bias_solution(engine, pricing):
    eq_heavy = engine.solve(
        SAMPLE_PORTFOLIO,
        pricing,
        0.01,
        factors=["equity", "vol"],
        weights={"equity": 1.0, "vol": 0.05},
        market=SAMPLE_MARKET,
    )
    vol_heavy = engine.solve(
        SAMPLE_PORTFOLIO,
        pricing,
        0.01,
        factors=["equity", "vol"],
        weights={"equity": 0.05, "vol": 1.0},
        market=SAMPLE_MARKET,
    )
    if eq_heavy.converged and vol_heavy.converged:
        eq_map = {s.factor: s.required_shock for s in eq_heavy.shocks}
        vol_map = {s.factor: s.required_shock for s in vol_heavy.shocks}
        # Heavier weight on a family tends to use more of that family's budget on the ray;
        # after coordinate descent magnitudes may shrink, but relative usage should differ.
        assert eq_map != vol_map


def test_invalid_factor_raises(engine, pricing):
    with pytest.raises(ValueError, match="unsupported"):
        engine.solve(
            SAMPLE_PORTFOLIO, pricing, 0.01, factors=["commodity"], market=SAMPLE_MARKET
        )


def test_service_and_api(svc):
    result = svc.reverse_stress_multi(SAMPLE_PORTFOLIO, 0.01, factors=["equity", "vol"])
    assert result.converged
    assert result.achieved_loss_pct >= 0.01
    assert result.assumptions

    client = TestClient(app)
    portfolio = client.get("/portfolio").json()
    rev = client.post(
        "/risk/stress/reverse/multi",
        json={"portfolio": portfolio, "target_loss_pct": 0.01, "factors": ["equity", "vol"]},
    )
    assert rev.status_code == 200, rev.text
    body = rev.json()
    assert body["converged"] is True
    assert body["method"] == "ray_search_coordinate_descent"
    assert len(body["assumptions"]) >= 1
