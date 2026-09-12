"""Public-data ingestion models and protocols. Adapters are imported explicitly."""

from app.market.ingestion.errors import (
    AuthorizationError,
    InsufficientHistoryError,
    MalformedResponseError,
    NotFoundError,
    ProviderError,
    RateLimitedError,
    UnavailableError,
)
from app.market.ingestion.models import (
    NORMALIZATION_VERSION,
    DataQualitySummary,
    DataSourceMetadata,
    Frequency,
    HistoricalPoint,
    HistoricalSeries,
    InstrumentCandidate,
    InstrumentRef,
    MacroSeriesRef,
)
from app.market.ingestion.protocols import (
    HistoricalDataProvider,
    InstrumentSearchProvider,
    MacroDataProvider,
)

__all__ = [
    "NORMALIZATION_VERSION",
    "AuthorizationError",
    "DataQualitySummary",
    "DataSourceMetadata",
    "Frequency",
    "HistoricalDataProvider",
    "HistoricalPoint",
    "HistoricalSeries",
    "InstrumentCandidate",
    "InstrumentRef",
    "InstrumentSearchProvider",
    "InsufficientHistoryError",
    "MacroDataProvider",
    "MacroSeriesRef",
    "MalformedResponseError",
    "NotFoundError",
    "ProviderError",
    "RateLimitedError",
    "UnavailableError",
]
