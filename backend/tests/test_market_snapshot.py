"""M1.3 market-data domain: immutability, bump/apply/diff, content identity."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.domain.models import MarketSnapshot, StressScenario
from app.market.curves import attach_standard_usd_curves
from app.market.snapshot import shock_snapshot
from app.market.vol_surfaces import (
    attach_vol_surface,
    build_equity_vol_surface,
    build_fx_vol_surface,
)
from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero


def test_market_snapshot_is_frozen():
    snap = MarketSnapshot(equity_spots={"SPY": 100.0}, rates={"USD": 0.04})
    with pytest.raises(Exception):
        snap.equity_spots["SPY"] = 101.0  # type: ignore[index]


def test_nested_curves_and_vol_surfaces_are_deep_frozen():
    base = MarketSnapshot(rates={"USD": 0.04})
    with_curves = attach_standard_usd_curves(base)
    with_vol = attach_vol_surface(with_curves, build_equity_vol_surface("SPY", 0.20))

    with pytest.raises(TypeError):
        with_vol.curves["USD_OIS"]["zeros"]["10Y"] = 0.99  # type: ignore[index]
    with pytest.raises(TypeError):
        with_vol.curves["USD_OIS"]["zeros"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        with_vol.vol_surfaces["SPY"]["grid"]["1Y|1"] = 0.99  # type: ignore[index]
    with pytest.raises(TypeError):
        with_vol.key_rates["USD"]["10Y"] = 0.99  # type: ignore[index]

    # Mutations must not stick even if TypeError were swallowed.
    assert with_vol.curves["USD_OIS"]["zeros"]["10Y"] == pytest.approx(0.04)
    assert with_vol.vol_surfaces["SPY"]["grid"]["1Y|1"] == pytest.approx(0.20)
    assert with_vol.key_rates["USD"]["10Y"] == pytest.approx(0.04)


def test_bump_equity_spot_is_relative_and_returns_new_snapshot():
    base = MarketSnapshot(id="base", equity_spots={"SPY": 100.0, "NVDA": 50.0}, rates={"USD": 0.04})
    bumped = base.bump(EquitySpot("SPY"), 0.10)
    assert bumped is not base
    assert bumped.equity_spots["SPY"] == pytest.approx(110.0)
    assert bumped.equity_spots["NVDA"] == 50.0
    assert base.equity_spots["SPY"] == 100.0


def test_bump_rate_parallel_shifts_scalar_and_pillars():
    base = attach_standard_usd_curves(
        MarketSnapshot(rates={"USD": 0.04, "EUR": 0.03}, key_rates={"EUR": {"10Y": 0.03}})
    )
    bumped = base.bump(RateZero(currency="USD", tenor="PARALLEL"), 0.0025)
    assert bumped.rates["USD"] == pytest.approx(0.0425)
    assert bumped.rates["EUR"] == 0.03
    assert bumped.key_rates["USD"]["10Y"] == pytest.approx(0.0425)
    assert bumped.curves["USD_OIS"]["zeros"]["10Y"] == pytest.approx(0.0425)
    assert bumped.curves["USD_SOFR"]["zeros"]["2Y"] == pytest.approx(0.041 + 0.0025)
    # ALL is an alias for parallel.
    via_all = base.bump(RateZero(currency="USD", tenor="ALL"), 0.0025)
    assert via_all.rates["USD"] == pytest.approx(bumped.rates["USD"])
    assert via_all.key_rates["USD"] == bumped.key_rates["USD"]


def test_bump_rate_tenor_does_not_parallel_shift_scalar_rates():
    base = attach_standard_usd_curves(MarketSnapshot(rates={"USD": 0.04}))
    bumped = base.bump(RateZero(currency="USD", tenor="10Y"), 0.0025)
    assert bumped.rates["USD"] == pytest.approx(0.04)
    assert bumped.key_rates["USD"]["10Y"] == pytest.approx(0.0425)
    assert bumped.key_rates["USD"]["2Y"] == pytest.approx(0.04)
    assert bumped.curves["USD_OIS"]["zeros"]["10Y"] == pytest.approx(0.0425)
    assert bumped.curves["USD_OIS"]["zeros"]["2Y"] == pytest.approx(0.04)
    assert bumped.curves["USD_SOFR"]["zeros"]["10Y"] == pytest.approx(0.041 + 0.0025)


def test_bump_rate_tenor_missing_raises():
    base = MarketSnapshot(rates={"USD": 0.04})
    with pytest.raises(KeyError, match="PARALLEL"):
        base.bump(RateZero(currency="USD", tenor="10Y"), 0.001)


def test_bump_vol_is_relative():
    base = MarketSnapshot(equity_vols={"SPY": 0.20}, fx_vols={"EURUSD": 0.10}, rates={"USD": 0.04})
    eq = base.bump(EquityVol(underlying="SPY"), 0.25)
    assert eq.equity_vols["SPY"] == pytest.approx(0.25)
    fx = base.bump(FXVol(pair="EURUSD"), 0.10)
    assert fx.fx_vols["EURUSD"] == pytest.approx(0.11)


def test_bump_vol_rewrites_attached_surface_grids_and_keeps_copies_frozen():
    base = attach_vol_surface(
        attach_vol_surface(
            MarketSnapshot(equity_vols={"SPY": 0.20}, fx_vols={"EURUSD": 0.10}, rates={"USD": 0.04}),
            build_equity_vol_surface("SPY", 0.20),
        ),
        build_fx_vol_surface("EURUSD", 0.10),
    )

    bumped = base.bump(EquityVol(underlying="SPY"), 0.25).bump(FXVol(pair="EURUSD"), 0.10)

    assert bumped.equity_vols["SPY"] == pytest.approx(0.25)
    assert bumped.vol_surfaces["SPY"]["atm_vol"] == pytest.approx(0.25)
    assert bumped.vol_surfaces["SPY"]["grid"]["1Y|1"] == pytest.approx(0.25)
    assert bumped.vol_surfaces["SPY"]["grid"]["2Y|1.2"] == pytest.approx(0.25)
    assert base.vol_surfaces["SPY"]["grid"]["1Y|1"] == pytest.approx(0.20)

    assert bumped.fx_vols["EURUSD"] == pytest.approx(0.11)
    assert bumped.vol_surfaces["EURUSD"]["atm_vol"] == pytest.approx(0.11)
    assert bumped.vol_surfaces["EURUSD"]["grid"]["1Y|1"] == pytest.approx(0.11)
    assert bumped.vol_surfaces["EURUSD"]["grid"]["2Y|0.8"] == pytest.approx(0.11)
    assert base.vol_surfaces["EURUSD"]["grid"]["1Y|1"] == pytest.approx(0.10)

    with pytest.raises(TypeError):
        bumped.vol_surfaces["SPY"]["grid"]["1Y|1"] = 0.99  # type: ignore[index]


def test_apply_vol_shock_updates_attached_surface_grids():
    base = attach_vol_surface(
        MarketSnapshot(equity_vols={"SPY": 0.20}, rates={"USD": 0.04}),
        build_equity_vol_surface("SPY", 0.20),
    )

    out = base.apply([(EquityVol(underlying="SPY"), 0.50)])

    assert out.equity_vols["SPY"] == pytest.approx(0.30)
    assert out.vol_surfaces["SPY"]["atm_vol"] == pytest.approx(0.30)
    assert out.vol_surfaces["SPY"]["grid"]["1M|0.8"] == pytest.approx(0.30)
    assert out.vol_surfaces["SPY"]["grid"]["2Y|1.2"] == pytest.approx(0.30)


def test_surface_vol_bucket_skew_and_term_shocks_use_surface_model():
    base = attach_vol_surface(
        MarketSnapshot(equity_vols={"SPY": 0.20}, rates={"USD": 0.04}),
        build_equity_vol_surface("SPY", 0.20),
    )

    bucket = base.bump(EquityVol(underlying="SPY", expiry="1Y"), 0.25)
    assert bucket.vol_surfaces["SPY"]["grid"]["1Y|1"] == pytest.approx(0.25)
    assert bucket.vol_surfaces["SPY"]["grid"]["3M|1"] == pytest.approx(0.20)
    assert bucket.equity_vols["SPY"] == pytest.approx(0.25)

    skew = base.bump(EquityVol(underlying="SPY", moneyness="SKEW"), 0.10)
    assert skew.vol_surfaces["SPY"]["grid"]["1Y|0.8"] == pytest.approx(0.18)
    assert skew.vol_surfaces["SPY"]["grid"]["1Y|1"] == pytest.approx(0.20)
    assert skew.vol_surfaces["SPY"]["grid"]["1Y|1.2"] == pytest.approx(0.22)
    assert skew.equity_vols["SPY"] == pytest.approx(0.20)

    term = base.bump(EquityVol(underlying="SPY", expiry="TERM"), 0.02)
    assert term.vol_surfaces["SPY"]["grid"]["3M|1"] == pytest.approx(0.20 + 0.02 * 0.25)
    assert term.vol_surfaces["SPY"]["grid"]["1Y|1"] == pytest.approx(0.22)
    assert term.vol_surfaces["SPY"]["grid"]["2Y|1"] == pytest.approx(0.24)
    assert term.equity_vols["SPY"] == pytest.approx(0.22)


def test_apply_multiple_shocks():
    base = MarketSnapshot(
        equity_spots={"SPY": 100.0},
        equity_vols={"SPY": 0.20},
        fx_spots={"EURUSD": 1.10},
        rates={"USD": 0.04},
        key_rates={"USD": {"5Y": 0.04}},
    )
    out = base.apply(
        [
            (EquitySpot("SPY"), -0.20),
            (EquityVol(underlying="SPY"), 0.50),
            (RateZero(currency="USD", tenor="PARALLEL"), 0.01),
            (FXSpot("EURUSD"), -0.05),
        ]
    )
    assert out.equity_spots["SPY"] == pytest.approx(80.0)
    assert out.equity_vols["SPY"] == pytest.approx(0.30)
    assert out.rates["USD"] == pytest.approx(0.05)
    assert out.key_rates["USD"]["5Y"] == pytest.approx(0.05)
    assert out.fx_spots["EURUSD"] == pytest.approx(1.10 * 0.95)


def _sequential_bump(base: MarketSnapshot, shocks: list) -> MarketSnapshot:
    out = base
    for factor, amount in shocks:
        out = out.bump(factor, amount)
    return out


def test_apply_mark_parity_vs_sequential_bump_multifactor():
    """R0.4.4: one-pass apply must match sequential bump marks exactly."""
    base = attach_vol_surface(
        attach_standard_usd_curves(
            MarketSnapshot(
                id="base",
                equity_spots={"SPY": 100.0, "NVDA": 50.0},
                equity_vols={"SPY": 0.20},
                fx_spots={"EURUSD": 1.10},
                fx_vols={"EURUSD": 0.10},
                rates={"USD": 0.04, "EUR": 0.03},
                key_rates={"EUR": {"10Y": 0.03}},
            )
        ),
        build_equity_vol_surface("SPY", 0.20),
    )
    shocks = [
        (EquitySpot("SPY"), -0.10),
        (EquitySpot("NVDA"), 0.05),
        (EquityVol(underlying="SPY"), 0.25),
        (FXSpot("EURUSD"), -0.05),
        (FXVol(pair="EURUSD"), 0.10),
        (RateZero(currency="USD", tenor="PARALLEL"), 0.0025),
        (RateZero(currency="USD", tenor="10Y"), 0.001),
        (RateZero(currency="EUR", tenor="ALL"), 0.0015),
    ]
    via_apply = base.apply(shocks)
    via_seq = _sequential_bump(base, shocks)

    assert via_apply.equity_spots == via_seq.equity_spots
    assert via_apply.equity_vols == via_seq.equity_vols
    assert via_apply.fx_spots == via_seq.fx_spots
    assert via_apply.fx_vols == via_seq.fx_vols
    assert via_apply.rates == via_seq.rates
    assert via_apply.key_rates == via_seq.key_rates
    assert via_apply.curves == via_seq.curves
    assert via_apply.vol_surfaces == via_seq.vol_surfaces
    assert via_apply.content_hash() == via_seq.content_hash()
    # Id policy: apply chains the same ``:bump:`` id segments as sequential bump
    # so the final id matches the last bump in the chain (documented on apply).
    assert via_apply.id == via_seq.id


def test_apply_freezes_once_not_per_factor(monkeypatch):
    """R0.4.4 / RF-006: multi-factor apply is O(1) freeze/copy, not O(K)."""
    base = MarketSnapshot(
        id="base",
        equity_spots={"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0, "E": 50.0},
        rates={"USD": 0.04},
    )
    shocks = [
        (EquitySpot("A"), 0.01),
        (EquitySpot("B"), 0.02),
        (EquitySpot("C"), -0.01),
        (EquitySpot("D"), 0.03),
        (EquitySpot("E"), -0.02),
        (RateZero(currency="USD", tenor="PARALLEL"), 0.0001),
    ]
    k = len(shocks)
    assert k >= 5

    copy_calls = {"n": 0}
    freeze_calls = {"n": 0}
    real_copy = MarketSnapshot.model_copy
    real_freeze = MarketSnapshot._apply_nested_freeze

    def counting_copy(self, *args, **kwargs):
        copy_calls["n"] += 1
        return real_copy(self, *args, **kwargs)

    def counting_freeze(self):
        freeze_calls["n"] += 1
        return real_freeze(self)

    monkeypatch.setattr(MarketSnapshot, "model_copy", counting_copy)
    monkeypatch.setattr(MarketSnapshot, "_apply_nested_freeze", counting_freeze)

    out = base.apply(shocks)
    # Tight O(1) band: instrumentation must fire (lower bound) and must not
    # grow with K (upper bound). Vacuous 0/0 would incorrectly pass upper-only.
    assert copy_calls["n"] == 1, (
        f"model_copy called {copy_calls['n']} times for {k} shocks; expected exactly 1"
    )
    assert 1 <= freeze_calls["n"] <= 2, (
        f"_apply_nested_freeze called {freeze_calls['n']} times for {k} shocks; "
        f"expected 1..2 (not O({k}))"
    )
    assert out.equity_spots["A"] == pytest.approx(10.1)
    assert out.equity_spots["E"] == pytest.approx(49.0)
    assert out.rates["USD"] == pytest.approx(0.0401)


def test_diff_identical_is_empty():
    a = MarketSnapshot(equity_spots={"SPY": 100.0}, rates={"USD": 0.04})
    b = MarketSnapshot(equity_spots={"SPY": 100.0}, rates={"USD": 0.04})
    assert a.diff(b) == {}


def test_diff_reports_relative_spots_and_absolute_rates():
    a = MarketSnapshot(equity_spots={"SPY": 100.0}, rates={"USD": 0.04}, equity_vols={"SPY": 0.20})
    b = MarketSnapshot(equity_spots={"SPY": 110.0}, rates={"USD": 0.045}, equity_vols={"SPY": 0.22})
    d = a.diff(b)
    assert d[EquitySpot("SPY").key] == pytest.approx(0.10)
    assert d["USD:RATE"] == pytest.approx(0.005)
    assert d["SPY:VOL"] == pytest.approx(0.10)  # relative vol change


def test_diff_includes_key_rates_curves_vols_projection_dividends():
    from app.domain.models import _deep_unfreeze

    a = attach_vol_surface(
        attach_standard_usd_curves(
            MarketSnapshot(
                rates={"USD": 0.04},
                dividend_yields={"SPY": 0.01},
            )
        ),
        build_equity_vol_surface("SPY", 0.20),
    )
    b = a.bump(RateZero("USD", "10Y"), 0.005)
    surfaces = _deep_unfreeze(a.vol_surfaces)
    surfaces["SPY"]["atm_vol"] = 0.22
    surfaces["SPY"]["grid"]["1Y|1"] = 0.22
    b = b.model_copy(
        update={
            "dividend_yields": {"SPY": 0.015},
            "projection_rates": {"USD": float(a.projection_rates["USD"]) + 0.001},
            "vol_surfaces": surfaces,
        }
    )
    d = a.diff(b)
    assert d["USD:RATE:10Y"] == pytest.approx(0.005)
    assert d["USD_OIS:ZERO:10Y"] == pytest.approx(0.005)
    assert d["USD:PROJ"] == pytest.approx(0.001)
    assert d["SPY:DIV"] == pytest.approx(0.005)
    assert d["SPY:ATM_VOL"] == pytest.approx(0.10)
    assert d["SPY:VOL:1Y|1"] == pytest.approx(0.10)
    assert "USD:RATE" not in d  # tenor bump must not look like a parallel rate diff


def test_content_hash_stable_for_equal_marks():
    a = MarketSnapshot(id="a", as_of="t0", equity_spots={"SPY": 100.0}, rates={"USD": 0.04})
    b = MarketSnapshot(id="b", as_of="current", equity_spots={"SPY": 100.0}, rates={"USD": 0.04})
    assert a.content_hash() == b.content_hash()
    c = a.bump(EquitySpot("SPY"), 0.01)
    assert c.content_hash() != a.content_hash()


def test_as_of_iso_string_coerces_to_date():
    snap = MarketSnapshot(as_of="2018-01-01", rates={"USD": 0.04})
    assert snap.as_of == date(2018, 1, 1)
    assert snap.as_of != date.today()


def test_as_of_date_is_kept():
    snap = MarketSnapshot(as_of=date(2024, 6, 14), rates={"USD": 0.04})
    assert snap.as_of == date(2024, 6, 14)


def test_as_of_engine_labels_are_not_wall_clock():
    today = date.today()
    current = MarketSnapshot(as_of="current", rates={"USD": 0.04})
    t0 = MarketSnapshot(as_of="t0", rates={"USD": 0.04})
    defaulted = MarketSnapshot(rates={"USD": 0.04})
    assert current.as_of == "current"
    assert t0.as_of == "t0"
    assert defaulted.as_of == "current"
    assert current.as_of != today
    assert t0.as_of != today


def test_as_of_rejects_unparseable_and_datetime():
    with pytest.raises(ValidationError):
        MarketSnapshot(as_of="later", rates={"USD": 0.04})
    with pytest.raises(ValidationError):
        MarketSnapshot(as_of="not-a-date", rates={"USD": 0.04})
    with pytest.raises(ValidationError):
        MarketSnapshot(as_of="2018-1-1", rates={"USD": 0.04})
    with pytest.raises(ValidationError):
        MarketSnapshot(as_of="", rates={"USD": 0.04})
    with pytest.raises(ValidationError):
        MarketSnapshot(as_of=datetime(2018, 1, 1, 12, 0), rates={"USD": 0.04})


def test_as_of_json_round_trip_stays_string_on_the_wire():
    snap = MarketSnapshot(id="s", as_of="2026-09-02", rates={"USD": 0.04})
    dumped = snap.model_dump(mode="json")
    assert dumped["as_of"] == "2026-09-02"
    loaded = MarketSnapshot.model_validate(dumped)
    assert loaded.as_of == date(2026, 9, 2)


def test_as_of_model_copy_parses_iso_and_rejects_garbage():
    base = MarketSnapshot(as_of="current", rates={"USD": 0.04})
    copied = base.model_copy(update={"as_of": "2024-06-14"})
    assert copied.as_of == date(2024, 6, 14)
    with pytest.raises(ValidationError):
        base.model_copy(update={"as_of": "illustrative_previous"})


def test_shock_snapshot_matches_typed_apply():
    base = MarketSnapshot(
        equity_spots={"SPY": 100.0, "NVDA": 200.0},
        equity_vols={"SPY": 0.20},
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.12},
        rates={"USD": 0.04, "EUR": 0.03},
    )
    scenario = StressScenario(
        name="combo",
        equity_shock=-0.10,
        vol_shock=0.25,
        rates_shift_bps=50,
        fx_shock=-0.05,
    )
    shocked = shock_snapshot(base, scenario)
    via_apply = base.apply(
        [
            (EquitySpot("SPY"), -0.10),
            (EquitySpot("NVDA"), -0.10),
            (EquityVol(underlying="SPY"), 0.25),
            (FXSpot("EURUSD"), -0.05),
            (FXVol(pair="EURUSD"), 0.25),
            (RateZero(currency="USD", tenor="ALL"), 0.005),
            (RateZero(currency="EUR", tenor="ALL"), 0.005),
        ]
    )
    assert shocked.equity_spots == via_apply.equity_spots
    assert shocked.equity_vols == via_apply.equity_vols
    assert shocked.fx_spots == via_apply.fx_spots
    assert shocked.fx_vols == via_apply.fx_vols
    assert shocked.rates == via_apply.rates


def test_submarket_views_expose_grouped_marks():
    """R0.4.1-A: typed views are the canonical grouped inspection API."""
    from types import MappingProxyType

    from app.market.curves import YieldCurve
    from app.market.markets import EquityMarket, FxMarket, RateMarket, VolMarket
    from app.market.vol_surfaces import VolSurface

    snap = MarketSnapshot(
        equity_spots={"SPY": 100.0},
        equity_vols={"SPY": 0.2},
        fx_spots={"EURUSD": 1.1},
        fx_vols={"EURUSD": 0.1},
        rates={"USD": 0.04},
        dividend_yields={"SPY": 0.015},
        projection_rates={"USD": 0.041},
        rate_spreads={"USD": 0.001},
        key_rates={"USD": {"10Y": 0.041}},
        vol_surfaces={"SPY": build_equity_vol_surface("SPY", 0.2).to_dict()},
    )

    equity = snap.equity
    rates = snap.rates_market
    vol = snap.vol
    fx = snap.fx

    assert isinstance(equity, EquityMarket)
    assert isinstance(rates, RateMarket)
    assert isinstance(vol, VolMarket)
    assert isinstance(fx, FxMarket)

    assert equity.spots is snap.equity_spots
    assert equity.dividend_yields is snap.dividend_yields
    assert equity.spots["SPY"] == 100.0
    assert equity.dividend_yields["SPY"] == 0.015

    assert rates.discount is snap.rates
    assert rates.projection is snap.projection_rates
    assert rates.spreads is snap.rate_spreads
    assert rates.key_rates is snap.key_rates
    assert rates.discount["USD"] == 0.04
    assert rates.projection["USD"] == 0.041
    assert rates.spreads["USD"] == 0.001
    assert rates.key_rates["USD"]["10Y"] == 0.041

    assert vol.equity is snap.equity_vols
    assert vol.fx is snap.fx_vols
    assert isinstance(vol.surfaces["SPY"], VolSurface)
    assert vol.equity["SPY"] == 0.2
    assert vol.fx["EURUSD"] == 0.1
    assert vol.surfaces["SPY"].atm_vol() == pytest.approx(0.2)
    assert dict(rates.curves) == {}
    assert all(isinstance(curve, YieldCurve) for curve in rates.curves.values())

    assert fx.spots is snap.fx_spots
    assert fx.spots["EURUSD"] == 1.1

    # Frozen dataclass + MappingProxy-backed nested marks.
    with pytest.raises(Exception):
        equity.spots = {}  # type: ignore[misc]
    with pytest.raises(Exception):
        rates.discount = {}  # type: ignore[misc]
    assert isinstance(equity.spots, MappingProxyType)
    assert isinstance(rates.key_rates, MappingProxyType)
    assert isinstance(vol.surfaces, MappingProxyType)
    assert isinstance(fx.spots, MappingProxyType)
    with pytest.raises(TypeError):
        equity.spots["SPY"] = 1.0  # type: ignore[index]
    with pytest.raises(TypeError):
        rates.key_rates["USD"]["10Y"] = 0.99  # type: ignore[index]
    with pytest.raises(TypeError):
        vol.surfaces["SPY"] = vol.surfaces["SPY"]  # type: ignore[index]
    with pytest.raises(TypeError):
        fx.spots["EURUSD"] = 0.0  # type: ignore[index]


def test_vol_market_surfaces_are_typed_vol_surfaces():
    from types import MappingProxyType

    from app.market.vol_surfaces import VolSurface

    snap = attach_vol_surface(
        MarketSnapshot(equity_vols={"SPY": 0.18}, rates={"USD": 0.04}),
        build_equity_vol_surface("SPY", 0.18),
    )
    surfaces = snap.vol.surfaces
    assert isinstance(surfaces, MappingProxyType)
    surface = surfaces["SPY"]
    assert isinstance(surface, VolSurface)
    assert surface.name == "SPY"
    assert surface.asset_class == "equity"
    assert surface.atm_vol() == pytest.approx(0.18)
    # Flat storage remains the dict payload.
    assert snap.vol_surfaces["SPY"]["atm_vol"] == pytest.approx(0.18)


def test_empty_vol_surfaces_view_is_empty_mapping():
    snap = MarketSnapshot(rates={"USD": 0.04}, vol_surfaces={})
    assert dict(snap.vol.surfaces) == {}


def test_invalid_vol_surface_payload_fails_closed():
    snap = MarketSnapshot(
        rates={"USD": 0.04},
        vol_surfaces={"SPY": {"asset_class": "equity", "atm_vol": 0.2}},
    )
    with pytest.raises((ValueError, KeyError, TypeError)):
        _ = snap.vol.surfaces


def test_vol_surface_missing_asset_class_fails_closed():
    snap = MarketSnapshot(
        rates={"USD": 0.04},
        vol_surfaces={"SPY": {"grid": {"1Y|1": 0.2}}},
    )
    with pytest.raises((ValueError, KeyError, TypeError)):
        _ = snap.vol.surfaces


def test_rate_market_exposes_typed_yield_curves():
    from types import MappingProxyType

    from app.market.curves import YieldCurve

    snap = attach_standard_usd_curves(MarketSnapshot(rates={"USD": 0.04}))
    rates = snap.rates_market
    assert isinstance(rates.curves, MappingProxyType)
    ois = rates.curves["USD_OIS"]
    sofr = rates.curves["USD_SOFR"]
    assert isinstance(ois, YieldCurve)
    assert isinstance(sofr, YieldCurve)
    assert ois.currency == "USD"
    assert ois.curve_type == "discount"
    assert ois.zero(10.0) == pytest.approx(0.04)
    assert sofr.curve_type == "projection"
    assert sofr.zero(2.0) == pytest.approx(0.041)
    # Scalars stay the frozen snapshot maps.
    assert rates.discount is snap.rates
    assert rates.projection is snap.projection_rates
    assert rates.spreads is snap.rate_spreads
    assert rates.key_rates is snap.key_rates
    # Flat storage unchanged.
    assert snap.curves["USD_OIS"]["zeros"]["10Y"] == pytest.approx(0.04)


def test_empty_curves_view_is_empty_mapping():
    snap = MarketSnapshot(rates={"USD": 0.04}, curves={})
    assert dict(snap.rates_market.curves) == {}


def test_invalid_curve_payload_fails_closed():
    snap = MarketSnapshot(rates={"USD": 0.04}, curves={"USD_OIS": {"currency": "USD"}})
    with pytest.raises((ValueError, KeyError, TypeError)):
        _ = snap.rates_market.curves


def test_curve_empty_zeros_payload_fails_closed():
    snap = MarketSnapshot(
        rates={"USD": 0.04},
        curves={"USD_OIS": {"currency": "USD", "curve_type": "discount", "zeros": {}}},
    )
    with pytest.raises((ValueError, KeyError, TypeError)):
        _ = snap.rates_market.curves


def test_bootstrapped_curve_is_typed_on_rate_market():
    from app.market.curves import CurveBootstrapInstrument, YieldCurve, attach_bootstrapped_curve

    snap = attach_bootstrapped_curve(
        MarketSnapshot(id="boot", rates={"USD": 0.01}),
        currency="USD",
        curve_type="discount",
        name="USD_BOOT",
        instruments=[
            CurveBootstrapInstrument(kind="deposit", tenor="6M", rate=0.04),
            CurveBootstrapInstrument(kind="zero", tenor="1Y", rate=0.041),
            CurveBootstrapInstrument(kind="zero", tenor="2Y", rate=0.042),
        ],
    )
    curve = snap.rates_market.curves["USD_BOOT"]
    assert isinstance(curve, YieldCurve)
    assert tuple(n.tenor for n in curve.nodes) == ("6M", "1Y", "2Y")
    assert curve.zero(1.0) == pytest.approx(0.041)


def test_invalid_fx_spot_key_fails_closed():
    with pytest.raises((ValidationError, ValueError, KeyError, TypeError)):
        MarketSnapshot(fx_spots={"EUR/USD": 1.1}, rates={"USD": 0.04})


def test_fx_market_rejects_non_iso_pair_keys():
    from app.market.markets import FxMarket

    with pytest.raises((ValueError, KeyError, TypeError)):
        FxMarket(spots={"US": 1.0})


def test_empty_fx_spots_remain_valid():
    snap = MarketSnapshot(fx_spots={}, rates={"USD": 0.04})
    assert dict(snap.fx.spots) == {}
    assert dict(snap.fx_spots) == {}
