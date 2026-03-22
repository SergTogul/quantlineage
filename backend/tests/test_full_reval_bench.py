"""R0.6.1 — full-revaluation baseline bench emits identity JSON (not a host SLA).

Runs ``benchmarks/run_full_reval_bench.py --json`` and pins ``impl``,
``n_obs``, and ``checksum``. Wall time is recorded, not gated.
Does not invoke ``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import json
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


def test_full_reval_bench_emits_identity_json():
    proc = subprocess.run(
        [sys.executable, str(BENCH_PATH), "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    row = json.loads(proc.stdout)
    assert row["impl"] == IMPL
    assert row["n_obs"] == N_OBS
    assert row["checksum"] == EXPECTED_CHECKSUM
    assert "wall_ms" in row
    assert isinstance(row["wall_ms"], (int, float))
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
    assert EXPECTED_CHECKSUM in text
