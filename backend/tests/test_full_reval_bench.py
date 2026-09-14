"""R0.6.1 / R0.6.7 / R0.6.8 — full-revaluation identity + acceptance benches (not a host SLA).

Runs ``benchmarks/run_full_reval_bench.py --json`` and pins R0.6.1 ``impl``,
``n_obs``, and ``checksum``. Acceptance payload records N×S (PR-safe 10×50),
``wall_ms`` / warm vs cold, peak RSS, and scenarios/sec. Wall time and RSS
are recorded, not gated. QuantLib is skip-or-run via the hard-gate helper.

R0.6.8 adds a nested ``reconstruction`` object: European option book (not
cash equity ``quantity * spot``), identity checksum per engine, isolated
RSS via a subprocess per impl, and a recorded builtin vs QuantLib P&L gap
at the existing option-match ``rel=2e-3``. Does not invoke
``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import functools
import json
import math
import os
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

RECONSTRUCTION_N_POSITIONS = 10
RECONSTRUCTION_N_OBS = 50
OPTION_MATCH_RTOL = 2e-3

_RECORDED_NUMBER_KEYS = (
    "wall_ms",
    "wall_ms_cold",
    "wall_ms_warm",
    "peak_rss_kib",
    "scenarios_per_sec",
)


@functools.lru_cache(maxsize=1)
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


def _assert_recorded_checksum(checksum: object) -> None:
    assert isinstance(checksum, str) and len(checksum) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", checksum)


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
    assert "EuropeanOptionPosition" in text
    assert "--isolated-impl" in text


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


def test_cash_equity_identity_checksums_unchanged():
    """R0.6.1 1×120 and R0.6.7 10×50 cash-equity pins must stay put."""
    text = BENCH_PATH.read_text(encoding="utf-8")
    assert EXPECTED_CHECKSUM in text
    assert EXPECTED_ACCEPTANCE_CHECKSUM in text
    row = _run_bench_json()
    assert row["checksum"] == EXPECTED_CHECKSUM
    assert row["acceptance"]["builtin"]["checksum"] == EXPECTED_ACCEPTANCE_CHECKSUM


def test_full_reval_bench_reconstruction_is_european_option_not_cash_equity():
    text = BENCH_PATH.read_text(encoding="utf-8")
    assert "EuropeanOptionPosition" in text
    assert "equity_vols" in text
    assert "dividend_yields" in text
    row = _run_bench_json()
    recon = row["reconstruction"]
    assert recon["n_positions"] == RECONSTRUCTION_N_POSITIONS
    assert recon["n_obs"] == RECONSTRUCTION_N_OBS
    assert recon["book"] == "european_option"
    assert recon["option_match_rtol"] == OPTION_MATCH_RTOL
    builtin = recon["builtin"]
    assert builtin["impl"] == IMPL
    assert builtin["n_positions"] == RECONSTRUCTION_N_POSITIONS
    assert builtin["n_obs"] == RECONSTRUCTION_N_OBS
    assert builtin["available"] is True
    _assert_recorded_finite(builtin)
    assert builtin["pnl_identity_ok"] is True
    _assert_recorded_checksum(builtin["checksum"])
    assert builtin["checksum"] != EXPECTED_CHECKSUM
    assert builtin["checksum"] != EXPECTED_ACCEPTANCE_CHECKSUM
    assert "throughput" not in builtin
    ql = recon["quantlib"]
    assert "available" in ql
    if ql["available"]:
        _assert_recorded_finite(ql)
        assert ql["impl"] == "full_reval_quantlib"
        assert ql["n_positions"] == RECONSTRUCTION_N_POSITIONS
        assert ql["n_obs"] == RECONSTRUCTION_N_OBS
        _assert_recorded_checksum(ql["checksum"])
        assert ql["checksum"] != EXPECTED_ACCEPTANCE_CHECKSUM
        assert ql["pnl_identity_ok"] is True
        assert "throughput" not in ql
    else:
        assert ql.get("skip_reason")


def test_full_reval_bench_reconstruction_rss_is_isolated_per_impl():
    text = BENCH_PATH.read_text(encoding="utf-8")
    assert "subprocess" in text
    assert "--isolated-impl" in text
    row = _run_bench_json()
    recon = row["reconstruction"]
    assert recon["rss_isolated"] is True
    builtin = recon["builtin"]
    assert builtin["rss_isolated"] is True
    assert "peak_rss_kib" in builtin
    assert math.isfinite(float(builtin["peak_rss_kib"]))
    ql = recon["quantlib"]
    if ql.get("available"):
        assert ql["rss_isolated"] is True
        assert math.isfinite(float(ql["peak_rss_kib"]))
        assert builtin.get("rss_pid") != ql.get("rss_pid")


def test_full_reval_bench_reconstruction_records_pnl_gap():
    from tests.quantlib_gate import import_quantlib

    import_quantlib()
    row = _run_bench_json()
    recon = row["reconstruction"]
    ql = recon["quantlib"]
    builtin = recon["builtin"]
    assert ql["available"] is True
    gap = recon["pnl_gap"]
    assert math.isfinite(float(gap["max_abs"]))
    assert math.isfinite(float(gap["max_rel"]))
    assert gap["rtol"] == OPTION_MATCH_RTOL
    assert gap["within_option_match_rtol"] is True
    _assert_recorded_checksum(builtin["checksum"])
    _assert_recorded_checksum(ql["checksum"])


def test_full_reval_n100_is_skipped_unless_nightly(monkeypatch):
    """N=100×50 must not run in default PR (skip unless QUANTLINEAGE_NIGHTLY=1)."""
    path = REPO_ROOT / "backend" / "tests" / "test_nightly_full_reval_n100.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "QUANTLINEAGE_NIGHTLY" in text
    assert "skipif" in text
    assert "100" in text
    assert "50" in text
    monkeypatch.delenv("QUANTLINEAGE_NIGHTLY", raising=False)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            str(path),
        ],
        cwd=str(REPO_ROOT / "backend"),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": "."},
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert re.search(r"skipped", combined, re.I), combined
    assert not re.search(r"(?m)^[0-9]+ failed", combined)
