"""R0.4.3 — pin canonical shock-unit conversion helpers and call-site wiring.

Wrong scales (×100, ÷100, bp-as-percent) must not equal the helpers.
R0.4.3-B: wired risk call sites must import helpers (no inline ×100 / ÷10000
on relative-vol→points or bp→decimal shock paths); reverse-stress must not
guess rate units from magnitude.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from app.risk import attribution, es, historical, reverse_stress, sensitivities
from app.risk import scenario_model, scenarios
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


def test_wired_call_sites_import_shock_units_helpers():
    """R0.4.3-B / R0.4.2-A wiring pin: restore of inline ×100 / ÷10000 must fail source checks."""
    assert "relative_vol_move_to_vol_points" in inspect.getsource(historical.approximate_pnl_series)
    assert "relative_vol_move_to_vol_points" in inspect.getsource(historical._panel_linear_contribution)
    assert "relative_vol_move_to_vol_points" in inspect.getsource(es._aggregate_factor_pnl_linear)
    assert "relative_vol_move_to_vol_points" in inspect.getsource(attribution._greek_buckets_for_position)
    assert "decimal_rate_to_bps" in inspect.getsource(attribution._greek_buckets_for_position)
    assert "bps_to_decimal_rate" in inspect.getsource(reverse_stress.build_single_factor_shocks)
    sens_src = inspect.getsource(sensitivities.SensitivityEngine)
    assert "bps_to_decimal_rate" in sens_src
    assert "bps_to_decimal_rate" in inspect.getsource(scenario_model._expand_stress_to_shocks)
    assert "decimal_rate_to_bps" in inspect.getsource(scenario_model.scenario_to_stress)
    assert "bps_to_decimal_rate" in inspect.getsource(scenarios.expand_aggregate_change)
    assert "bps_to_decimal_rate" in inspect.getsource(scenarios.panel_amount_to_bump)
    assert "decimal_rate_to_bps" in inspect.getsource(scenarios.to_stress_scenario)


def test_wired_risk_modules_no_inline_vol_point_or_bp_shock_literals():
    """Inline relative→points / bp→decimal shock scales belong only in shock_units."""
    panel_src = inspect.getsource(historical._panel_linear_contribution)
    assert "move * 100" not in panel_src
    assert "* 100.0" not in panel_src

    approx_src = inspect.getsource(historical.approximate_pnl_series)
    assert "* 100.0" not in approx_src
    assert "* 100" not in approx_src

    es_src = inspect.getsource(es._aggregate_factor_pnl_linear)
    assert "vol_pct * 100" not in es_src
    assert "* 100.0" not in es_src

    attr_src = inspect.getsource(attribution._greek_buckets_for_position)
    assert "* 100.0" not in attr_src
    assert "* 10000.0" not in attr_src
    assert "* 10_000" not in attr_src

    rates_src = inspect.getsource(reverse_stress.build_single_factor_shocks)
    assert "/ 10000" not in rates_src
    assert "/ 10_000" not in rates_src

    # R0.4.2-A: scenario expand/collapse modules convert only via helpers.
    for mod in (scenario_model, scenarios):
        src = inspect.getsource(mod)
        assert "/ 10000" not in src
        assert "/ 10_000" not in src
        assert "* 10000" not in src
        assert "* 10_000" not in src


def test_from_wire_bound_never_guesses_bp_from_magnitude():
    src = inspect.getsource(reverse_stress.from_wire_bound)
    assert "max_shock > 1" not in src
    assert "RATES_BP_SCALE" not in src
    # 500 stays 500 (search magnitude); 500 bp wire requires magnitude 0.5.
    assert reverse_stress.from_wire_bound("rates", 500.0) == pytest.approx(500.0)
    assert reverse_stress.to_wire_shock("rates", 0.5) == pytest.approx(500.0)
