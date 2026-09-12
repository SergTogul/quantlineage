"""Typed fail-closed errors for series validation and alignment."""

from __future__ import annotations


class SeriesValidationError(Exception):
    """Base quality-library failure. ``code`` is the stable taxonomy token."""

    code = "invalid_series"

    def __init__(self, message: str = "") -> None:
        super().__init__(message)


class UnsortedDatesError(SeriesValidationError):
    code = "unsorted_dates"


class DuplicateDatesError(SeriesValidationError):
    code = "duplicate_dates"


class NonFiniteValueError(SeriesValidationError):
    code = "non_finite_value"


class NonPositivePriceError(SeriesValidationError):
    code = "non_positive_price"


class UnknownUnitError(SeriesValidationError):
    code = "unknown_unit"


class InsufficientObservationsError(SeriesValidationError):
    code = "insufficient_observations"


class InsufficientAlignedHistoryError(SeriesValidationError):
    code = "insufficient_aligned_history"
