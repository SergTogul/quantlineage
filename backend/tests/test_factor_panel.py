"""R0.5.3 / RF-005 leftover — typed per-factor historical observation panel.

The panel is the real type. It is not wired into HistoricalRiskEngine / VaR.
Demo four-macro history stays `projection="four_macro_demo"`. Do not close RF-005.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.risk.factor_panel import (
    EQUITY_CHANGE_UNIT,
    PER_FACTOR_PANEL_PROJECTION,
    RATE_CHANGE_UNIT,
    FactorPanelObservation,
    HistoricalFactorPanel,
    change_unit,
)
from app.risk.factor_types import EquitySpot, RateZero

AAA = EquitySpot("AAA")
BBB = EquitySpot("BBB")
USD_2Y = RateZero("USD", "2Y")
USD_10Y = RateZero("USD", "10Y")
AS_OF = date(2024, 1, 2)


def _two_equity_two_tenor(*, aaa: float, bbb: float, usd2y: float, usd10y: float) -> HistoricalFactorPanel:
    return HistoricalFactorPanel.from_pairs(
        dates=[AS_OF],
        rows=[
            [
                (AAA, aaa),
                (BBB, bbb),
                (USD_2Y, usd2y),
                (USD_10Y, usd10y),
            ]
        ],
    )


def test_two_equities_and_two_tenors_are_independently_readable():
    """Exit criterion: four typed moves in one observation, independently addressable."""
    panel = _two_equity_two_tenor(aaa=0.01, bbb=-0.02, usd2y=1.5, usd10y=-3.0)

    assert panel.change(AS_OF, AAA) == 0.01
    assert panel.change(AS_OF, BBB) == -0.02
    assert panel.change(AS_OF, USD_2Y) == 1.5
    assert panel.change(AS_OF, USD_10Y) == -3.0

    obs = panel.observation_on(AS_OF)
    assert obs.change(AAA) == 0.01
    assert obs.change(BBB) == -0.02
    assert obs.change(USD_2Y) == 1.5
    assert obs.change(USD_10Y) == -3.0


def test_changing_one_factor_leaves_the_other_three_unchanged():
    base = _two_equity_two_tenor(aaa=0.01, bbb=-0.02, usd2y=1.5, usd10y=-3.0)

    equity_moved = _two_equity_two_tenor(aaa=0.07, bbb=-0.02, usd2y=1.5, usd10y=-3.0)
    assert equity_moved.change(AS_OF, AAA) == 0.07
    assert equity_moved.change(AS_OF, BBB) == base.change(AS_OF, BBB)
    assert equity_moved.change(AS_OF, USD_2Y) == base.change(AS_OF, USD_2Y)
    assert equity_moved.change(AS_OF, USD_10Y) == base.change(AS_OF, USD_10Y)

    tenor_moved = _two_equity_two_tenor(aaa=0.01, bbb=-0.02, usd2y=1.5, usd10y=12.0)
    assert tenor_moved.change(AS_OF, USD_10Y) == 12.0
    assert tenor_moved.change(AS_OF, USD_2Y) == base.change(AS_OF, USD_2Y)
    assert tenor_moved.change(AS_OF, AAA) == base.change(AS_OF, AAA)
    assert tenor_moved.change(AS_OF, BBB) == base.change(AS_OF, BBB)


def test_same_currency_tenors_are_distinct_despite_shared_rate_key():
    """RateZero.key is currency-only (USD:RATE); the panel keys on the typed factor."""
    assert USD_2Y.key == USD_10Y.key == "USD:RATE"
    obs = FactorPanelObservation.from_pairs(
        AS_OF,
        [(USD_2Y, 1.0), (USD_10Y, 5.0)],
    )
    assert obs.change(USD_2Y) == 1.0
    assert obs.change(USD_10Y) == 5.0


def test_panel_is_per_name_per_tenor_not_four_macro_demo():
    panel = _two_equity_two_tenor(aaa=0.01, bbb=-0.02, usd2y=1.5, usd10y=-3.0)
    assert panel.is_per_name_per_tenor_panel is True
    assert panel.projection == PER_FACTOR_PANEL_PROJECTION
    assert panel.projection != "four_macro_demo"
    assert PER_FACTOR_PANEL_PROJECTION != "four_macro_demo"


def test_units_match_historical_data_conventions():
    """Equity relative returns; rate moves in basis points (historical_data.py)."""
    assert EQUITY_CHANGE_UNIT == "relative_return"
    assert RATE_CHANGE_UNIT == "basis_points"
    assert change_unit(AAA) == EQUITY_CHANGE_UNIT
    assert change_unit(USD_2Y) == RATE_CHANGE_UNIT
    assert change_unit(USD_10Y) == RATE_CHANGE_UNIT


def test_duplicate_equity_in_one_row_fails_closed():
    with pytest.raises(ValueError, match="duplicate"):
        FactorPanelObservation.from_pairs(
            AS_OF,
            [(AAA, 0.01), (AAA, 0.02)],
        )


def test_duplicate_rate_tenor_in_one_row_fails_closed():
    with pytest.raises(ValueError, match="duplicate"):
        FactorPanelObservation.from_pairs(
            AS_OF,
            [(USD_2Y, 1.0), (RateZero("USD", "2Y"), 2.0)],
        )


def test_empty_observation_fails_closed():
    with pytest.raises(ValueError, match="empty"):
        FactorPanelObservation.from_pairs(AS_OF, [])


def test_empty_panel_fails_closed():
    with pytest.raises(ValueError, match="empty"):
        HistoricalFactorPanel.from_pairs(dates=[], rows=[])


def test_mismatched_date_and_row_counts_fail_closed():
    with pytest.raises(ValueError, match="length"):
        HistoricalFactorPanel.from_pairs(
            dates=[AS_OF, date(2024, 1, 3)],
            rows=[[(AAA, 0.01)]],
        )


def test_mismatched_row_widths_fail_closed():
    with pytest.raises(ValueError, match="length"):
        HistoricalFactorPanel.from_pairs(
            dates=[AS_OF, date(2024, 1, 3)],
            rows=[
                [(AAA, 0.01), (BBB, -0.02)],
                [(AAA, 0.03)],
            ],
        )


def test_mismatched_column_series_lengths_fail_closed():
    with pytest.raises(ValueError, match="length"):
        HistoricalFactorPanel.from_columns(
            dates=[AS_OF, date(2024, 1, 3)],
            changes={
                AAA: [0.01],
                BBB: [0.02, 0.03],
            },
        )
