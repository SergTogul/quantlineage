"""R0 exit honesty pins.

Milestone R0 is COMPLETE. Labeled-runner SLA-K1/K2 is post-R0 (still not
MET) — not an R0 leftover. RF-014/017/018/019 stay CLOSED as MET.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FINDINGS = REPO_ROOT / "reviews" / "FINDINGS.md"
MILESTONE = REPO_ROOT / "reviews" / "REMEDIATION_MILESTONE.md"
ROADMAP = REPO_ROOT / "ROADMAP.md"

CLOSED_P0_P1 = [f"RF-{n:03d}" for n in range(1, 17)]
OPEN_LEFTOVERS: tuple[str, ...] = ()


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


def test_findings_header_claims_r0_complete_and_sla_post_r0():
    header = _findings().split("# Executive Summary", 1)[0]
    assert "Milestone R0 COMPLETE" in header
    assert "IN PROGRESS" not in header
    assert "post-r0" in header.lower()
    assert "not MET" in header


def test_closed_p0_p1_remain_closed():
    text = _findings()
    for rf_id in CLOSED_P0_P1:
        section = _finding_section(text, rf_id)
        assert "Status: **CLOSED**" in section, rf_id


def test_open_leftovers_empty_after_r0_complete():
    assert OPEN_LEFTOVERS == ()


def test_rf014_shared_acls_tls_secrets_closed():
    """RF-014 MET: shared ACLs + TLS terminator + secrets; local demo unauthenticated."""
    section = _finding_section(_findings(), "RF-014")
    status = _status_line(section)
    assert "Status: **CLOSED**" in section
    assert "IN PROGRESS" not in status
    assert "ACCEPTED / DEFERRED" not in status
    assert "**MET**" in section
    assert "OIDC" in section or "not production OIDC" in section.lower()
    lower = section.lower()
    assert "acl" in lower
    assert "tls" in lower
    assert "secret" in lower
    assert "unauthenticated" in lower


def test_rf016_sla_is_post_r0_not_r0_gate():
    section = _finding_section(_findings(), "RF-016")
    status = _status_line(section)
    assert "Status: **CLOSED**" in section
    assert "IN PROGRESS" not in status
    assert "post-R0" in section
    assert "not MET" in section


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


def test_rf020_closed_after_r0_complete():
    status = _status_line(_finding_section(_findings(), "RF-020"))
    assert "CLOSED" in status
    assert "IN PROGRESS" not in status


def test_roadmap_current_gate_r0_complete():
    gate = ROADMAP.read_text(encoding="utf-8").split("## Progress", 1)[0]
    assert "Milestone R0 is **COMPLETE**" in gate
    assert "IN PROGRESS" not in gate
    assert "post-R0" in gate


def test_milestone_header_complete():
    head = "\n".join(MILESTONE.read_text(encoding="utf-8").splitlines()[:12])
    assert "Status: **COMPLETE**" in head
    assert "IN PROGRESS" not in head
    assert "post-R0" in head
