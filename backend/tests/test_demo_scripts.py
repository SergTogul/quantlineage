"""M10.3: deterministic demo risk scripts / artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.demo.run_demo_risk import (
    DEMO_ARTIFACT_FLOAT_DECIMALS,
    DEMO_ARTIFACT_SCHEMA_VERSION,
    build_demo_risk_artifact,
    default_artifact_path,
    dumps_demo_artifact,
    main,
    run_demo_risk,
)
from app.risk.historical_data import (
    DEMO_MULTI_FACTOR_DATASET_ID,
)
from app.sample import DEMO_PORTFOLIOS


@pytest.fixture(autouse=True)
def _deterministic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTLINEAGE_PRICING_ENGINE", "builtin")
    monkeypatch.setenv("QUANTLINEAGE_SCENARIO_KERNEL", "python")
    # Avoid cache wrapper nondeterminism from env toggles.
    monkeypatch.setenv("QUANTLINEAGE_PRICING_CACHE", "0")
    monkeypatch.setenv("QUANTLINEAGE_CURVE_CACHE", "0")
    monkeypatch.setenv("QUANTLINEAGE_SCENARIO_CACHE", "0")


def test_build_artifact_covers_all_demo_portfolios():
    artifact = build_demo_risk_artifact()
    assert artifact["schema_version"] == DEMO_ARTIFACT_SCHEMA_VERSION
    assert artifact["milestone"] == "M10.3"
    assert artifact["pricing_engine"] == "builtin"
    assert artifact["historical_dataset"] == DEMO_MULTI_FACTOR_DATASET_ID
    assert artifact["methodology"] == "DELTA_GAMMA"
    ids = [b["id"] for b in artifact["portfolios"]]
    assert ids == [p.id for p in DEMO_PORTFOLIOS]
    for book in artifact["portfolios"]:
        assert book["summary"]["portfolio_id"] == book["id"]
        assert book["summary"]["var_99"] >= 0
        assert book["summary"]["expected_shortfall_99"] >= book["summary"]["var_99"]
        assert len(book["stress"]) == 5
        assert all("pnl" in row and "scenario" in row for row in book["stress"])
        assert len(book["var_report"]["methods"]) >= 1


def test_artifact_byte_identical_across_reruns():
    a = dumps_demo_artifact(build_demo_risk_artifact())
    b = dumps_demo_artifact(build_demo_risk_artifact())
    assert a == b
    # Stable formatting: sorted keys + trailing newline.
    assert a.endswith("\n")
    json.loads(a)  # well-formed


def test_run_demo_risk_check_and_write(tmp_path: Path):
    out = tmp_path / "demo_risk_artifact.json"
    artifact = run_demo_risk(output=out, check=True)
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["artifact_id"] == artifact["artifact_id"]
    assert loaded == artifact or loaded == json.loads(dumps_demo_artifact(artifact))


def test_subset_portfolio_and_unknown_id():
    artifact = build_demo_risk_artifact(portfolio_ids=["rates-macro"])
    assert [b["id"] for b in artifact["portfolios"]] == ["rates-macro"]
    # Rates book: equity stress PnL is ~0 (no equity risk).
    eq_stress = next(s for s in artifact["portfolios"][0]["stress"] if s["scenario"] == "Equities -10%")
    assert abs(eq_stress["pnl"]) < 1e-9

    with pytest.raises(ValueError, match="unknown demo portfolio"):
        build_demo_risk_artifact(portfolio_ids=["not-a-book"])


def test_cli_main_stdout_and_check(capsys: pytest.CaptureFixture[str], tmp_path: Path):
    rc = main(["--check", "--portfolio", "equity-vol"])
    assert rc == 0
    printed = capsys.readouterr().out
    payload = json.loads(printed)
    assert payload["portfolios"][0]["id"] == "equity-vol"

    out = tmp_path / "out.json"
    rc = main(["--check", "-o", str(out), "--portfolio", "global-macro"])
    assert rc == 0
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8"))["portfolios"][0]["id"] == "global-macro"


def test_committed_artifact_matches_rebuild():
    """Frozen ``data/demo_risk_artifact.json`` matches a fresh builtin rebuild."""
    golden = default_artifact_path()
    assert golden.is_file(), "expected committed M10.3 artifact under data/"
    rebuilt = dumps_demo_artifact(build_demo_risk_artifact())
    assert golden.read_text(encoding="utf-8") == rebuilt


def test_stabilize_floats_collapses_platform_ulp():
    """Known CI ULP pairs must dump identically after rounding."""
    left = {
        "pnl": 4861.095921907545,
        "nested": [-85855.66340861515, 105124.17243726869],
    }
    right = {
        "pnl": 4861.095921907533,
        "nested": [-85855.66340861516, 105124.17243726872],
    }
    assert dumps_demo_artifact(left) == dumps_demo_artifact(right)
    assert DEMO_ARTIFACT_FLOAT_DECIMALS == 8


def test_scripts_entrypoint_importable():
    """Repo ``scripts/run_demo_risk.py`` remains a thin path shim."""
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "run_demo_risk.py"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "app.demo.run_demo_risk" in text
