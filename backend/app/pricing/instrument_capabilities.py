"""Static instrument capability registry (R0.5.1 / RF-005 leftover).

Declares, for each production ``InstrumentTerms`` / ``trade_cache_key`` family:

- pricing adapter identity as name strings only (``quantlib`` production,
  ``builtin`` reference) — this module does not import either engine;
- required typed factor kinds from :mod:`app.risk.factor_types`;
- sensitivity names already written onto ``Valuation`` today;
- snapshot maps those families read (exposure mapping).

This is a frozen lookup table, not a plugin framework. It is not wired into
``value()`` fail-closed (R0.5.2 already raises on unknown QuantLib types).
Unknown families fail closed here. Dividend yields and IR vols have no typed
factor class yet; they appear only as snapshot maps.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero

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


def _entry(
    family: str,
    *,
    required_factor_kinds: frozenset[type],
    supported_sensitivities: frozenset[str],
    snapshot_maps: frozenset[str],
) -> InstrumentCapability:
    return InstrumentCapability(
        family=family,
        pricing_adapter=ADAPTER_QUANTLIB,
        reference_adapter=ADAPTER_BUILTIN,
        required_factor_kinds=required_factor_kinds,
        supported_sensitivities=supported_sensitivities,
        snapshot_maps=snapshot_maps,
    )


_REGISTRY: dict[str, InstrumentCapability] = {
    "equity": _entry(
        "equity",
        required_factor_kinds=frozenset({EquitySpot}),
        supported_sensitivities=frozenset({"delta"}),
        snapshot_maps=frozenset({"equity_spots"}),
    ),
    "equity_future": _entry(
        "equity_future",
        required_factor_kinds=frozenset({EquitySpot, RateZero}),
        supported_sensitivities=frozenset({"delta", "dv01"}),
        snapshot_maps=frozenset({"equity_spots", "rates", "dividend_yields"}),
    ),
    "european_option": _entry(
        "european_option",
        required_factor_kinds=frozenset({EquitySpot, EquityVol, RateZero}),
        supported_sensitivities=frozenset({"delta", "gamma", "vega"}),
        snapshot_maps=frozenset(
            {"equity_spots", "equity_vols", "rates", "dividend_yields", "vol_surfaces"}
        ),
    ),
    "bond": _entry(
        "bond",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"dv01"}),
        snapshot_maps=frozenset({"rates", "key_rates", "curves"}),
    ),
    "swap": _entry(
        "swap",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"dv01"}),
        snapshot_maps=frozenset({"rates", "key_rates", "curves"}),
    ),
    "fx_forward": _entry(
        "fx_forward",
        required_factor_kinds=frozenset({FXSpot, RateZero}),
        supported_sensitivities=frozenset({"fx_delta"}),
        snapshot_maps=frozenset({"fx_spots", "rates"}),
    ),
    "fx_option": _entry(
        "fx_option",
        required_factor_kinds=frozenset({FXSpot, FXVol, RateZero}),
        supported_sensitivities=frozenset({"fx_delta", "gamma", "vega"}),
        snapshot_maps=frozenset({"fx_spots", "fx_vols", "rates", "vol_surfaces"}),
    ),
    "ir_future": _entry(
        "ir_future",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"dv01"}),
        snapshot_maps=frozenset(
            {"rates", "projection_rates", "key_rates", "curves", "ir_future_quotes"}
        ),
    ),
    "cap_floor": _entry(
        "cap_floor",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"vega", "dv01"}),
        snapshot_maps=frozenset(
            {"rates", "projection_rates", "key_rates", "curves", "ir_vols", "vol_surfaces"}
        ),
    ),
    "swaption": _entry(
        "swaption",
        required_factor_kinds=frozenset({RateZero}),
        supported_sensitivities=frozenset({"vega", "dv01"}),
        snapshot_maps=frozenset(
            {"rates", "projection_rates", "key_rates", "curves", "ir_vols", "vol_surfaces"}
        ),
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
