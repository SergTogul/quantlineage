"""R0.12.4 nightly — hierarchy identity (checksum / nodes / MV), not a host SLA.

Skipped unless ``RISKFORGE_NIGHTLY=1`` so PR-FAST / backend-pytest stay fast.
Does not change pricing engines or risk formulas. Does not invoke
``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_PATH = REPO_ROOT / "benchmarks" / "run_hierarchy_bench.py"

pytestmark = pytest.mark.skipif(
    os.environ.get("RISKFORGE_NIGHTLY") != "1",
    reason="nightly-only hierarchy identity (set RISKFORGE_NIGHTLY=1)",
)


def _load_bench():
    spec = importlib.util.spec_from_file_location("run_hierarchy_bench", BENCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hierarchy_identity_checksum_and_additive():
    bench = _load_bench()
    row = bench.run_hierarchy_identity()
    assert row["impl"] == bench.IMPL
    assert row["n_positions"] == bench.EXPECTED_N_POSITIONS == 64
    assert row["n_nodes"] == bench.EXPECTED_N_NODES == 94
    assert row["market_value"] == bench.EXPECTED_MARKET_VALUE == 64000.0
    assert row["additive_ok"] is True
    assert row["checksum"] == bench.EXPECTED_CHECKSUM
    assert "throughput" not in row
