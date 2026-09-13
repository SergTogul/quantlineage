"""Public-data quality, alignment, and content hashing. No FastAPI, no adapters."""

from app.market.ingestion.normalize import STALE_AFTER_DAYS
from app.market.quality.align import align_series
from app.market.quality.errors import (
    DuplicateDatesError,
    InsufficientAlignedHistoryError,
    InsufficientObservationsError,
    NonFiniteValueError,
    NonPositivePriceError,
    SeriesValidationError,
    UnknownUnitError,
    UnsortedDatesError,
)
from app.market.quality.hash import content_hash
from app.market.quality.models import (
    ALLOWED_UNITS,
    MIN_OBSERVATIONS,
    AlignmentResult,
    SeriesLineage,
)
from app.market.quality.validate import validate_series

__all__ = [
    "ALLOWED_UNITS",
    "MIN_OBSERVATIONS",
    "STALE_AFTER_DAYS",
    "AlignmentResult",
    "DuplicateDatesError",
    "InsufficientAlignedHistoryError",
    "InsufficientObservationsError",
    "NonFiniteValueError",
    "NonPositivePriceError",
    "SeriesLineage",
    "SeriesValidationError",
    "UnknownUnitError",
    "UnsortedDatesError",
    "align_series",
    "content_hash",
    "validate_series",
]
