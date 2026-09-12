"""Wave A public-history dataset identity, factor mappings, and freeze config."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.market.ingestion.models import NORMALIZATION_VERSION, Frequency
from app.market.quality.models import MIN_OBSERVATIONS

WAVE_A_DATASET_ID = "real:public:wave-a"
WAVE_A_DATASET_NAME = "wave-a"
WAVE_A_MIN_ALIGNED_RETURNS = MIN_OBSERVATIONS
WAVE_A_NORMALIZATION_VERSION = NORMALIZATION_VERSION
WAVE_A_ALIGNMENT = "intersection"
WAVE_A_PROVIDER_SOURCE = "yahoo+fred"

WAVE_A_TRANSFORM_CONFIG: dict[str, str] = {
    "equity": "relative_return",
    "equity_formula": "p_t / p_{t-1} - 1",
    "rate_snapshot": "percent_to_decimal",
    "rate_historical_move": "decimal_rate_to_bps(d1-d0)",
}


@dataclass(frozen=True, slots=True)
class FactorMapping:
    instrument_id: str
    factor_column: str
    provider: str
    source_symbol: str
    asset_type: str
    unit: str
    kind: str


@dataclass(frozen=True, slots=True)
class PublicHistoryDatasetSpec:
    dataset_name: str
    dataset_id: str
    start: date
    end: date
    frequency: Frequency
    alignment: str
    min_aligned_returns: int
    normalization_version: str
    factor_mappings: tuple[FactorMapping, ...]
    provider_source: str


WAVE_A_FACTOR_MAPPINGS: tuple[FactorMapping, ...] = (
    FactorMapping(
        instrument_id="equity:US:AAPL",
        factor_column="EquitySpot:AAPL",
        provider="yahoo",
        source_symbol="AAPL",
        asset_type="equity",
        unit="price",
        kind="equity",
    ),
    FactorMapping(
        instrument_id="equity:US:MSFT",
        factor_column="EquitySpot:MSFT",
        provider="yahoo",
        source_symbol="MSFT",
        asset_type="equity",
        unit="price",
        kind="equity",
    ),
    FactorMapping(
        instrument_id="equity:US:NVDA",
        factor_column="EquitySpot:NVDA",
        provider="yahoo",
        source_symbol="NVDA",
        asset_type="equity",
        unit="price",
        kind="equity",
    ),
    FactorMapping(
        instrument_id="equity:US:SPY",
        factor_column="EquitySpot:SPY",
        provider="yahoo",
        source_symbol="SPY",
        asset_type="etf",
        unit="price",
        kind="equity",
    ),
    FactorMapping(
        instrument_id="macro:FRED:DGS2",
        factor_column="RateZero:USD:2Y",
        provider="fred",
        source_symbol="DGS2",
        asset_type="macro",
        unit="percent",
        kind="rate",
    ),
    FactorMapping(
        instrument_id="macro:FRED:DGS5",
        factor_column="RateZero:USD:5Y",
        provider="fred",
        source_symbol="DGS5",
        asset_type="macro",
        unit="percent",
        kind="rate",
    ),
    FactorMapping(
        instrument_id="macro:FRED:DGS10",
        factor_column="RateZero:USD:10Y",
        provider="fred",
        source_symbol="DGS10",
        asset_type="macro",
        unit="percent",
        kind="rate",
    ),
)


WAVE_A_SPEC = PublicHistoryDatasetSpec(
    dataset_name=WAVE_A_DATASET_NAME,
    dataset_id=WAVE_A_DATASET_ID,
    start=date(2020, 1, 2),
    end=date(2024, 12, 31),
    frequency=Frequency.DAILY,
    alignment=WAVE_A_ALIGNMENT,
    min_aligned_returns=WAVE_A_MIN_ALIGNED_RETURNS,
    normalization_version=WAVE_A_NORMALIZATION_VERSION,
    factor_mappings=WAVE_A_FACTOR_MAPPINGS,
    provider_source=WAVE_A_PROVIDER_SOURCE,
)
