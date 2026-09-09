"""Static instrument capability registry (R0.5.1 / RF-012 wire).

Declares adapter identity, required factor kinds, produced sensitivities,
and snapshot-map exposure for each production family. Production pricing,
snapshot overlay, cache identity, and typed factor extraction consult
``get_capability`` so unknown families fail closed. Does not import
pricing engines.
"""

from __future__ import annotations

import pytest

from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero

PRODUCTION_FAMILY_TYPES = (
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


# Pinned from current Builtin / QuantLib Valuation fields and snapshot reads.
# No IRVol / DividendYield types exist in factor_types; those live in maps.
_FAMILY_SPEC: dict[str, dict[str, frozenset]] = {
    "equity": {
        "factors": frozenset({EquitySpot}),
        "sens": frozenset({"delta"}),
        "maps": frozenset({"equity_spots"}),
    },
    "equity_future": {
        "factors": frozenset({EquitySpot, RateZero}),
        "sens": frozenset({"delta", "dv01"}),
        "maps": frozenset({"equity_spots", "rates", "dividend_yields"}),
    },
    "european_option": {
        "factors": frozenset({EquitySpot, EquityVol, RateZero}),
        "sens": frozenset({"delta", "gamma", "vega"}),
        "maps": frozenset({"equity_spots", "equity_vols", "rates", "dividend_yields"}),
    },
    "bond": {
        "factors": frozenset({RateZero}),
        "sens": frozenset({"dv01"}),
        "maps": frozenset({"rates"}),
    },
    "swap": {
        "factors": frozenset({RateZero}),
        "sens": frozenset({"dv01"}),
        "maps": frozenset({"rates"}),
    },
    "fx_forward": {
        "factors": frozenset({FXSpot, RateZero}),
        "sens": frozenset({"fx_delta"}),
        "maps": frozenset({"fx_spots", "rates"}),
    },
    "fx_option": {
        "factors": frozenset({FXSpot, FXVol, RateZero}),
        "sens": frozenset({"fx_delta", "gamma", "vega"}),
        "maps": frozenset({"fx_spots", "fx_vols", "rates"}),
    },
    "ir_future": {
        "factors": frozenset({RateZero}),
        "sens": frozenset({"dv01"}),
        "maps": frozenset({"rates", "projection_rates", "ir_future_quotes"}),
    },
    "cap_floor": {
        "factors": frozenset({RateZero}),
        "sens": frozenset({"vega", "dv01"}),
        "maps": frozenset({"rates", "projection_rates", "ir_vols"}),
    },
    "swaption": {
        "factors": frozenset({RateZero}),
        "sens": frozenset({"vega", "dv01"}),
        "maps": frozenset({"rates", "projection_rates", "ir_vols"}),
    },
}


def test_all_ten_production_families_are_registered():
    from app.pricing.instrument_capabilities import PRODUCTION_FAMILIES, get_capability

    assert tuple(PRODUCTION_FAMILIES) == PRODUCTION_FAMILY_TYPES
    assert set(_FAMILY_SPEC) == set(PRODUCTION_FAMILY_TYPES)
    for family in PRODUCTION_FAMILY_TYPES:
        cap = get_capability(family)
        spec = _FAMILY_SPEC[family]
        assert cap.family == family
        assert cap.pricing_adapter in {"quantlib", "builtin"}
        assert cap.reference_adapter in {"quantlib", "builtin"}
        assert isinstance(cap.pricing_adapter, str)
        assert isinstance(cap.reference_adapter, str)
        assert spec["factors"] <= cap.required_factor_kinds
        assert cap.supported_sensitivities == spec["sens"]
        assert spec["maps"] <= cap.snapshot_maps


def test_european_option_requires_spot_vol_rates_and_dividends():
    from app.pricing.instrument_capabilities import get_capability

    cap = get_capability("european_option")
    assert EquitySpot in cap.required_factor_kinds
    assert EquityVol in cap.required_factor_kinds
    assert RateZero in cap.required_factor_kinds
    assert "equity_spots" in cap.snapshot_maps
    assert "equity_vols" in cap.snapshot_maps
    assert "rates" in cap.snapshot_maps
    assert "dividend_yields" in cap.snapshot_maps
    assert cap.supported_sensitivities == frozenset({"delta", "gamma", "vega"})


def test_bond_requires_rates():
    from app.pricing.instrument_capabilities import get_capability

    cap = get_capability("bond")
    assert RateZero in cap.required_factor_kinds
    assert "rates" in cap.snapshot_maps
    assert cap.supported_sensitivities == frozenset({"dv01"})


def test_fx_option_requires_fx_spot_vol_and_domestic_foreign_rates():
    from app.pricing.instrument_capabilities import get_capability

    cap = get_capability("fx_option")
    assert FXSpot in cap.required_factor_kinds
    assert FXVol in cap.required_factor_kinds
    assert RateZero in cap.required_factor_kinds
    assert "fx_spots" in cap.snapshot_maps
    assert "fx_vols" in cap.snapshot_maps
    assert "rates" in cap.snapshot_maps
    assert cap.supported_sensitivities == frozenset({"fx_delta", "gamma", "vega"})


def test_unknown_family_raises():
    from app.pricing.instrument_capabilities import get_capability

    with pytest.raises((KeyError, TypeError), match="unknown instrument family"):
        get_capability("convertible_bond")
    with pytest.raises((KeyError, TypeError)):
        get_capability(object())  # type: ignore[arg-type]


def test_registry_does_not_import_pricing_engines():
    import app.pricing.instrument_capabilities as mod

    assert not hasattr(mod, "BuiltinPricingEngine")
    assert not hasattr(mod, "QuantLibPricingEngine")
    assert "app.pricing.builtin" not in __import__("sys").modules or (
        "BuiltinPricingEngine" not in getattr(mod, "__dict__", {})
    )
    source = __import__("inspect").getsource(mod)
    assert "BuiltinPricingEngine" not in source
    assert "QuantLibPricingEngine" not in source
    assert "from app.pricing.builtin" not in source
    assert "from app.pricing.quantlib" not in source
    assert "import quantlib" not in source.lower()


class _UnknownTerms:
    type = "convertible_bond"
    id = "mystery"


class _UnknownPosition:
    id = "mystery"
    type = "convertible_bond"


def _empty_market():
    from app.domain.models import MarketSnapshot

    return MarketSnapshot(id="m", as_of="t0", equity_spots={}, rates={})


def test_builtin_value_consults_get_capability(monkeypatch):
    from app.domain.models import EquityPosition, MarketSnapshot
    from app.pricing.builtin import BuiltinPricingEngine

    monkeypatch.setattr(
        "app.pricing.builtin.get_capability",
        lambda family: (_ for _ in ()).throw(AssertionError(f"wired:{family}")),
        raising=False,
    )
    position = EquityPosition(type="equity", id="e", symbol="ABC", quantity=1)
    market = MarketSnapshot(id="m", equity_spots={"ABC": 10.0}, rates={"USD": 0.04})
    with pytest.raises(AssertionError, match="wired:equity"):
        BuiltinPricingEngine().value(position, market)


def test_builtin_snapshot_overlay_unknown_family_fails_closed():
    from app.pricing.builtin import _snapshot_marks_from_terms

    with pytest.raises((KeyError, TypeError), match="unknown instrument family"):
        _snapshot_marks_from_terms(_UnknownTerms(), _empty_market())  # type: ignore[arg-type]


def test_factor_extraction_unknown_family_fails_closed():
    from types import SimpleNamespace

    from app.domain.models import Valuation
    from app.risk.factors import RiskFactorEngine

    class _StubPricing:
        def value(self, position, market=None):
            return Valuation(position_id=position.id, market_value=1.0)

    book = SimpleNamespace(positions=[_UnknownPosition()])
    with pytest.raises((KeyError, TypeError), match="unknown instrument family"):
        RiskFactorEngine().calculate_typed(book, _StubPricing(), _empty_market())  # type: ignore[arg-type]


def test_trade_cache_key_consults_get_capability(monkeypatch):
    from app.domain.models import EquityPosition
    from app.pricing.cache import trade_cache_key

    monkeypatch.setattr(
        "app.pricing.cache.get_capability",
        lambda family: (_ for _ in ()).throw(AssertionError(f"wired:{family}")),
        raising=False,
    )
    position = EquityPosition(type="equity", id="e", symbol="ABC", quantity=1)
    with pytest.raises(AssertionError, match="wired:equity"):
        trade_cache_key(position)
