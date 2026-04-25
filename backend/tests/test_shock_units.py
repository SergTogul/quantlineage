"""R0.4.3-A — pin canonical shock-unit conversion helpers.

Wrong scales (×100, ÷100, bp-as-percent) must not equal the helpers.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.risk.shock_units import (
    bps_to_decimal_rate,
    decimal_rate_to_bps,
    relative_vol_move_to_vol_points,
)


def test_bps_to_decimal_rate_one_bp():
    assert bps_to_decimal_rate(1.0) == pytest.approx(0.0001, abs=1e-18)
    assert bps_to_decimal_rate(1.0) != pytest.approx(0.01, abs=1e-12)  # bp-as-percent
    assert bps_to_decimal_rate(1.0) != pytest.approx(1.0 / 100.0, abs=1e-12)  # ÷100
    assert bps_to_decimal_rate(1.0) != pytest.approx(1.0 * 100.0, abs=1e-9)  # ×100


def test_bps_to_decimal_rate_ten_and_hundred():
    assert bps_to_decimal_rate(10.0) == pytest.approx(0.001, abs=1e-18)
    assert bps_to_decimal_rate(100.0) == pytest.approx(0.01, abs=1e-18)
    # 10bp treated as 10% or as decimal 10/100
    assert bps_to_decimal_rate(10.0) != pytest.approx(0.10, abs=1e-12)
    assert bps_to_decimal_rate(10.0) != pytest.approx(10.0 / 100.0, abs=1e-12)


def test_decimal_rate_to_bps_round_trip():
    assert decimal_rate_to_bps(0.0001) == pytest.approx(1.0, abs=1e-12)
    assert decimal_rate_to_bps(0.01) == pytest.approx(100.0, abs=1e-12)
    assert decimal_rate_to_bps(bps_to_decimal_rate(25.0)) == pytest.approx(25.0, abs=1e-12)
    # Wrong inverse scales
    assert decimal_rate_to_bps(0.0001) != pytest.approx(0.0001 * 100.0, abs=1e-12)  # ×100
    assert decimal_rate_to_bps(0.0001) != pytest.approx(0.0001 / 100.0, abs=1e-18)  # ÷100
    assert decimal_rate_to_bps(0.01) != pytest.approx(1.0, abs=1e-12)  # bp-as-percent style


def test_relative_vol_move_to_vol_points_scalar():
    assert relative_vol_move_to_vol_points(0.01) == pytest.approx(1.0, abs=1e-12)
    assert relative_vol_move_to_vol_points(0.04) == pytest.approx(4.0, abs=1e-12)
    # Forgetting ×100 (vega÷100 style)
    assert relative_vol_move_to_vol_points(0.04) != pytest.approx(0.04, abs=1e-12)
    assert relative_vol_move_to_vol_points(0.04) != pytest.approx(0.04 / 100.0, abs=1e-18)
    # Treating relative move as whole percent points without /100 first
    assert relative_vol_move_to_vol_points(0.04) != pytest.approx(4.0 / 100.0, abs=1e-12)


def test_relative_vol_move_to_vol_points_array():
    vol_pct = np.array([0.0, 0.01, -0.02, 0.25], dtype=float)
    points = relative_vol_move_to_vol_points(vol_pct)
    np.testing.assert_allclose(points, np.array([0.0, 1.0, -2.0, 25.0]), atol=1e-12)
    assert not np.allclose(points, vol_pct)  # missing ×100
    assert not np.allclose(points, vol_pct / 100.0)  # ÷100
    assert not np.allclose(points, vol_pct * 100.0 / 100.0)  # cancel scales
