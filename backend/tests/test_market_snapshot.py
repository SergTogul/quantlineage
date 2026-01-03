"""M1.3 market-data domain: immutability, bump/apply/diff, content identity."""

from __future__ import annotations

import pytest

from app.domain.models import MarketSnapshot, StressScenario
from app.market.curves import attach_standard_usd_curves
from app.market.snapshot import shock_snapshot
from app.market.vol_surfaces import attach_vol_surface, build_equity_vol_surface
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
    b = MarketSnapshot(id="b", as_of="t1", equity_spots={"SPY": 100.0}, rates={"USD": 0.04})
    assert a.content_hash() == b.content_hash()
    c = a.bump(EquitySpot("SPY"), 0.01)
    assert c.content_hash() != a.content_hash()


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
    snap = MarketSnapshot(
        equity_spots={"SPY": 100.0},
        equity_vols={"SPY": 0.2},
        fx_spots={"EURUSD": 1.1},
        fx_vols={"EURUSD": 0.1},
        rates={"USD": 0.04},
        key_rates={"USD": {"10Y": 0.041}},
    )
    assert snap.equity.spots["SPY"] == 100.0
    assert snap.vol.equity["SPY"] == 0.2
    assert snap.fx.spots["EURUSD"] == 1.1
    assert snap.rates_market.discount["USD"] == 0.04
    assert snap.rates_market.key_rates["USD"]["10Y"] == 0.041
