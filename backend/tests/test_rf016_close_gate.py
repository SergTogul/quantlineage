"""R0.12.7 / RF-016 — close-gate residual pins.

PR-FULL QuantLib remains a hard gate (cannot skip-green). Labeled-runner
SLA-K1/K2 and QA-024 demo-artifact range are accepted residuals (not MET).
Do not invent ubuntu-latest SLA floors or a fake QuantLib range gate.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FINDINGS = REPO_ROOT / "reviews" / "FINDINGS.md"
MILESTONE = REPO_ROOT / "reviews" / "REMEDIATION_MILESTONE.md"


def _rf016_section() -> str:
    text = FINDINGS.read_text(encoding="utf-8")
    start = text.index("## RF-016")
    end = text.index("## RF-017")
    return text[start:end]


def test_findings_rf016_closed_with_named_accepted_residuals():
    section = _rf016_section()
    assert "Status: **CLOSED**" in section
    assert "accepted residual" in section
    assert "no labeled runner" in section
    assert "SLA-K1/K2 not CI-enforced" in section
    assert (
        "Labeled-runner SLA-K1/K2 is an **accepted residual** (not MET)"
        in section
    )
    assert (
        "QA-024 demo-artifact range check remains a leftover residual (not MET)"
        in section
    )
    assert 'cannot produce a green "full" CI run' in section
    assert "A broken QuantLib installation cannot produce a green" in section


def test_milestone_r0127_records_accepted_labeled_runner_residual():
    text = MILESTONE.read_text(encoding="utf-8")
    assert "## R0.12.7" in text
    assert "accepted residual" in text
    assert "no labeled runner" in text
    assert "SLA-K1/K2 not CI-enforced" in text
    assert "QA-024" in text
    assert "check_m6_sla.py" in text
    assert "ubuntu-latest" in text
