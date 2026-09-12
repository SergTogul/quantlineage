"""Locked Wave A supported universe. Do not expand from provider search hits."""

from __future__ import annotations

from app.market.catalog.models import CatalogRecord, ProviderMapping


def _equity(*, instrument_id: str, display_name: str, symbol: str, asset_type: str) -> CatalogRecord:
    return CatalogRecord(
        instrument_id=instrument_id,
        display_name=display_name,
        asset_type=asset_type,
        currency="USD",
        geography="US",
        exchange="US",
        provider_mappings=(ProviderMapping(provider="yahoo", source_symbol=symbol),),
        supported_for_history=True,
        supported_for_snapshot=True,
        supported_for_risk_factor=True,
        risk_factor_mapping=f"EquitySpot:{symbol}",
    )


def _fred(*, series_id: str, display_name: str, tenor: str, aliases: tuple[str, ...]) -> CatalogRecord:
    return CatalogRecord(
        instrument_id=f"macro:FRED:{series_id}",
        display_name=display_name,
        asset_type="macro",
        currency="USD",
        geography="US",
        exchange=None,
        provider_mappings=(ProviderMapping(provider="fred", source_symbol=series_id),),
        supported_for_history=True,
        supported_for_snapshot=True,
        supported_for_risk_factor=True,
        risk_factor_mapping=f"RateZero:USD:{tenor}",
        search_aliases=aliases,
    )


WAVE_A_UNIVERSE: tuple[CatalogRecord, ...] = (
    _equity(
        instrument_id="equity:US:AAPL",
        display_name="Apple Inc.",
        symbol="AAPL",
        asset_type="equity",
    ),
    _equity(
        instrument_id="equity:US:MSFT",
        display_name="Microsoft Corporation",
        symbol="MSFT",
        asset_type="equity",
    ),
    _equity(
        instrument_id="equity:US:NVDA",
        display_name="NVIDIA Corporation",
        symbol="NVDA",
        asset_type="equity",
    ),
    _equity(
        instrument_id="equity:US:SPY",
        display_name="SPDR S&P 500 ETF Trust",
        symbol="SPY",
        asset_type="etf",
    ),
    _fred(
        series_id="DGS2",
        display_name="US Treasury 2-Year",
        tenor="2Y",
        aliases=("2y", "2-year", "2 year", "treasury 2"),
    ),
    _fred(
        series_id="DGS5",
        display_name="US Treasury 5-Year",
        tenor="5Y",
        aliases=("5y", "5-year", "5 year", "treasury 5"),
    ),
    _fred(
        series_id="DGS10",
        display_name="US Treasury 10-Year",
        tenor="10Y",
        aliases=("10y", "10-year", "10 year", "treasury 10"),
    ),
)
