"""M1.4 yield-curve domain: nodes, interpolation, parallel/key-rate shocks."""

from __future__ import annotations

import math

import pytest

from app.market.curves import (
    KEY_TENORS,
    TENOR_YEARS,
    YieldCurve,
    build_flat_curve,
    build_usd_ois_discount,
    build_usd_sofr_projection,
)


def test_key_tenors_cover_required_set():
    assert KEY_TENORS == ("1Y", "2Y", "5Y", "7Y", "10Y", "20Y", "30Y")
    assert set(TENOR_YEARS) == set(KEY_TENORS)


def test_flat_curve_df_and_zero():
    curve = build_flat_curve("USD", "discount", "USD_FLAT", 0.04)
    assert curve.zero(10.0) == pytest.approx(0.04)
    assert curve.df(10.0) == pytest.approx(math.exp(-0.04 * 10.0))


def test_usd_ois_and_sofr_have_all_key_nodes():
    ois = build_usd_ois_discount(base_rate=0.04)
    sofr = build_usd_sofr_projection(base_rate=0.041)
    assert ois.name == "USD_OIS"
    assert sofr.name == "USD_SOFR"
    assert ois.curve_type == "discount"
    assert sofr.curve_type == "projection"
    assert tuple(n.tenor for n in ois.nodes) == KEY_TENORS
    assert tuple(n.tenor for n in sofr.nodes) == KEY_TENORS


def test_interpolation_between_nodes():
    # Upward sloping zeros: 2Y=3%, 5Y=4% → 3Y between them.
    nodes = {
        "1Y": 0.03,
        "2Y": 0.03,
        "5Y": 0.04,
        "7Y": 0.04,
        "10Y": 0.042,
        "20Y": 0.043,
        "30Y": 0.044,
    }
    curve = YieldCurve.from_zero_dict("USD", "discount", "USD_TEST", nodes)
    z3 = curve.zero(3.0)
    assert 0.03 < z3 < 0.04


def test_parallel_shift_bps():
    curve = build_usd_ois_discount(0.04)
    shifted = curve.parallel_shift_bps(25)
    assert shifted.zero(10.0) == pytest.approx(curve.zero(10.0) + 0.0025)
    assert curve.zero(10.0) == pytest.approx(0.04)  # immutable


def test_key_rate_shift_only_moves_target_tenor_with_triangular_weights():
    curve = build_flat_curve("USD", "discount", "USD_FLAT", 0.04)
    shocked = curve.key_rate_shift_bps("10Y", 50)
    # Exact node moves by 50bp; adjacent KEY_TENOR nodes stay put (tent weight 0);
    # interpolated points between 7Y–10Y and 10Y–20Y receive partial bumps.
    assert shocked.zero(TENOR_YEARS["10Y"]) == pytest.approx(0.045)
    assert shocked.zero(TENOR_YEARS["7Y"]) == pytest.approx(0.04)
    assert shocked.zero(TENOR_YEARS["20Y"]) == pytest.approx(0.04)
    assert shocked.zero(8.5) > 0.04
    assert shocked.zero(15.0) > 0.04
    assert shocked.zero(TENOR_YEARS["1Y"]) == pytest.approx(0.04)
    assert shocked.zero(TENOR_YEARS["30Y"]) == pytest.approx(0.04)


def test_snapshot_attaches_usd_curves_and_key_rates():
    from app.market.curves import attach_standard_usd_curves
    from app.domain.models import MarketSnapshot

    base = MarketSnapshot(rates={"USD": 0.04})
    snap = attach_standard_usd_curves(base, ois_rate=0.04, sofr_rate=0.041)
    assert "USD_OIS" in snap.curves
    assert "USD_SOFR" in snap.curves
    assert snap.key_rates["USD"]["10Y"] == pytest.approx(0.04)
    assert snap.rates_market.discount["USD"] == pytest.approx(0.04)


def test_eur_gbp_flat_builders_exist_for_architecture():
    eur = build_flat_curve("EUR", "discount", "EUR_OIS", 0.02)
    gbp = build_flat_curve("GBP", "discount", "GBP_SONIA", 0.03)
    assert eur.currency == "EUR"
    assert gbp.currency == "GBP"
