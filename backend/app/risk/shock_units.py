"""Canonical RF-004 shock-unit conversions for approximate P&L and sensitivities.

These helpers name dual conventions without changing numerical semantics.
Call sites must convert at the boundary rather than scattering ``/ 10_000`` or
``* 100`` literals.

Frozen internal conventions (from ``reviews/r0.4-architecture-brief.md``;
do not change silently):

| Factor family | Engine-facing amount | Notes |
|---|---|---|
| Equity / FX spot | relative return (``0.01`` = +1%) | cash delta / fx_delta |
| Equity / FX vol (``FactorShock`` / ``MarketSnapshot.bump``) | relative vol-level change | ``0.25`` = +25% of current vol |
| SensitivityEngine FD vega bump | **absolute** decimal vol (``0.01`` = +1 vol point) | vega quoted per vol point |
| Rates (``FactorShock`` / ``bump``) | absolute decimal rate (``0.0001`` = +1 bp) | |
| Historical ``rate_moves_bps`` / approx DV01 | basis points (``1.0`` = +1 bp) | convert at boundary |
| Historical ``vol_moves`` / ``vol_pct`` | relative vol move | ``×100`` → vol points for vega P&L |
| UI display % | whole percent (``20`` = 20%) | convert to fraction before API |

Dual vol conventions (intentional; do **not** unify by changing semantics):

- ``MarketSnapshot.bump(EquityVol|FXVol, amount)`` — *relative* vol-level change.
- ``SensitivityEngine`` FD vega bumps — *absolute* decimal vol points (``0.01``).
- Approximate P&L: relative ``vol_pct`` → vol points via
  :func:`relative_vol_move_to_vol_points` before multiplying by vega.
"""

from __future__ import annotations

from typing import overload

import numpy as np
from numpy.typing import NDArray


def bps_to_decimal_rate(bps: float) -> float:
    """Convert basis points to absolute decimal rate (``1.0`` bp → ``0.0001``)."""
    return float(bps) / 10_000.0


def decimal_rate_to_bps(rate: float) -> float:
    """Convert absolute decimal rate to basis points (``0.0001`` → ``1.0`` bp)."""
    return float(rate) * 10_000.0


@overload
def relative_vol_move_to_vol_points(vol_pct: float) -> float: ...


@overload
def relative_vol_move_to_vol_points(vol_pct: NDArray[np.floating]) -> NDArray[np.floating]: ...


def relative_vol_move_to_vol_points(vol_pct: float | NDArray[np.floating]) -> float | NDArray[np.floating]:
    """Convert relative vol move to vol points for vega P&L (``0.01`` → ``1.0``).

    Matches ``approximate_pnl_series``: vega is quoted per 1 vol point
    (0.01 absolute vol), so a +1% relative vol move becomes +1 vol point.
    """
    if isinstance(vol_pct, np.ndarray):
        return np.asarray(vol_pct, dtype=float) * 100.0
    return float(vol_pct) * 100.0
