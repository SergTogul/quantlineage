"""Stage 10.3 FULL_REVALUATION matrix harness gates (not an HTTP / kernel SLA).

CI-safe smoke is tiny N×S. Parity and reproduction run on the same fixture.
Does not invoke ``benchmarks/check_m6_sla.py``. Wall time is recorded, not floored.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_PATH = REPO_ROOT / "benchmarks" / "full_reval_stage103.py"
BENCH_PATH = REPO_ROOT / "benchmarks" / "run_full_reval_bench.py"

SMOKE_N_TRADES = 4
SMOKE_N_SCENARIOS = 8
SEED = 103
OPTION_MATCH_RTOL = 2e-3

_RECORDED_NUMBER_KEYS = (
    "wall_ms",
    "wall_ms_cold",
    "wall_ms_warm",
    "peak_rss_kib",
    "scenarios_per_sec",
)


def _load_stage():
    spec = importlib.util.spec_from_file_location("full_reval_stage103", STAGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stage103_harness_module_exists():
    assert STAGE_PATH.is_file()
    text = STAGE_PATH.read_text(encoding="utf-8")
    assert "FULL_REVALUATION" in text
    assert "create_synthetic_factor_panel" in text or "synthetic" in text.lower()
    assert not re.search(r"(?m)^\s*(import |from ).*check_m6_sla", text)
    assert not re.search(r"check_m6_sla\.py\s", text)
    assert not re.search(r"wall_ms\s*[><]=?\s*\d", text)
    assert not re.search(r"scenarios_per_sec\s*[><]=?\s*\d", text)


def test_stage103_smoke_records_matrix_fields_without_sla():
    stage = _load_stage()
    payload = stage.run_smoke()
    assert payload["n_trades"] == SMOKE_N_TRADES
    assert payload["n_scenarios"] == SMOKE_N_SCENARIOS
    assert payload["seed"] == SEED
    assert payload["methodology"] == "FULL_REVALUATION"
    builtin = payload["builtin"]
    assert builtin["available"] is True
    assert builtin["engine"] == "builtin"
    assert builtin["worker_count"] == 1
    assert builtin["cache_state"] == "valuation_lru_bypassed"
    for key in _RECORDED_NUMBER_KEYS:
        assert math.isfinite(float(builtin[key])), key
    assert re.fullmatch(r"[0-9a-f]{64}", builtin["checksum"])
    assert "throughput" not in builtin
    assert "environment" in payload
    env = payload["environment"]
    for field in ("platform", "python", "machine", "logical_cpus"):
        assert field in env
    assert "sla" not in json.dumps(payload).lower() or "not" in json.dumps(payload).lower()
    phases = payload["profile"]
    for name in (
        "scenario_construction_ms",
        "snapshot_transform_ms",
        "engine_construction_ms",
        "pricing_ms",
        "persistence_ms",
        "aggregation_ms",
    ):
        assert math.isfinite(float(phases[name])), name
    assert float(phases["persistence_ms"]) == 0.0


def test_stage103_full_reval_differs_from_linear_on_option_book():
    stage = _load_stage()
    workload = stage.build_multi_asset_workload(SMOKE_N_TRADES, SMOKE_N_SCENARIOS, seed=SEED)
    assert any(getattr(p, "type", None) == "european_option" for p in workload.portfolio.positions)
    full = stage.run_methodology_cell(
        workload, methodology="FULL_REVALUATION", engine_name="builtin"
    )
    linear = stage.run_methodology_cell(
        workload, methodology="LINEAR", engine_name="builtin"
    )
    assert full["checksum"] != linear["checksum"]
    assert not np.allclose(full["pnl"], linear["pnl"], rtol=1e-4, atol=1e-6)


def test_stage103_same_seed_reproduces_checksum():
    stage = _load_stage()
    first = stage.run_smoke()
    second = stage.run_smoke()
    assert first["builtin"]["checksum"] == second["builtin"]["checksum"]
    other_seed = stage.build_multi_asset_workload(SMOKE_N_TRADES, SMOKE_N_SCENARIOS, seed=SEED + 1)
    other = stage.run_methodology_cell(
        other_seed, methodology="FULL_REVALUATION", engine_name="builtin"
    )
    assert other["checksum"] != first["builtin"]["checksum"]


def test_stage103_parity_gate_tiny_fixture():
    from tests.quantlib_gate import import_quantlib

    import_quantlib()
    stage = _load_stage()
    payload = stage.run_parity_gate(
        n_trades=SMOKE_N_TRADES, n_scenarios=SMOKE_N_SCENARIOS, seed=SEED
    )
    assert payload["rtol"] == OPTION_MATCH_RTOL
    assert payload["within_tolerance"] is True
    assert math.isfinite(float(payload["max_rel"]))
    assert math.isfinite(float(payload["max_abs"]))
    assert payload["builtin_checksum"] != payload["quantlib_checksum"] or payload["max_abs"] == 0.0
    assert re.fullmatch(r"[0-9a-f]{64}", payload["builtin_checksum"])
    assert re.fullmatch(r"[0-9a-f]{64}", payload["quantlib_checksum"])


def test_stage103_cli_emits_json_csv_markdown(tmp_path):
    csv_path = tmp_path / "stage103.csv"
    md_path = tmp_path / "stage103.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(BENCH_PATH),
            "--stage103",
            "--smoke",
            "--json",
            "--csv",
            str(csv_path),
            "--markdown",
            str(md_path),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["kind"] == "stage103_smoke"
    assert payload["n_trades"] == SMOKE_N_TRADES
    assert csv_path.is_file()
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert rows
    assert "checksum" in rows[0]
    assert "methodology" in rows[0]
    md = md_path.read_text(encoding="utf-8")
    assert "FULL_REVALUATION" in md
    assert "not an http sla" in md.lower() or "not a host sla" in md.lower()
    assert "SLA-K1" in md
    assert "unchanged" in md.lower() or "post-R0" in md or "post-r0" in md.lower()
