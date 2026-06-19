"""M13.1/M13.3 final-demo deterministic setup and clean-checkout smoke."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_final_demo_check():
    script = ROOT / "scripts" / "check_final_demo.py"
    spec = importlib.util.spec_from_file_location("check_final_demo", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_final_demo_check_validates_committed_artifact(tmp_path: Path):
    module = _load_final_demo_check()
    output = tmp_path / "demo_risk_artifact.json"

    result = module.check_final_demo(output=output)

    assert result["status"] == "ok"
    assert result["artifact"] == str(output)
    assert result["portfolio_ids"] == ["equity-vol", "rates-macro", "global-macro"]
    assert result["pricing_engine"] == "builtin"
    assert result["historical_dataset"] == "demo-multi-factor-history"
    assert result["methodology"] == "DELTA_GAMMA"
    assert result["scenario_count"] == 5
    assert output.read_text(encoding="utf-8") == (
        ROOT / "data" / "demo_risk_artifact.json"
    ).read_text(encoding="utf-8")
