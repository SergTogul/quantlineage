"""R0.6.8 nightly — N=100 × S=50 reconstruction full-reval (not a host SLA).

Skipped unless ``QUANTLINEAGE_NIGHTLY=1`` so PR-FAST / backend-pytest stay fast.
Records wall / RSS / scenarios/sec / checksums; does not invent floors.
Does not invoke ``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_PATH = REPO_ROOT / "benchmarks" / "run_full_reval_bench.py"
NIGHTLY_N_POSITIONS = 100
NIGHTLY_N_OBS = 50

pytestmark = pytest.mark.skipif(
    os.environ.get("QUANTLINEAGE_NIGHTLY") != "1",
    reason="nightly-only N=100 reconstruction bench (set QUANTLINEAGE_NIGHTLY=1)",
)


def _load_bench():
    spec = importlib.util.spec_from_file_location("run_full_reval_bench", BENCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_recorded_finite(row: dict) -> None:
    for key in ("wall_ms", "wall_ms_cold", "wall_ms_warm", "peak_rss_kib", "scenarios_per_sec"):
        assert key in row, f"missing recorded field {key}"
        assert math.isfinite(float(row[key])), f"{key} is not finite: {row[key]!r}"
    assert "throughput" not in row


def test_reconstruction_n100_records_matrix_without_sla():
    bench = _load_bench()
    recon = bench.run_reconstruction_matrix(NIGHTLY_N_POSITIONS, NIGHTLY_N_OBS)
    assert recon["n_positions"] == NIGHTLY_N_POSITIONS
    assert recon["n_obs"] == NIGHTLY_N_OBS
    assert recon["book"] == "european_option"
    assert recon["rss_isolated"] is True
    builtin = recon["builtin"]
    assert builtin["available"] is True
    assert builtin["n_positions"] == NIGHTLY_N_POSITIONS
    assert builtin["n_obs"] == NIGHTLY_N_OBS
    assert builtin["pnl_identity_ok"] is True
    assert isinstance(builtin["checksum"], str) and len(builtin["checksum"]) == 64
    _assert_recorded_finite(builtin)
    ql = recon["quantlib"]
    assert "available" in ql
    if ql["available"]:
        _assert_recorded_finite(ql)
        assert ql["n_positions"] == NIGHTLY_N_POSITIONS
        assert ql["n_obs"] == NIGHTLY_N_OBS
        assert ql["pnl_identity_ok"] is True
        assert recon["pnl_gap"]["within_option_match_rtol"] is True
    else:
        assert ql.get("skip_reason")
