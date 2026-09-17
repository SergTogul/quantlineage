"""Canonical RF-004 shock-unit conversions for approximate P&L and sensitivities.

These helpers name dual conventions without changing numerical semantics.
Call sites must convert at the boundary rather than scattering ``/ 10_000`` or
``* 100`` literals.

Frozen internal conventions:

| Factor family | Engine-facing amount | Notes |
|---|---|---|
| Equity / FX spot | relative return (``0.01`` = +1%) | cash delta / fx_delta |
| Equity / FX vol (``FactorShock`` / ``MarketSnapshot.bump``) | relative vol-level change | ``0.25`` = +25% of current vol |
| SensitivityEngine FD vega bump | **absolute** decimal vol (``0.01`` = +1 vol point) | vega quoted per vol point |
| Rates (``FactorShock`` / ``bump``) | absolute decimal rate (``0.0001`` = +1bp) | |
| Historical ``rate_moves_bps`` / approx DV01 | basis points (``1.0`` = +1 bp) | convert at boundary |
| Historical ``vol_moves`` / ``vol_pct`` | relative vol move | ``base_vol × relative × 100`` → vol points |
| UI display % | whole percent (``20`` = 20%) | convert to fraction before API |

Dual vol conventions:

- ``MarketSnapshot.bump(EquityVol|FXVol, amount)`` — *relative* vol-level change
  (``new_vol = old_vol × (1 + amount)``).
- ``SensitivityEngine`` FD vega bumps — *absolute* decimal vol points (``0.01``).
- Approximate P&L: relative ``vol_pct`` → vol points via
  :func:`relative_vol_move_to_vol_points` (needs the factor's **base vol**).
- Attribution P&L explain: absolute decimal vol difference ``v1 - v0`` via
  :func:`decimal_vol_change_to_vol_points``.
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
def decimal_vol_change_to_vol_points(delta_decimal_vol: float) -> float: ...


@overload
def decimal_vol_change_to_vol_points(
    delta_decimal_vol: NDArray[np.floating],
) -> NDArray[np.floating]: ...


def decimal_vol_change_to_vol_points(
    delta_decimal_vol: float | NDArray[np.floating],
) -> float | NDArray[np.floating]:
    """Convert an absolute decimal vol change to vega vol points (``0.01`` → ``1.0``).

    Attribution passes ``v1 - v0`` in decimal vol (0.20 → 0.22 is ``+0.02``).
    Vega is quoted per 1 vol point, so that difference is +2 vol points.
    """
    if isinstance(delta_decimal_vol, np.ndarray):
        return np.asarray(delta_decimal_vol, dtype=float) * 100.0
    return float(delta_decimal_vol) * 100.0


@overload
def relative_vol_move_to_vol_points(vol_pct: float, *, base_vol: float) -> float: ...


@overload
def relative_vol_move_to_vol_points(
    vol_pct: NDArray[np.floating], *, base_vol: float
) -> NDArray[np.floating]: ...


def relative_vol_move_to_vol_points(
    vol_pct: float | NDArray[np.floating],
    *,
    base_vol: float,
) -> float | NDArray[np.floating]:
    """Convert a relative vol-level move to vega vol points.

    ``absolute vol-point move = base_vol × relative_move × 100``.

    Example: ``base_vol=0.20``, ``relative_move=0.10`` → ``2.0`` vol points
    (FULL_REVALUATION shocked vol ``0.20 × 1.10 = 0.22``). A forgotten
    ``base_vol=0`` yields 0 vol points rather than the old ``relative × 100``
    overstatement.
    """
    return decimal_vol_change_to_vol_points(base_vol * vol_pct)
