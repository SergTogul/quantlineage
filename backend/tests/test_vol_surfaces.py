"""M1.5 volatility surfaces: equity/FX grids, lookup, and shock ops.

Conventions
-----------
- Vols are absolute decimals (0.20 = 20%).
- Parallel / bucket shocks are absolute vol shifts (0.01 = +1 vol point).
- Moneyness is strike/spot (1.0 = ATM).
- Expiry axis uses year fractions with labeled buckets.
"""

from __future__ import annotations

import math

import pytest

from app.market.vol_surfaces import (
    DEFAULT_EXPIRIES,
    DEFAULT_MONEYNESS,
    EXPIRY_YEARS,
    EquityVolSurface,
    FxVolSurface,
    VolSurface,
    attach_vol_surface,
    build_equity_vol_surface,
    build_fx_vol_surface,
    flat_vol_grid,
)


@pytest.fixture
def eq_surf() -> EquityVolSurface:
    return build_equity_vol_surface("SPY", 0.20)


@pytest.fixture
def fx_surf() -> FxVolSurface:
    return build_fx_vol_surface("EURUSD", 0.10)


def test_default_axes():
    assert DEFAULT_EXPIRIES == ("1M", "3M", "6M", "1Y", "2Y")
    assert DEFAULT_MONEYNESS == (0.8, 0.9, 1.0, 1.1, 1.2)
    assert EXPIRY_YEARS["1Y"] == pytest.approx(1.0)


def test_flat_equity_surface_lookup(eq_surf: EquityVolSurface):
    assert eq_surf.underlying == "SPY"
    assert eq_surf.asset_class == "equity"
    assert eq_surf.vol(1.0, 1.0) == pytest.approx(0.20)
    assert eq_surf.vol(0.25, 0.9) == pytest.approx(0.20)


def test_fx_surface_metadata(fx_surf: FxVolSurface):
    assert fx_surf.pair == "EURUSD"
    assert fx_surf.asset_class == "fx"
    assert fx_surf.vol(0.5, 1.0) == pytest.approx(0.10)


def test_bilinear_interpolation_on_smile_term():
    grid = {
        ("1Y", 0.9): 0.22,
        ("1Y", 1.0): 0.20,
        ("1Y", 1.1): 0.21,
        ("2Y", 0.9): 0.24,
        ("2Y", 1.0): 0.22,
        ("2Y", 1.1): 0.23,
    }
    # Fill remaining default axis with ATM-ish flat so builder accepts full grid.
    full = flat_vol_grid(0.20)
    full.update(grid)
    surf = VolSurface.from_grid("TEST", "equity", full)
    # Mid-moneyness at 1Y between 0.9 and 1.0.
    v = surf.vol(1.0, 0.95)
    assert 0.20 < v < 0.22


def test_parallel_vol_shift(eq_surf: EquityVolSurface):
    shifted = eq_surf.parallel_shift(0.05)
    assert shifted.vol(1.0, 1.0) == pytest.approx(0.25)
    assert eq_surf.vol(1.0, 1.0) == pytest.approx(0.20)  # immutable


def test_expiry_bucket_shift(eq_surf: EquityVolSurface):
    shocked = eq_surf.expiry_bucket_shift("1Y", 0.03)
    assert shocked.vol(EXPIRY_YEARS["1Y"], 1.0) == pytest.approx(0.23)
    assert shocked.vol(EXPIRY_YEARS["3M"], 1.0) == pytest.approx(0.20)
    assert shocked.vol(EXPIRY_YEARS["2Y"], 1.0) == pytest.approx(0.20)


def test_skew_shock_tilts_wings_preserves_atm(eq_surf: EquityVolSurface):
    # +0.10 per unit moneyness away from ATM: 0.8 → -0.02, 1.2 → +0.02
    shocked = eq_surf.skew_shock(0.10)
    assert shocked.vol(1.0, 1.0) == pytest.approx(0.20)
    assert shocked.vol(1.0, 0.8) == pytest.approx(0.18)
    assert shocked.vol(1.0, 1.2) == pytest.approx(0.22)


def test_term_structure_shock_scales_with_expiry(eq_surf: EquityVolSurface):
    shocked = eq_surf.term_structure_shock(0.02)  # +2 vol pts per year
    assert shocked.vol(EXPIRY_YEARS["1Y"], 1.0) == pytest.approx(0.22)
    assert shocked.vol(EXPIRY_YEARS["2Y"], 1.0) == pytest.approx(0.24)
    # 3M ≈ 0.25y → +0.005
    assert shocked.vol(EXPIRY_YEARS["3M"], 1.0) == pytest.approx(0.20 + 0.02 * EXPIRY_YEARS["3M"])


def test_to_dict_plain_and_attach_to_snapshot():
    from app.domain.models import MarketSnapshot

    surf = build_equity_vol_surface("SPY", 0.18)
    payload = surf.to_dict()
    assert payload["asset_class"] == "equity"
    assert isinstance(payload["grid"], dict)
    assert "QuantLib" not in repr(payload)

    base = MarketSnapshot(equity_vols={"SPY": 0.18}, rates={"USD": 0.04})
    snap = attach_vol_surface(base, surf)
    assert "SPY" in snap.vol_surfaces
    assert snap.vol.surfaces["SPY"]["atm_vol"] == pytest.approx(0.18)
    # Scalar ATM mark kept in sync for pricing compatibility.
    assert snap.equity_vols["SPY"] == pytest.approx(0.18)


def test_vols_remain_positive_after_shocks(eq_surf: EquityVolSurface):
    shocked = eq_surf.parallel_shift(-0.19)
    assert shocked.vol(1.0, 1.0) == pytest.approx(0.01)
    floored = eq_surf.parallel_shift(-0.50)
    assert floored.vol(1.0, 1.0) >= 1e-6
