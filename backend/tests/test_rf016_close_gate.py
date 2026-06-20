"""R0.12.7 / RF-016 — close-gate residual pins.

PR-FULL QuantLib remains a hard gate (cannot skip-green). Labeled-runner
SLA-K1/K2 is an accepted residual (not MET). QA-024 demo-artifact range is
MET via the QuantLib band gate. Do not invent ubuntu-latest SLA floors.
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
    leftover = "QA-024 demo-artifact range check remains a leftover residual"
    assert leftover not in section
    assert "QA-024 demo-artifact range check is **MET**" in section
    assert 'cannot produce a green "full" CI run' in section
    assert "A broken QuantLib installation cannot produce a green" in section


def test_milestone_r0127_records_accepted_labeled_runner_residual():
    text = MILESTONE.read_text(encoding="utf-8")
    assert "## R0.12.7" in text
    assert "accepted residual" in text
    assert "no labeled runner" in text
    assert "SLA-K1/K2 not CI-enforced" in text
    assert "check_m6_sla.py" in text
    assert "ubuntu-latest" in text


def test_milestone_r0128_records_qa024_range_met():
    text = MILESTONE.read_text(encoding="utf-8")
    assert "## R0.12.8" in text
    assert "QA-024 demo-artifact range check is **MET**" in text
    leftover = "QA-024 demo-artifact range check remains a leftover residual"
    r0128 = text.split("## R0.12.8", 1)[1]
    nxt = r0128.find("\n## ")
    section = r0128 if nxt == -1 else r0128[:nxt]
    assert leftover not in section
    assert "labeled-runner SLA" in section.lower() or "SLA-K1/K2" in section
    assert "not MET" in section
    assert "check_m6_sla.py" in section
    assert "Milestone R0 COMPLETE" not in section
