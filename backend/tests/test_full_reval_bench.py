"""R0.6.1 / R0.6.7 — full-revaluation identity + acceptance benches (not a host SLA).

Runs ``benchmarks/run_full_reval_bench.py --json`` and pins R0.6.1 ``impl``,
``n_obs``, and ``checksum``. Acceptance payload records N×S (PR-safe 10×50),
``wall_ms`` / warm vs cold, peak RSS, and scenarios/sec. Wall time and RSS
are recorded, not gated. QuantLib is skip-or-run via the hard-gate helper.
Does not invoke ``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_PATH = REPO_ROOT / "benchmarks" / "run_full_reval_bench.py"

N_OBS = 120
IMPL = "full_reval_builtin"
# Engine P&L checksum (allclose 1e-12 to 10 * 100 * linspace(-0.05, 0.05, 120)).
EXPECTED_CHECKSUM = "6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f"

ACCEPTANCE_N_POSITIONS = 10
ACCEPTANCE_N_OBS = 50
# Engine P&L checksum for 10×UNIT equity × linspace(-0.05, 0.05, 50).
EXPECTED_ACCEPTANCE_CHECKSUM = "a28cf4ee6199bf40da3f2598f4241fc85fa4adc4f86bccbbd97e4938047d7537"

_RECORDED_NUMBER_KEYS = (
    "wall_ms",
    "wall_ms_cold",
    "wall_ms_warm",
    "peak_rss_kib",
    "scenarios_per_sec",
)


def _run_bench_json() -> dict:
    proc = subprocess.run(
        [sys.executable, str(BENCH_PATH), "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _assert_recorded_finite(row: dict) -> None:
    for key in _RECORDED_NUMBER_KEYS:
        assert key in row, f"missing recorded field {key}"
        value = row[key]
        assert isinstance(value, (int, float)), f"{key} is not a number: {value!r}"
        assert math.isfinite(float(value)), f"{key} is not finite: {value!r}"
    assert "throughput" not in row


def test_full_reval_bench_emits_identity_json():
    row = _run_bench_json()
    assert row["impl"] == IMPL
    assert row["n_obs"] == N_OBS
    assert row["n_positions"] == 1
    assert row["checksum"] == EXPECTED_CHECKSUM
    assert "wall_ms" in row
    assert isinstance(row["wall_ms"], (int, float))
    assert math.isfinite(float(row["wall_ms"]))
    assert "throughput" not in row


def test_full_reval_bench_script_is_identity_not_sla():
    text = BENCH_PATH.read_text(encoding="utf-8")
    assert BENCH_PATH.is_file()
    assert "full_revaluation_pnl_series" in text
    assert "checksum" in text
    assert "n_obs" in text
    assert not re.search(r"(?m)^\s*(import |from ).*check_m6_sla", text)
    assert not re.search(r"check_m6_sla\.py\s", text)
    assert not re.search(r"throughput\s*>\s*0", text)
    assert not re.search(r"wall_ms\s*[><]=?\s*\d", text)
    assert not re.search(r"peak_rss_kib\s*[><]=?\s*\d", text)
    assert not re.search(r"scenarios_per_sec\s*[><]=?\s*\d", text)
    assert EXPECTED_CHECKSUM in text
    assert EXPECTED_ACCEPTANCE_CHECKSUM in text


def test_full_reval_bench_acceptance_records_matrix_without_sla():
    row = _run_bench_json()
    acc = row["acceptance"]
    assert acc["n_positions"] == ACCEPTANCE_N_POSITIONS
    assert acc["n_obs"] == ACCEPTANCE_N_OBS
    assert acc["n_positions"] * acc["n_obs"] > 1 * 120
    builtin = acc["builtin"]
    assert builtin["impl"] == IMPL
    assert builtin["n_positions"] == ACCEPTANCE_N_POSITIONS
    assert builtin["n_obs"] == ACCEPTANCE_N_OBS
    _assert_recorded_finite(builtin)
    assert builtin["pnl_identity_ok"] is True
    assert builtin["checksum"] == EXPECTED_ACCEPTANCE_CHECKSUM
    assert "quantlib" in acc
    ql = acc["quantlib"]
    assert "available" in ql
    if ql["available"]:
        _assert_recorded_finite(ql)
        assert ql["n_positions"] == ACCEPTANCE_N_POSITIONS
        assert ql["n_obs"] == ACCEPTANCE_N_OBS
        assert ql["checksum"] == EXPECTED_ACCEPTANCE_CHECKSUM
        assert ql["pnl_identity_ok"] is True
    else:
        assert ql.get("skip_reason")


def test_full_reval_bench_quantlib_same_nxs():
    from tests.quantlib_gate import import_quantlib

    import_quantlib()
    row = _run_bench_json()
    ql = row["acceptance"]["quantlib"]
    builtin = row["acceptance"]["builtin"]
    assert ql["available"] is True
    assert ql["impl"] == "full_reval_quantlib"
    assert ql["n_positions"] == builtin["n_positions"] == ACCEPTANCE_N_POSITIONS
    assert ql["n_obs"] == builtin["n_obs"] == ACCEPTANCE_N_OBS
    _assert_recorded_finite(ql)
    assert ql["checksum"] == builtin["checksum"] == EXPECTED_ACCEPTANCE_CHECKSUM
    assert ql["pnl_identity_ok"] is True
    assert "throughput" not in ql
