"""Static instrument capability registry (R0.5.1 / RF-005 leftover).

Declares, for each production ``InstrumentTerms`` / ``trade_cache_key`` family:

- pricing adapter identity as name strings only (``quantlib`` production,
  ``builtin`` reference) — this module does not import either engine;
- required typed factor kinds from :mod:`app.risk.factor_types`;
- sensitivity names already written onto ``Valuation`` today;
- snapshot maps those families read (exposure mapping).

This is a frozen lookup table, not a plugin framework. Production pricing,
snapshot overlay, cache identity, and typed factor extraction call
:func:`get_capability` so unknown families fail closed. Trade-cache schema
ids live on each row. Named typed factors for panel / ``calculate_typed``
come from :func:`named_risk_factors`. Builtin/QuantLib ``value()`` and the
shared overlay dispatch by ``terms.type`` handler maps after
:func:`get_capability`. This is not a plugin registry.
Dividend yields and IR vols have no typed factor class yet; they appear
only as snapshot maps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from app.risk.factor_types import (
    EquitySpot,
    EquityVol,
    FXSpot,
    FXVol,
    RateZero,
    RiskFactor,
)

ADAPTER_QUANTLIB = "quantlib"
ADAPTER_BUILTIN = "builtin"

PRODUCTION_FAMILIES: tuple[str, ...] = (
    "equity",
    "equity_future",
    "european_option",
    "bond",
    "swap",
    "fx_forward",
    "fx_option",
    "ir_future",
    "cap_floor",
    "swaption",
)


@dataclass(frozen=True, slots=True)
class InstrumentCapability:
    """Declared capabilities for one production instrument family."""

    family: str
    pricing_adapter: str
    reference_adapter: str
    required_factor_kinds: frozenset[type]
    supported_sensitivities: frozenset[str]
    snapshot_maps: frozenset[str]
    trade_cache_schema: str


def _entry(
    family: str,
    *,
    required_factor_kinds: frozenset[type],
    supported_sensitivities: frozenset[str],
    snapshot_maps: frozenset[str],
    trade_cache_schema: str,
) -> InstrumentCapability:
    return InstrumentCapability(
        family=family,
        pricing_adapter=ADAPTER_QUANTLIB,
        reference_adapter=ADAPTER_BUILTIN,
        required_factor_kinds=required_factor_kinds,
        supported_sensitivities=supported_sensitivities,
        snapshot_maps=snapshot_maps,
        trade_cache_schema=trade_cache_schema,
    )


_REGISTRY: dict[str, InstrumentCapability] = {
    "equity": _entry(
        "equity",
        required_factor_kinds=frozenset({EquitySpot}),
        supported_sensitivities=frozenset({"delta"}),
        snapshot_maps=frozenset({"equity_spots"}),
        trade_cache_schema="equity_terms_v1",
    ),
    "equity_future": _entry(
        "equity_future",
        required_factor_kinds=frozenset({EquitySpot, RateZero}),
        supported_sensitivities=frozenset({"delta", "dv01"}),
        snapshot_maps=frozenset({"equity_spots", "rates", "dividend_yields"}),
        trade_cache_schema="equity_future_terms_v1",
    ),
    "european_option": _entry(
        "european_option",
        required_factor_kinds=frozenset({EquitySpot, EquityVol, RateZero}),
        supported_sensitivities=frozenset({"delta", "gamma", "vega"}),
        snapshot_maps=frozenset(
            {"equity_spots", "equity_vols", "rates", "dividend_yields", "vol_surfaces"}
        ),
        trade_cache_schema="equity_option_terms_v1",
    ),
    "bond": _entry(
        "bond",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"dv01"}),
        snapshot_maps=frozenset({"rates", "key_rates", "curves"}),
        trade_cache_schema="bond_terms_v1",
    ),
    "swap": _entry(
        "swap",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"dv01"}),
        snapshot_maps=frozenset({"rates", "key_rates", "curves"}),
        trade_cache_schema="swap_terms_v1",
    ),
    "fx_forward": _entry(
        "fx_forward",
        required_factor_kinds=frozenset({FXSpot, RateZero}),
        supported_sensitivities=frozenset({"fx_delta"}),
        snapshot_maps=frozenset({"fx_spots", "rates"}),
        trade_cache_schema="fx_forward_terms_v1",
    ),
    "fx_option": _entry(
        "fx_option",
        required_factor_kinds=frozenset({FXSpot, FXVol, RateZero}),
        supported_sensitivities=frozenset({"fx_delta", "gamma", "vega"}),
        snapshot_maps=frozenset({"fx_spots", "fx_vols", "rates", "vol_surfaces"}),
        trade_cache_schema="fx_option_terms_v1",
    ),
    "ir_future": _entry(
        "ir_future",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"dv01"}),
        snapshot_maps=frozenset(
            {"rates", "projection_rates", "key_rates", "curves", "ir_future_quotes"}
        ),
        trade_cache_schema="ir_future_terms_v1",
    ),
    "cap_floor": _entry(
        "cap_floor",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"vega", "dv01"}),
        snapshot_maps=frozenset(
            {"rates", "projection_rates", "key_rates", "curves", "ir_vols", "vol_surfaces"}
        ),
        trade_cache_schema="cap_floor_terms_v1",
    ),
    "swaption": _entry(
        "swaption",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"vega", "dv01"}),
        snapshot_maps=frozenset(
            {"rates", "projection_rates", "key_rates", "curves", "ir_vols", "vol_surfaces"}
        ),
        trade_cache_schema="swaption_terms_v1",
    ),
}


def get_capability(family: str) -> InstrumentCapability:
    """Return the static capability row for a production family.

    Unknown families fail closed. ``family`` must be the InstrumentTerms
    ``type`` / trade-cache family id (e.g. ``european_option``).
    """
    if not isinstance(family, str):
        raise TypeError(f"unknown instrument family: {type(family).__name__}")
    try:
        return _REGISTRY[family]
    except KeyError:
        raise KeyError(f"unknown instrument family: {family!r}") from None


def _rate_tenor_years(position: object) -> float:
    years = getattr(position, "maturity_years", None)
    if years is None:
        years = getattr(position, "option_maturity_years", None)
    if years is None:
        raise TypeError(
            f"cannot name RateZero tenor for family {getattr(position, 'type', None)!r}"
        )
    return float(years)


def named_risk_factors(position: object) -> tuple[RiskFactor, ...]:
    """Instantiate declared typed factors from position fields (fail-closed).

    Identity matches ``RiskFactorEngine.calculate_typed``: per-name equity/FX
    and per-tenor rates via ``round(maturity_years)Y`` (swaption uses
    ``option_maturity_years``). Vol kinds are included when declared.

    ``RateZero`` is named when declared and ``dv01`` is supported, except when
    an equity/FX spot kind is also declared — those families keep spot/vol
    identity and treat funding rates as snapshot maps only (no IRVol type;
    IR option vega stays on ``Valuation``).
    """
    cap = get_capability(getattr(position, "type", None))
    kinds = cap.required_factor_kinds
    factors: list[RiskFactor] = []
    p = cast(Any, position)
    if EquitySpot in kinds:
        factors.append(EquitySpot(p.symbol))
    if EquityVol in kinds:
        factors.append(EquityVol(underlying=p.symbol))
    if FXSpot in kinds:
        factors.append(FXSpot(p.pair))
    if FXVol in kinds:
        factors.append(FXVol(pair=p.pair))
    if (
        RateZero in kinds
        and "dv01" in cap.supported_sensitivities
        and EquitySpot not in kinds
        and FXSpot not in kinds
    ):
        tenor = f"{round(_rate_tenor_years(position))}Y"
        factors.append(RateZero(currency=p.currency, tenor=tenor))
    if not factors:
        raise TypeError(
            f"capability {cap.family!r} declares no named typed risk factors"
        )
    return tuple(factors)
