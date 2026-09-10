"""QA-024 — QuantLib demo-artifact range gate.

Prices the three demo books with QuantLib and compares ``var_99``,
``market_value``, and named stress P&Ls to ``data/demo_risk_artifact.json``
bands. Builtin golden is not bit-identical for swaps/QL. Market value and
named stress P&Ls use relative 25% with a $1 abs floor; ``var_99`` uses
``[0.25×, 4×]`` of the builtin artifact (see ``docs/demo/final_demo.md``).

Skip-unless-QuantLib locally. Nightly / ``RISKFORGE_REQUIRE_QUANTLIB``
fail-closes via ``require_quantlib_for_nightly``. Do not treat this as a
labeled-runner SLA or run ``check_m6_sla.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.quantlib_gate import require_quantlib_for_nightly

from app.demo.run_demo_risk import build_demo_risk_artifact, default_artifact_path

REPO_ROOT = Path(__file__).resolve().parents[2]
FINAL_DEMO = REPO_ROOT / "docs" / "demo" / "final_demo.md"
NIGHTLY_YML = REPO_ROOT / ".github" / "workflows" / "nightly.yml"

DEMO_QL_RELATIVE_BAND = 0.25
DEMO_QL_ABS_FLOOR = 1.0
# Swap DV01 / curve conventions move historical VaR more than NPV. Builtin
# rates-macro 99% VaR is ~2.9× smaller than QuantLib on this demo book.
VAR_99_MIN_RATIO = 0.25
VAR_99_MAX_RATIO = 4.0


def demo_ql_band_tol(reference: float, *, rel: float = DEMO_QL_RELATIVE_BAND) -> float:
    return max(rel * abs(reference), DEMO_QL_ABS_FLOOR)


def within_demo_ql_band(
    actual: float, reference: float, *, rel: float = DEMO_QL_RELATIVE_BAND
) -> bool:
    return abs(actual - reference) <= demo_ql_band_tol(reference, rel=rel)


def within_var_99_band(actual: float, reference: float) -> bool:
    if actual < 0 or reference < 0:
        return False
    if reference <= DEMO_QL_ABS_FLOOR:
        return abs(actual - reference) <= DEMO_QL_ABS_FLOOR
    return VAR_99_MIN_RATIO * reference <= actual <= VAR_99_MAX_RATIO * reference


def test_band_allows_relative_25_percent():
    assert within_demo_ql_band(125.0, 100.0)
    assert within_demo_ql_band(75.0, 100.0)
    assert not within_demo_ql_band(126.0, 100.0)
    assert not within_demo_ql_band(74.0, 100.0)


def test_band_uses_abs_floor_when_reference_is_zero():
    assert within_demo_ql_band(0.5, 0.0)
    assert within_demo_ql_band(-1.0, 0.0)
    assert not within_demo_ql_band(1.01, 0.0)


def test_var_99_band_allows_observed_swap_ratio_not_collapse_or_blowup():
    # rates-macro observed ~2.9×; still reject 5× and a 5× collapse.
    assert within_var_99_band(2.9 * 11585.0, 11585.0)
    assert within_var_99_band(0.25 * 11585.0, 11585.0)
    assert not within_var_99_band(4.1 * 11585.0, 11585.0)
    assert not within_var_99_band(0.24 * 11585.0, 11585.0)
    assert not within_var_99_band(-1.0, 11585.0)


def test_final_demo_documents_quantlib_relative_band():
    text = FINAL_DEMO.read_text(encoding="utf-8")
    assert "QuantLib" in text
    assert "25%" in text
    assert "4×" in text or "4x" in text
    assert "demo_risk_artifact.json" in text


def test_nightly_quantlib_job_runs_demo_artifact_range_pytest():
    text = NIGHTLY_YML.read_text(encoding="utf-8")
    assert "tests/test_qa024_ql_demo_range.py" in text
    assert "check_m6_sla.py" not in text.split("quantlib-e2e:", 1)[1].split(
        "hierarchy-benchmark:", 1
    )[0]


def test_quantlib_demo_books_key_numbers_within_artifact_bands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_quantlib_for_nightly()
    monkeypatch.setenv("RISKFORGE_PRICING_ENGINE", "quantlib")
    monkeypatch.setenv("RISKFORGE_SCENARIO_KERNEL", "python")
    monkeypatch.setenv("RISKFORGE_PRICING_CACHE", "0")
    monkeypatch.setenv("RISKFORGE_CURVE_CACHE", "0")
    monkeypatch.setenv("RISKFORGE_SCENARIO_CACHE", "0")

    golden_path = default_artifact_path()
    assert golden_path.is_file()
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert golden["pricing_engine"] == "builtin"

    ql_artifact = build_demo_risk_artifact()
    assert ql_artifact["pricing_engine"] == "quantlib"
    assert [book["id"] for book in ql_artifact["portfolios"]] == [
        book["id"] for book in golden["portfolios"]
    ]

    mismatches: list[str] = []
    for ql_book, ref_book in zip(
        ql_artifact["portfolios"], golden["portfolios"], strict=True
    ):
        pid = ql_book["id"]
        ql_mv = float(ql_book["summary"]["market_value"])
        ref_mv = float(ref_book["summary"]["market_value"])
        if not within_demo_ql_band(ql_mv, ref_mv):
            mismatches.append(
                f"{pid}.market_value: ql={ql_mv} builtin={ref_mv} "
                f"tol={demo_ql_band_tol(ref_mv)}"
            )
        ql_var = float(ql_book["summary"]["var_99"])
        ref_var = float(ref_book["summary"]["var_99"])
        if not within_var_99_band(ql_var, ref_var):
            mismatches.append(
                f"{pid}.var_99: ql={ql_var} builtin={ref_var} "
                f"allowed=[{VAR_99_MIN_RATIO * ref_var}, {VAR_99_MAX_RATIO * ref_var}]"
            )
        ql_stress = {row["scenario"]: float(row["pnl"]) for row in ql_book["stress"]}
        ref_stress = {row["scenario"]: float(row["pnl"]) for row in ref_book["stress"]}
        assert ql_stress.keys() == ref_stress.keys()
        for name, reference in ref_stress.items():
            actual = ql_stress[name]
            if not within_demo_ql_band(actual, reference):
                mismatches.append(
                    f"{pid}.stress[{name!r}]: ql={actual} builtin={reference} "
                    f"tol={demo_ql_band_tol(reference)}"
                )
    assert not mismatches, (
        "QuantLib demo numbers outside artifact bands:\n" + "\n".join(mismatches)
    )
