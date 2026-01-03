"""M2.8 Incremental VaR — VaR(P') − VaR(P) for hypothetical portfolio changes.

Conventions:
- Units: currency loss (same as HistoricalRiskEngine / RiskSummary)
- Sign: positive incremental VaR ⇒ change increases portfolio VaR
- Default methodology: DELTA_GAMMA
- Tolerance: abs 1e-9 vs independent before/after calculate()
"""

from __future__ import annotations

import math

import pytest

from app.domain.models import EquityPosition, Portfolio, VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.incremental_var import (
    apply_what_if_changes,
    incremental_var,
)
from app.sample import SAMPLE_PORTFOLIO

_TOL = 1e-9
_SEED = 7
_OBS = 80


def _engine() -> HistoricalRiskEngine:
    return HistoricalRiskEngine(seed=_SEED, observations=_OBS)


def _new_equity(position_id: str = "eq-hypo", quantity: float = 500.0) -> EquityPosition:
    return EquityPosition(
        type="equity",
        id=position_id,
        symbol="SPY",
        quantity=quantity,
        price=565.0,
        sector="ETF",
    )


def test_apply_add_does_not_mutate_base_portfolio():
    base = SAMPLE_PORTFOLIO.model_copy(deep=True)
    n_before = len(base.positions)
    ids_before = [p.id for p in base.positions]
    after = apply_what_if_changes(base, [{"operation": "add", "position": _new_equity()}])
    assert len(base.positions) == n_before
    assert [p.id for p in base.positions] == ids_before
    assert len(after.positions) == n_before + 1
    assert any(p.id == "eq-hypo" for p in after.positions)


def test_apply_remove_and_modify():
    base = SAMPLE_PORTFOLIO
    removed = apply_what_if_changes(base, [{"operation": "remove", "position_id": "eq-spy"}])
    assert all(p.id != "eq-spy" for p in removed.positions)
    assert len(removed.positions) == len(base.positions) - 1

    modified_pos = _new_equity("eq-spy", quantity=50.0)
    modified = apply_what_if_changes(
        base,
        [{"operation": "modify", "position_id": "eq-spy", "position": modified_pos}],
    )
    spy = next(p for p in modified.positions if p.id == "eq-spy")
    assert spy.quantity == 50.0
    assert len(modified.positions) == len(base.positions)


def test_apply_rejects_invalid_ops():
    with pytest.raises(ValueError, match="unknown position"):
        apply_what_if_changes(SAMPLE_PORTFOLIO, [{"operation": "remove", "position_id": "missing"}])
    with pytest.raises(ValueError, match="already exists"):
        apply_what_if_changes(
            SAMPLE_PORTFOLIO,
            [{"operation": "add", "position": _new_equity("eq-spy")}],
        )


def test_incremental_var_equals_after_minus_before():
    pricing = BuiltinPricingEngine()
    engine = _engine()
    trade = _new_equity()
    result = incremental_var(
        SAMPLE_PORTFOLIO,
        pricing,
        changes=[{"operation": "add", "position": trade}],
        risk_engine=engine,
        methodology=VaRMethodology.DELTA_GAMMA,
    )
    before = engine.calculate(SAMPLE_PORTFOLIO, pricing, methodology=VaRMethodology.DELTA_GAMMA)
    after_pf = apply_what_if_changes(SAMPLE_PORTFOLIO, [{"operation": "add", "position": trade}])
    after = engine.calculate(after_pf, pricing, methodology=VaRMethodology.DELTA_GAMMA)

    assert math.isclose(result.before.var_99, before["var_99"], abs_tol=_TOL)
    assert math.isclose(result.after.var_99, after["var_99"], abs_tol=_TOL)
    assert math.isclose(
        result.incremental.var_99,
        after["var_99"] - before["var_99"],
        abs_tol=_TOL,
    )
    assert math.isclose(
        result.incremental.var_95,
        after["var_95"] - before["var_95"],
        abs_tol=_TOL,
    )
    assert math.isclose(
        result.incremental.expected_shortfall_99,
        after["expected_shortfall_99"] - before["expected_shortfall_99"],
        abs_tol=_TOL,
    )


def test_removing_all_risk_positions_reduces_var():
    """Removing a long equity sleeve should not increase VaR (typically lowers it)."""
    pricing = BuiltinPricingEngine()
    engine = _engine()
    result = incremental_var(
        SAMPLE_PORTFOLIO,
        pricing,
        changes=[{"operation": "remove", "position_id": "eq-nvda"}],
        risk_engine=engine,
    )
    assert result.incremental.var_99 <= 0.0 + _TOL


def test_empty_changes_zero_incremental():
    pricing = BuiltinPricingEngine()
    engine = _engine()
    result = incremental_var(SAMPLE_PORTFOLIO, pricing, changes=[], risk_engine=engine)
    assert result.incremental.var_99 == 0.0
    assert result.incremental.var_95 == 0.0
    assert result.incremental.expected_shortfall_99 == 0.0
    assert result.after.var_99 == result.before.var_99


def test_zero_portfolio_add_trade_incremental_equals_standalone_var():
    empty = Portfolio(id="empty", name="Empty", positions=[])
    trade = _new_equity()
    pricing = BuiltinPricingEngine()
    engine = _engine()
    result = incremental_var(
        empty,
        pricing,
        changes=[{"operation": "add", "position": trade}],
        risk_engine=engine,
    )
    standalone = engine.calculate(
        Portfolio(id="t", name="t", positions=[trade]),
        pricing,
    )
    assert result.before.var_99 == 0.0
    assert math.isclose(result.incremental.var_99, standalone["var_99"], abs_tol=_TOL)
