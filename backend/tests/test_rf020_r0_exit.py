"""Leftover-wave honesty pins.

P0/P1 code findings stay CLOSED except RF-014 shared ACLs/TLS (reopened).
RF-017 is CLOSED as MET for ABI (not ACCEPTED / DEFERRED); product Historical
VaR stays Python/NumPy by design.
RF-018 is CLOSED as MET (OpenAPI snapshot + request-boundary units; not a TS rewrite).
RF-019 is CLOSED as MET (JSON-schema allowlist + injection/ambiguity evals).
Do not claim Milestone R0 COMPLETE until remaining leftovers are MET.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FINDINGS = REPO_ROOT / "reviews" / "FINDINGS.md"
MILESTONE = REPO_ROOT / "reviews" / "REMEDIATION_MILESTONE.md"
ROADMAP = REPO_ROOT / "ROADMAP.md"

CLOSED_P0_P1 = [f"RF-{n:03d}" for n in range(1, 17) if n != 14]
OPEN_LEFTOVERS = ("RF-014",)


def _findings() -> str:
    return FINDINGS.read_text(encoding="utf-8")


def _finding_section(text: str, rf_id: str) -> str:
    start = text.index(f"## {rf_id}")
    nxt = text.find("\n## RF-", start + 1)
    if nxt == -1:
        nxt = text.find("\n# Priority Backlog", start + 1)
    assert nxt != -1, f"could not bound {rf_id}"
    return text[start:nxt]


def _status_line(section: str) -> str:
    for line in section.splitlines():
        if line.startswith("Status:"):
            return line
    raise AssertionError("missing Status: line")


def test_findings_header_does_not_claim_r0_complete_while_leftovers_open():
    header = _findings().split("# Executive Summary", 1)[0]
    assert "IN PROGRESS" in header
    assert "Milestone R0 COMPLETE" not in header


def test_closed_p0_p1_except_rf014_remain_closed():
    text = _findings()
    for rf_id in CLOSED_P0_P1:
        section = _finding_section(text, rf_id)
        assert "Status: **CLOSED**" in section, rf_id


def test_leftover_findings_are_in_progress_not_accepted_deferred():
    text = _findings()
    for rf_id in OPEN_LEFTOVERS:
        status = _status_line(_finding_section(text, rf_id))
        assert "IN PROGRESS" in status, rf_id
        assert "ACCEPTED / DEFERRED" not in status, rf_id


def test_rf018_frontend_contracts_closed():
    """RF-018 MET without a TypeScript rewrite: pins, npm ci, OpenAPI, wire units."""
    assert "RF-018" not in OPEN_LEFTOVERS
    section = _finding_section(_findings(), "RF-018")
    status = _status_line(section)
    assert "Status: **CLOSED**" in section
    assert "IN PROGRESS" not in status
    assert "ACCEPTED / DEFERRED" not in status
    assert "TypeScript rewrite" in section or "TS rewrite" in section or "not a TypeScript" in section.lower()


def test_rf017_closed_as_met_abi_not_accepted_deferred():
    """RF-017 ABI/validation/contiguous buffers are MET; not a C++ VaR deferral."""
    section = _finding_section(_findings(), "RF-017")
    status = _status_line(section)
    assert "Status: **CLOSED**" in section
    assert "IN PROGRESS" not in status
    assert "ACCEPTED / DEFERRED" not in status
    assert "**MET**" in section
    assert "by design" in section
    assert "python/NumPy" in section or "Python/NumPy" in section

def test_rf019_is_closed_and_not_an_open_leftover():
    assert "RF-019" not in OPEN_LEFTOVERS
    status = _status_line(_finding_section(_findings(), "RF-019"))
    assert "CLOSED" in status
    assert "IN PROGRESS" not in status
    assert "ACCEPTED / DEFERRED" not in status


def test_roadmap_does_not_claim_complete_while_leftovers_open():
    gate = ROADMAP.read_text(encoding="utf-8").split("## Progress", 1)[0]
    assert "IN PROGRESS" in gate or "leftover" in gate.lower()


def test_milestone_header_not_complete_while_leftovers_open():
    head = "\n".join(MILESTONE.read_text(encoding="utf-8").splitlines()[:12])
    assert "IN PROGRESS" in head
