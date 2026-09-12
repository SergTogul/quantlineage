"""Convert public observed levels to engine-facing historical factor moves.

Equity history is a relative return. Rate snapshots are decimal levels
(G5 reuses :func:`percent_level_to_decimal`). Historical RateZero moves are
basis points via :func:`app.risk.shock_units.decimal_rate_to_bps`. Convert once.
"""

from __future__ import annotations

from app.risk.shock_units import decimal_rate_to_bps


def equity_relative_return(price_t0: float, price_t1: float) -> float:
    """Adjusted close levels → relative return (``100, 101`` → ``+0.01``)."""
    previous = float(price_t0)
    if previous == 0.0:
        raise ValueError("previous price must be non-zero")
    return float(price_t1) / previous - 1.0


def percent_level_to_decimal(percent: float) -> float:
    """FRED percent level → snapshot decimal rate (``4.25`` → ``0.0425``)."""
    return float(percent) / 100.0


def percent_level_move_to_bps(percent_t0: float, percent_t1: float) -> float:
    """Day-over-day FRED percent levels → historical bp move (``4.25→4.30`` → ``+5``)."""
    delta_decimal = percent_level_to_decimal(percent_t1) - percent_level_to_decimal(percent_t0)
    return decimal_rate_to_bps(delta_decimal)
