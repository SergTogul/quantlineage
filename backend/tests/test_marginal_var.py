"""M2.7 Marginal VaR — parametric Euler derivative of portfolio VaR.

Methodology:
- Same P&L construction as Component VaR (LINEAR | DELTA_GAMMA | FULL_REVALUATION)
- Parametric VaR_α = z_α · σ_P with σ_P = sample std(Σ X_i), z_α = Φ⁻¹(α)
- Marginal VaR_i = ∂VaR/∂w_i |_{w=1} = z_α · Cov(X_i, X_P) / σ_P
- Euler: Component VaR_i = w_i · Marginal VaR_i; at current holdings (w_i ≡ 1 for
  each position's P&L series), Component_i = Marginal_i and Σ Component = VaR
- Finite-difference check: scale position i P&L by (1+ε), ΔVaR/ε ≈ Marginal_i

Conventions:
- Units: currency risk per unit scale of the position's current P&L
- Sign: negative Marginal VaR means increasing the position reduces parametric VaR
- Tolerances: analytical equality abs 1e-9; FD vs analytical rel 5e-2 / abs 1e-4
"""

from __future__ import annotations

import math

import numpy as np

from app.domain.models import (
    EquityPosition,
    EuropeanOptionPosition,
    Portfolio,
    VaRMethodology,
)
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.marginal_var import finite_difference_marginal_var, parametric_marginal_vars
from app.risk.var import VaRAnalytics
from app.sample import SAMPLE_PORTFOLIO


def _mixed_series(n: int = 100) -> FactorObservationSeries:
    rng = np.random.default_rng(11)
    return FactorObservationSeries(
        equity_returns=rng.normal(-0.001, 0.02, n),
        vol_moves=rng.normal(0.0, 0.08, n),
        rate_moves_bps=rng.normal(0.0, 4.0, n),
        fx_returns=rng.normal(0.0, 0.008, n),
    )


def _book() -> Portfolio:
    return Portfolio(
        id="mvar_book",
        name="Marginal VaR Book",
        positions=[
            EquityPosition(
                type="equity",
                id="eq",
                symbol="SPY",
                quantity=800,
                price=100.0,
            ),
            EuropeanOptionPosition(
                type="european_option",
                id="put",
                symbol="SPY",
                quantity=400,
                spot=100.0,
                strike=95.0,
                maturity_years=0.5,
                volatility=0.27,
                risk_free_rate=0.04,
                option_type="put",
            ),
        ],
    )


def test_marginal_var_equals_component_at_unit_weights_delta_gamma():
    pricing = BuiltinPricingEngine()
    report = VaRAnalytics(dataset=ArrayHistoricalDataset(_mixed_series())).report(
        _book(), pricing, confidence=0.99, methodology=VaRMethodology.DELTA_GAMMA
    )
    assert all(hasattr(c, "marginal_var") for c in report.contributions)
    for c in report.contributions:
        assert math.isclose(c.marginal_var, c.component_var, rel_tol=1e-9, abs_tol=1e-9)


def test_marginal_var_equals_component_under_full_revaluation():
    pricing = BuiltinPricingEngine()
    report = VaRAnalytics(dataset=ArrayHistoricalDataset(_mixed_series())).report(
        SAMPLE_PORTFOLIO,
        pricing,
        confidence=0.95,
        methodology=VaRMethodology.FULL_REVALUATION,
    )
    pvar = next(m.var for m in report.methods if m.method == "parametric")
    assert pvar > 0
    for c in report.contributions:
        assert math.isclose(c.marginal_var, c.component_var, rel_tol=1e-9, abs_tol=1e-9)


def test_parametric_marginal_matches_finite_difference():
    """Independent FD check of ∂VaR/∂w_i on synthetic P&L series."""
    rng = np.random.default_rng(3)
    n = 200
    x1 = rng.normal(0, 1.0, n)
    x2 = 0.4 * x1 + rng.normal(0, 0.8, n)
    pos = {"a": x1, "b": x2}
    z = 2.3263478740408408  # ~ Φ⁻¹(0.99)
    analytical = parametric_marginal_vars(pos, z)
    for pid in pos:
        fd = finite_difference_marginal_var(pos, pid, z, epsilon=1e-5)
        assert math.isclose(analytical[pid], fd, rel_tol=5e-2, abs_tol=1e-4)


def test_zero_risk_portfolio_has_zero_marginal_var():
    z = np.zeros(50)
    series = FactorObservationSeries(
        equity_returns=z.copy(),
        vol_moves=z.copy(),
        rate_moves_bps=z.copy(),
        fx_returns=z.copy(),
    )
    report = VaRAnalytics(dataset=ArrayHistoricalDataset(series)).report(
        _book(), BuiltinPricingEngine(), methodology=VaRMethodology.DELTA_GAMMA
    )
    assert all(c.marginal_var == 0.0 for c in report.contributions)
