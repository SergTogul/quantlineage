"""Parametric Component / Marginal VaR (Euler allocation).

Methodology
-----------
Given position P&L series ``X_i`` (from LINEAR, DELTA_GAMMA, or FULL_REVALUATION)
and portfolio P&L ``X = Σ_i X_i``:

- Sample std ``σ_P = std(X)`` (ddof=1), variance ``Var(X)`` (ddof=1)
- Normal parametric VaR at confidence α: ``VaR = max(0, z_α · σ_P)``
  with ``z_α = Φ⁻¹(α)``
- **Marginal VaR** (Euler derivative at current holdings)::

      MVaR_i = ∂VaR/∂w_i |_{w=1} = z_α · Cov(X_i, X) / σ_P

  when ``σ_P > 0``; else 0. Here ``w_i`` scales position *i*'s P&L.
- **Component VaR** (homogeneous allocation)::

      CVaR_i = VaR · Cov(X_i, X) / Var(X) = w_i · MVaR_i

  At current holdings (``w_i ≡ 1`` for each position's P&L series),
  ``CVaR_i = MVaR_i`` and ``Σ_i CVaR_i = VaR``.

Units / signs
-------------
- Currency units matching PricingEngine market_value / P&L.
- Negative MVaR/CVaR means the position is a hedge (reduces parametric VaR).

Not implemented here
--------------------
- Historical (quantile) component/marginal VaR
- Incremental VaR (discrete removal) — Milestone M2.8
- Per-notional normalization of Marginal VaR
"""

from __future__ import annotations

import numpy as np


def parametric_component_var(
    position_pnl: np.ndarray,
    portfolio_pnl: np.ndarray,
    portfolio_var: float,
) -> float:
    """Euler component of parametric VaR for one position."""
    if portfolio_var <= 0 or len(portfolio_pnl) < 2:
        return 0.0
    variance = float(np.var(portfolio_pnl, ddof=1))
    if variance <= 0:
        return 0.0
    cov = float(np.cov(position_pnl, portfolio_pnl, ddof=1)[0, 1])
    return portfolio_var * cov / variance


def parametric_marginal_var(
    position_pnl: np.ndarray,
    portfolio_pnl: np.ndarray,
    z: float,
) -> float:
    """∂VaR/∂w_i at unit weight for normal parametric VaR = z · σ."""
    if len(portfolio_pnl) < 2:
        return 0.0
    sigma = float(np.std(portfolio_pnl, ddof=1))
    if sigma <= 0:
        return 0.0
    cov = float(np.cov(position_pnl, portfolio_pnl, ddof=1)[0, 1])
    return z * cov / sigma


def parametric_marginal_vars(position_pnls: dict[str, np.ndarray], z: float) -> dict[str, float]:
    """Marginal VaR for each position id given P&L series and z-score."""
    if not position_pnls:
        return {}
    n = next(iter(position_pnls.values())).shape[0]
    total = sum(position_pnls.values(), start=np.zeros(n))
    return {pid: parametric_marginal_var(pnl, total, z) for pid, pnl in position_pnls.items()}


def finite_difference_marginal_var(
    position_pnls: dict[str, np.ndarray],
    position_id: str,
    z: float,
    epsilon: float = 1e-5,
) -> float:
    """Central finite-difference estimate of ∂VaR/∂w_i (parametric).

    Scales ``position_id`` P&L by ``(1±ε)``, recomputes ``z · σ``, returns ΔVaR/(2ε).
    """
    if position_id not in position_pnls:
        raise KeyError(position_id)
    n = next(iter(position_pnls.values())).shape[0]

    def _var(scale: float) -> float:
        total = np.zeros(n)
        for pid, pnl in position_pnls.items():
            total = total + (pnl * scale if pid == position_id else pnl)
        sigma = float(np.std(total, ddof=1)) if n > 1 else 0.0
        return max(0.0, z * sigma)

    return (_var(1.0 + epsilon) - _var(1.0 - epsilon)) / (2.0 * epsilon)
