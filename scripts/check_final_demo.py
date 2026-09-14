#!/usr/bin/env python3
"""M13 final-demo clean-checkout smoke.

This check intentionally reuses the deterministic M10 demo data/script path:
demo portfolios + packaged historical factors + builtin pricing + Python
scenario kernel. It validates artifact generation only; it does not launch the
browser UI or invent expected risk numbers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


REQUIRED_PATHS = (
    "README.md",
    "ROADMAP.md",
    "data/demo_historical_factors.csv",
    "data/demo_multi_factor_history.csv",
    "data/demo_risk_artifact.json",
    "docs/demo/final_demo.md",
    "docs/demo/quantlineage_demo_01_overview.png",
    "docs/demo/quantlineage_demo_02_portfolio.png",
    "docs/demo/quantlineage_demo_03_var_es.png",
    "docs/demo/quantlineage_demo_04_stress.png",
    "backend/app/demo/run_demo_risk.py",
    "scripts/run_demo_risk.py",
)


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"required final-demo file missing: {path.relative_to(ROOT)}")


def check_final_demo(*, output: Path | None = None) -> dict[str, Any]:
    """Validate the documented final-demo artifact path from a clean checkout."""
    for relpath in REQUIRED_PATHS:
        _require_file(ROOT / relpath)

    # Force the same deterministic path documented for the final portfolio demo.
    os.environ["QUANTLINEAGE_PRICING_ENGINE"] = "builtin"
    os.environ["QUANTLINEAGE_SCENARIO_KERNEL"] = "python"
    os.environ["QUANTLINEAGE_PRICING_CACHE"] = "0"
    os.environ["QUANTLINEAGE_CURVE_CACHE"] = "0"
    os.environ["QUANTLINEAGE_SCENARIO_CACHE"] = "0"

    from app.demo.run_demo_risk import run_demo_risk
    from app.risk.historical_data import DEMO_MULTI_FACTOR_DATASET_ID
    from app.risk.stress import DEFAULT_SCENARIOS
    from app.sample import DEMO_PORTFOLIOS

    tempdir: tempfile.TemporaryDirectory[str] | None = None
    try:
        if output is None:
            tempdir = tempfile.TemporaryDirectory(prefix="quantlineage-final-demo-")
            artifact_path = Path(tempdir.name) / "demo_risk_artifact.json"
        else:
            artifact_path = output
        artifact = run_demo_risk(output=artifact_path, check=True)
        _require_file(artifact_path)

        golden_path = ROOT / "data" / "demo_risk_artifact.json"
        generated = artifact_path.read_text(encoding="utf-8")
        golden = golden_path.read_text(encoding="utf-8")
        if generated != golden:
            raise RuntimeError(
                "generated final-demo artifact does not match data/demo_risk_artifact.json"
            )
    finally:
        if tempdir is not None:
            tempdir.cleanup()

    portfolio_ids = [book["id"] for book in artifact["portfolios"]]
    expected_ids = [portfolio.id for portfolio in DEMO_PORTFOLIOS]
    if portfolio_ids != expected_ids:
        raise RuntimeError(f"demo portfolio order changed: got {portfolio_ids}, want {expected_ids}")

    scenario_ids = artifact["scenario_set"]
    expected_scenarios = [scenario.id or scenario.name for scenario in DEFAULT_SCENARIOS]
    if scenario_ids != expected_scenarios:
        raise RuntimeError(f"demo scenario set changed: got {scenario_ids}, want {expected_scenarios}")

    if artifact["historical_dataset"] != DEMO_MULTI_FACTOR_DATASET_ID:
        raise RuntimeError(
            f"demo historical dataset changed: got {artifact['historical_dataset']!r}, "
            f"want {DEMO_MULTI_FACTOR_DATASET_ID!r}"
        )

    return {
        "status": "ok",
        "artifact": str(artifact_path) if output is not None else "temporary",
        "golden": str(golden_path),
        "portfolio_ids": portfolio_ids,
        "scenario_count": len(scenario_ids),
        "pricing_engine": artifact["pricing_engine"],
        "historical_dataset": artifact["historical_dataset"],
        "methodology": artifact["methodology"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "M13.1/M13.3: verify final-demo prerequisites and deterministic "
            "M10 demo risk artifact generation."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Optional path for the generated artifact; default uses a temporary directory.",
    )
    args = parser.parse_args(argv)
    result = check_final_demo(output=args.output)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
