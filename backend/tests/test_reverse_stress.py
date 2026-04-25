"""M3.5 single-factor reverse stress tests.

Acceptance:
- Numerical solve: smallest adverse factor move whose loss % of |NAV| meets target
- Returns target loss (absolute), solved shock, resulting P&L, convergence info
- Uses typed RiskFactor / formal Scenario internally
- ``POST /risk/stress/reverse`` wire fields stay compatible
- Convergence and no-solution cases covered

Units / sign:
- equity / fx: relative adverse down-move; ``required_shock`` is magnitude
- vol: relative vol-up; ``required_shock`` is magnitude
- rates: ``required_shock`` in bp (legacy scale: max_shock=0.80 → 800bp bound;
  always relative-style magnitude — never ``max_shock > 1`` → bp heuristic)
- loss = max(0, -pnl); loss_pct = loss / |base_mv|
- Tolerances: abs 1e-6 on loss fraction; abs 1e-4 on pnl / |NAV| reconciliation
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.models import MarketSnapshot, Portfolio
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, RateZero
from app.risk.reverse_stress import (
    ReverseStressEngine,
    build_reverse_scenario,
    build_single_factor_shocks,
    from_wire_bound,
    to_wire_shock,
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
    return ReverseStressEngine()


def test_build_single_factor_shocks_use_typed_risk_factors():
    base = MarketSnapshot(
        id="b",
        equity_spots={"SPY": 100.0},
        equity_vols={"SPY": 0.2},
        fx_spots={"EURUSD": 1.1},
        fx_vols={"EURUSD": 0.1},
        rates={"USD": 0.04},
    )
    eq = build_single_factor_shocks("equity", 0.1, base)
    assert len(eq) == 1
    assert isinstance(eq[0].factor, EquitySpot)
    assert eq[0].amount == pytest.approx(-0.1)

    vol = build_single_factor_shocks("vol", 0.25, base)
    assert any(isinstance(s.factor, EquityVol) and s.amount == pytest.approx(0.25) for s in vol)

    fx = build_single_factor_shocks("fx", 0.05, base)
    assert isinstance(fx[0].factor, FXSpot) and fx[0].amount == pytest.approx(-0.05)

    rates = build_single_factor_shocks("rates", 0.1, base)  # 100bp → 0.01 decimal
    assert isinstance(rates[0].factor, RateZero)
    assert rates[0].amount == pytest.approx(0.01)


def test_reverse_scenario_is_formal_reverse_category():
    base = MarketSnapshot(id="b", equity_spots={"SPY": 100.0}, equity_vols={}, fx_spots={}, fx_vols={}, rates={})
    scenario = build_reverse_scenario("equity", 0.12, base)
    assert scenario.category == ScenarioCategory.REVERSE
    assert scenario.id == "reverse"
    assert not scenario.is_empty


def test_zero_magnitude_builds_empty_shocks():
    base = MarketSnapshot(id="b", equity_spots={"SPY": 100.0}, equity_vols={}, fx_spots={}, fx_vols={}, rates={})
    assert build_single_factor_shocks("equity", 0.0, base) == ()
    assert build_reverse_scenario("equity", 0.0, base).is_empty


def test_equity_reverse_stress_converges_to_target(engine, pricing):
    target = 0.01
    result = engine.solve(SAMPLE_PORTFOLIO, pricing, target, "equity", 0.8, market=SAMPLE_MARKET)
    assert result.converged is True
    assert result.required_shock is not None
    assert 0 < result.required_shock <= 0.8
    assert result.achieved_loss_pct + 1e-6 >= target
    assert result.shock_unit == "relative"
    assert result.target_loss == pytest.approx(target * abs(result.base_market_value), rel=0, abs=1e-6)
    assert result.pnl < 0
    assert result.convergence is not None
    assert result.convergence.method == "binary_search"
    assert result.convergence.iterations >= 1
    # Loss fraction reconciles with |pnl| / |NAV|
    assert abs(-result.pnl) / abs(result.base_market_value) == pytest.approx(
        result.achieved_loss_pct, rel=0, abs=1e-4
    )


def test_equity_reverse_stress_deterministic(engine, pricing):
    a = engine.solve(SAMPLE_PORTFOLIO, pricing, 0.02, "equity", 0.8, market=SAMPLE_MARKET)
    b = engine.solve(SAMPLE_PORTFOLIO, pricing, 0.02, "equity", 0.8, market=SAMPLE_MARKET)
    assert a.model_dump() == b.model_dump()


def test_no_solution_within_bound(engine, pricing):
    # Unreachable: demand 50% NAV loss but only allow a 1bp-scale equity move.
    result = engine.solve(
        SAMPLE_PORTFOLIO, pricing, 0.50, "equity", max_shock=0.001, market=SAMPLE_MARKET
    )
    assert result.converged is False
    assert result.required_shock is None
    assert result.achieved_loss_pct < 0.50
    assert result.convergence is not None
    assert "not reachable" in (result.convergence.message or "").lower()
    assert result.target_loss > 0
    # P&L still reported at the bound.
    assert result.pnl <= 0


def test_vol_reverse_stress_returns_relative_shock(engine, pricing):
    result = engine.solve(SAMPLE_PORTFOLIO, pricing, 0.005, "vol", 0.8, market=SAMPLE_MARKET)
    if result.converged:
        assert result.shock_unit == "relative"
        assert result.required_shock is not None and result.required_shock > 0
        assert result.achieved_loss_pct + 1e-6 >= 0.005
    else:
        # Sample book may be vol-insensitive enough that small targets still fail —
        # document either outcome via convergence payload.
        assert result.required_shock is None
        assert result.convergence is not None


def test_rates_wire_units_bp(engine, pricing):
    assert to_wire_shock("rates", 0.1) == pytest.approx(100.0)
    assert from_wire_bound("rates", 0.80) == pytest.approx(0.80)
    # Breaking change (R0.4.3-B / RF-004): no magnitude heuristic. ``500`` is
    # *not* reinterpreted as 500 bp; pass ``0.5`` → 500 bp via RATES_BP_SCALE.
    assert from_wire_bound("rates", 500.0) == pytest.approx(500.0)
    assert to_wire_shock("rates", 0.5) == pytest.approx(500.0)
    assert from_wire_bound("rates", 0.5) == pytest.approx(0.5)

    result = engine.solve(SAMPLE_PORTFOLIO, pricing, 0.002, "rates", 0.8, market=SAMPLE_MARKET)
    assert result.shock_unit == "bp"
    if result.converged:
        assert result.required_shock is not None
        # Bound is 800bp when max_shock=0.8
        assert 0 < result.required_shock <= 800.0 + 1e-6
        assert result.convergence.search_bound == pytest.approx(800.0)


def test_rates_from_wire_bound_no_magnitude_heuristic():
    """RF-004: unit choice must not depend on whether max_shock > 1."""
    import inspect

    import app.risk.reverse_stress as reverse_stress_mod

    source = inspect.getsource(from_wire_bound)
    assert "max_shock > 1" not in source
    assert "/ RATES_BP_SCALE" not in source
    # Same pass-through for ≤1 and >1; wire bp only via to_wire_shock scale.
    assert from_wire_bound("rates", 0.80) == pytest.approx(0.80)
    assert from_wire_bound("rates", 1.0) == pytest.approx(1.0)
    assert from_wire_bound("rates", 1.01) == pytest.approx(1.01)
    assert from_wire_bound("rates", 500.0) == pytest.approx(500.0)
    assert from_wire_bound("rates", 500.0) != pytest.approx(0.5)
    assert to_wire_shock("rates", from_wire_bound("rates", 0.5)) == pytest.approx(500.0)
    # Equity/vol/fx also pass through without magnitude branching.
    assert from_wire_bound("equity", 500.0) == pytest.approx(500.0)
    assert "if max_shock > 1.0" not in inspect.getsource(reverse_stress_mod)


def test_service_and_api_compatibility():
    from app.risk.historical import HistoricalRiskEngine

    svc = PortfolioService(BuiltinPricingEngine(), HistoricalRiskEngine())
    result = svc.reverse_stress(SAMPLE_PORTFOLIO, 0.01, "equity", 0.8)
    assert result.converged
    assert 0 < result.required_shock <= 0.8
    assert result.achieved_loss_pct >= 0.01
    # New fields present without breaking legacy consumers
    assert result.target_loss > 0
    assert result.pnl < 0
    assert result.convergence is not None

    with TestClient(app) as client:
        portfolio = client.get("/portfolio").json()
        rev = client.post(
            "/risk/stress/reverse",
            json={"portfolio": portfolio, "target_loss_pct": 0.01, "factor": "equity"},
        )
        assert rev.status_code == 200, rev.text
        body = rev.json()
        assert body["converged"] is True
        assert body["required_shock"] is not None
        assert "target_loss" in body
        assert "pnl" in body
        assert body["convergence"]["method"] == "binary_search"


def test_invalid_factor_raises(engine, pricing):
    with pytest.raises(ValueError, match="unsupported"):
        engine.solve(SAMPLE_PORTFOLIO, pricing, 0.01, "commodity", 0.8, market=SAMPLE_MARKET)


def test_empty_portfolio_no_factor_exposure(engine, pricing):
    empty = Portfolio(id="empty", name="Empty", positions=[])
    result = engine.solve(empty, pricing, 0.01, "equity", 0.8, market=MarketSnapshot(id="empty"))
    assert result.converged is False
    assert result.required_shock is None
    assert result.achieved_loss_pct == pytest.approx(0.0)
    assert result.pnl == pytest.approx(0.0)
