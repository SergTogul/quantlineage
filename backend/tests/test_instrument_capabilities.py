"""Static instrument capability registry (R0.5.1 / RF-012 remaining ladders).

Declares adapter identity, required factor kinds, produced sensitivities,
snapshot-map exposure, and trade-cache schema ids for each production family.
Production pricing, snapshot overlay, cache identity, and typed factor
extraction consult ``get_capability`` / ``named_risk_factors`` so unknown
families fail closed. Does not import pricing engines.
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


# --- R0.5.7 remaining ladders (RF-012) ---

_TRADE_CACHE_SCHEMA_IDS = {
    "equity": "equity_terms_v1",
    "equity_future": "equity_future_terms_v1",
    "european_option": "equity_option_terms_v1",
    "bond": "bond_terms_v1",
    "swap": "swap_terms_v1",
    "fx_forward": "fx_forward_terms_v1",
    "fx_option": "fx_option_terms_v1",
    "ir_future": "ir_future_terms_v1",
    "cap_floor": "cap_floor_terms_v1",
    "swaption": "swaption_terms_v1",
}


class _AllGreeksPricing:
    def value(self, position, market=None):
        from app.domain.models import Valuation

        return Valuation(
            position_id=position.id,
            market_value=1.0,
            delta=1.0,
            gamma=1.0,
            vega=3.0,
            dv01=12.5,
            fx_delta=1.0,
        )


def _position_for_family(family: str):
    from app.domain.models import (
        BondPosition,
        CapFloorPosition,
        EquityFuturePosition,
        EquityPosition,
        EuropeanOptionPosition,
        FXForwardPosition,
        FXOptionPosition,
        InterestRateFuturePosition,
        SwapPosition,
        SwaptionPosition,
    )

    factories = {
        "equity": lambda: EquityPosition(type="equity", id="e", symbol="SPY", quantity=1),
        "equity_future": lambda: EquityFuturePosition(
            type="equity_future", id="f", symbol="SPY", quantity=1, maturity_years=0.25
        ),
        "european_option": lambda: EuropeanOptionPosition(
            type="european_option",
            id="o",
            symbol="SPY",
            quantity=1,
            strike=100.0,
            maturity_years=0.5,
            option_type="call",
        ),
        "bond": lambda: BondPosition(
            type="bond",
            id="b",
            issuer="UST",
            face_value=100.0,
            quantity=1,
            maturity_years=10.0,
            duration=8.0,
        ),
        "swap": lambda: SwapPosition(
            type="swap",
            id="s",
            currency="USD",
            notional=1_000_000.0,
            maturity_years=5.0,
            fixed_rate=0.04,
            duration=4.0,
        ),
        "fx_forward": lambda: FXForwardPosition(
            type="fx_forward",
            id="xf",
            pair="EURUSD",
            notional_base=1.0,
            strike=1.1,
            maturity_years=0.5,
        ),
        "fx_option": lambda: FXOptionPosition(
            type="fx_option",
            id="xo",
            pair="EURUSD",
            notional_base=1.0,
            strike=1.1,
            maturity_years=0.5,
            option_type="call",
        ),
        "ir_future": lambda: InterestRateFuturePosition(
            type="ir_future", id="ir", currency="USD", quantity=1, maturity_years=0.25
        ),
        "cap_floor": lambda: CapFloorPosition(
            type="cap_floor",
            id="c",
            currency="USD",
            notional=1_000_000.0,
            strike=0.03,
            maturity_years=2.0,
            option_type="cap",
        ),
        "swaption": lambda: SwaptionPosition(
            type="swaption",
            id="w",
            currency="USD",
            notional=1_000_000.0,
            strike=0.03,
            option_maturity_years=1.0,
            swap_tenor_years=5.0,
            option_type="payer",
        ),
    }
    return factories[family]()


def test_trade_cache_schema_lives_on_capability_registry():
    import inspect

    from app.pricing import cache as cache_mod
    from app.pricing.instrument_capabilities import get_capability

    for family, schema in _TRADE_CACHE_SCHEMA_IDS.items():
        assert get_capability(family).trade_cache_schema == schema
    source = inspect.getsource(cache_mod)
    assert "_TRADE_CACHE_SCHEMAS" not in source


def test_calculate_typed_includes_cap_floor_rate_zero():
    from app.domain.models import Portfolio
    from app.risk.factor_types import RateZero
    from app.risk.factors import RiskFactorEngine

    book = Portfolio(id="p", name="p", positions=[_position_for_family("cap_floor")])
    typed = RiskFactorEngine().calculate_typed(book, _AllGreeksPricing(), _empty_market())
    by_factor = dict(typed)
    assert RateZero("USD", "2Y") in by_factor
    assert by_factor[RateZero("USD", "2Y")] == pytest.approx(12.5)
    assert by_factor[RateZero("USD", "2Y")] != pytest.approx(15.5)


def test_calculate_typed_includes_swaption_rate_zero():
    from app.domain.models import Portfolio
    from app.risk.factor_types import RateZero
    from app.risk.factors import RiskFactorEngine

    book = Portfolio(id="p", name="p", positions=[_position_for_family("swaption")])
    typed = RiskFactorEngine().calculate_typed(book, _AllGreeksPricing(), _empty_market())
    by_factor = dict(typed)
    assert RateZero("USD", "1Y") in by_factor
    assert by_factor[RateZero("USD", "1Y")] == pytest.approx(12.5)


@pytest.mark.parametrize("family", PRODUCTION_FAMILY_TYPES)
def test_calculate_typed_extracts_every_production_family(family):
    from app.domain.models import Portfolio
    from app.risk.factors import RiskFactorEngine

    book = Portfolio(id="p", name="p", positions=[_position_for_family(family)])
    typed = RiskFactorEngine().calculate_typed(book, _AllGreeksPricing(), _empty_market())
    assert typed, f"{family} was skipped after get_capability"


def test_required_factors_for_position_maps_cap_floor_and_swaption():
    from app.risk.factor_types import RateZero
    from app.risk.historical import required_factors_for_position

    assert required_factors_for_position(_position_for_family("cap_floor")) == (
        RateZero("USD", "2Y"),
    )
    assert required_factors_for_position(_position_for_family("swaption")) == (
        RateZero("USD", "1Y"),
    )


def test_required_factors_unknown_family_fails_closed():
    from app.risk.historical import required_factors_for_position

    with pytest.raises((KeyError, TypeError), match="unknown instrument family"):
        required_factors_for_position(_UnknownPosition())  # type: ignore[arg-type]


def test_required_factors_driven_from_registry_not_isinstance_ladder():
    import inspect

    from app.risk import historical as historical_mod

    source = inspect.getsource(historical_mod.required_factors_for_position)
    assert "get_capability" in source or "named_risk_factors" in source
    assert "isinstance" not in source


def test_builtin_ir_option_calculate_typed_matches_valuation_dv01():
    from app.domain.models import CapFloorPosition, MarketSnapshot, Portfolio
    from app.pricing.builtin import BuiltinPricingEngine
    from app.risk.factor_types import RateZero
    from app.risk.factors import RiskFactorEngine

    cap = CapFloorPosition(
        type="cap_floor",
        id="usd-cap",
        currency="USD",
        notional=1_000_000.0,
        strike=0.04,
        maturity_years=2.0,
        option_type="cap",
    )
    market = MarketSnapshot(
        id="ir-opt",
        rates={"USD": 0.035},
        projection_rates={"USD": 0.04},
        ir_vols={"USD": 0.20},
    )
    pricing = BuiltinPricingEngine()
    valuation = pricing.value(cap, market)
    typed = dict(
        RiskFactorEngine().calculate_typed(
            Portfolio(id="p", name="p", positions=[cap]), pricing, market
        )
    )
    assert valuation.vega != 0.0
    assert typed[RateZero("USD", "2Y")] == pytest.approx(valuation.dv01)
