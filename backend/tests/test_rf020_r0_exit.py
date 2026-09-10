"""R0 exit / RF-020 — docs-honesty pins.

P0/P1 are CLOSED. Accepted residuals (RF-014 auth/ACLs/TLS, RF-016
labeled-runner SLA, QA-024 range) must not be checked as MET. RF-017 /
RF-018 / RF-019 are ACCEPTED / DEFERRED, not CLOSED as MET. ROADMAP must
not say Milestone R0 IN PROGRESS while claiming COMPLETE.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FINDINGS = REPO_ROOT / "reviews" / "FINDINGS.md"
MILESTONE = REPO_ROOT / "reviews" / "REMEDIATION_MILESTONE.md"
ROADMAP = REPO_ROOT / "ROADMAP.md"
KNOWN_LIMITATIONS = REPO_ROOT / "docs" / "known_limitations.md"

P0_P1_IDS = [f"RF-{n:03d}" for n in range(1, 17)]
P2_DEFERRED = ("RF-017", "RF-018", "RF-019")


def _findings() -> str:
    return FINDINGS.read_text(encoding="utf-8")


def _milestone() -> str:
    return MILESTONE.read_text(encoding="utf-8")


def _roadmap() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def _known() -> str:
    return KNOWN_LIMITATIONS.read_text(encoding="utf-8")


def _finding_section(text: str, rf_id: str) -> str:
    start = text.index(f"## {rf_id}")
    nxt = text.find("\n## RF-", start + 1)
    if nxt == -1:
        nxt = text.find("\n# Priority Backlog", start + 1)
    assert nxt != -1, f"could not bound {rf_id}"
    return text[start:nxt]


def _exit_checklist() -> str:
    text = _milestone()
    start = text.index("# R0 Final Exit Checklist")
    return text[start:]


def _status_line(section: str) -> str:
    for line in section.splitlines():
        if line.startswith("Status:"):
            return line
    raise AssertionError("missing Status: line")


def test_findings_header_declares_milestone_r0_complete():
    header = _findings().split("# Executive Summary", 1)[0]
    assert "Milestone R0 COMPLETE" in header
    assert "R0 IN PROGRESS" not in header


def test_findings_rf020_closed_with_dated_count_disclaimer():
    section = _finding_section(_findings(), "RF-020")
    assert "Status: **CLOSED**" in section
    assert "IN PROGRESS" not in _status_line(section)
    assert "not a live" in section.lower() or "not re-run" in section.lower()
    assert "FINDINGS" in section
    assert "known_limitations" in section


def test_p2_findings_are_accepted_deferred_not_closed_as_met():
    text = _findings()
    for rf_id in P2_DEFERRED:
        section = _finding_section(text, rf_id)
        status = _status_line(section)
        assert "ACCEPTED / DEFERRED" in status, rf_id
        assert "Status: **CLOSED**" not in section, rf_id


def test_all_p0_and_p1_findings_are_closed():
    text = _findings()
    for rf_id in P0_P1_IDS:
        section = _finding_section(text, rf_id)
        assert "Status: **CLOSED**" in section, rf_id


def test_roadmap_current_gate_says_r0_complete_not_in_progress():
    text = _roadmap()
    gate = text.split("## Progress", 1)[0]
    assert "Milestone R0" in gate
    assert "**COMPLETE**" in gate
    assert "**IN PROGRESS**" not in gate
    assert "not re-run" in gate.lower() or "not a live" in gate.lower()


def test_roadmap_does_not_claim_complete_while_in_progress():
    text = _roadmap()
    progress = text.split("## Progress", 1)[1].split("Workstream 0", 1)[0]
    assert "Milestone R0" in progress
    assert "**IN PROGRESS**" not in progress
    assert "**COMPLETE**" in progress


def test_milestone_status_complete_and_checklist_distinguishes_residuals():
    text = _milestone()
    head = "\n".join(text.splitlines()[:12])
    assert "Status: **COMPLETE**" in head
    assert "IN PROGRESS" not in head
    checklist = _exit_checklist()
    assert "accepted residual, not MET" in checklist or "accepted residual (not MET)" in checklist
    assert "[~]" in checklist


def test_accepted_residuals_are_not_checked_as_met():
    checklist = _exit_checklist()
    residual_needles = (
        "shared deployment requires auth/authorization",
        "labeled-runner SLA",
        "QA-024",
    )
    for needle in residual_needles:
        assert needle in checklist, needle
        for line in checklist.splitlines():
            if needle in line:
                assert line.lstrip().startswith("[~]") or line.lstrip().startswith("- [~]"), line
                assert "[x]" not in line
                break


def test_known_limitations_name_r0_accepted_residuals():
    text = _known()
    lower = text.lower()
    assert "rf-014" in lower
    assert "acl" in lower or "authorization" in lower
    assert "tls" in lower
    assert "labeled-runner" in lower or "labeled runner" in lower
    assert "sla-k1" in lower and "sla-k2" in lower
    assert "qa-024" in lower
    assert "not met" in lower
    assert "rf-017" in lower
    assert "rf-018" in lower
    assert "rf-019" in lower


def test_findings_release_gate_matches_r0_complete():
    text = _findings()
    gate = text.split("# Release / Development Gate", 1)[1]
    assert "Milestone R0 COMPLETE" in gate or "Milestone R0** is complete" in gate
    assert re.search(r"paused until \*\*Milestone R0\*\* is complete", gate) is None
