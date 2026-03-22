"""R0.12.2 / RF-016 — PR-FULL CI aggregator contract.

A green GitHub check whose display name contains PR-FULL must mean the
production-relevant jobs have all succeeded. This job is a needs:
aggregator; it must not re-run pytest. The QuantLib hard-gate (R0.1.6)
must remain a separate mandatory job with RISKFORGE_REQUIRE_QUANTLIB.
This is not nightly (R0.12.4) and not native ABI (R0.12.5).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_NEEDS = (
    "backend",
    "backend-quantlib",
    "frontend",
    "lint",
    "e2e",
    "postgres-smoke",
)


def _workflow_text() -> str:
    return CI_YML.read_text(encoding="utf-8")


def _job_block(text: str, job_key: str) -> str:
    pattern = rf"(?ms)^  {re.escape(job_key)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)"
    match = re.search(pattern, text)
    assert match, f"CI job {job_key!r} missing from .github/workflows/ci.yml"
    return match.group(0)


def _needs_ids(block: str) -> set[str]:
    inline = re.search(r"needs:\s*\[([^\]]+)\]", block)
    if inline:
        return {
            part.strip().strip("'\"")
            for part in inline.group(1).split(",")
            if part.strip()
        }
    listed = re.search(r"(?m)^    needs:\n((?:      - \S+\n)+)", block)
    if listed:
        return set(re.findall(r"^      - (\S+)", listed.group(1), re.M))
    raise AssertionError("PR-FULL job must declare needs:")


def test_pr_full_job_name_is_explicit():
    text = _workflow_text()
    block = _job_block(text, "pr-full")
    assert re.search(r"(?i)name:\s*.*pr-full", block), (
        "job pr-full must have a display name containing PR-FULL"
    )


def test_pr_full_needs_production_relevant_jobs():
    block = _job_block(_workflow_text(), "pr-full")
    needed = _needs_ids(block)
    missing = [job_id for job_id in REQUIRED_NEEDS if job_id not in needed]
    assert not missing, f"PR-FULL needs: must include {missing}; found {sorted(needed)}"
    extra = needed - set(REQUIRED_NEEDS)
    assert not extra, f"PR-FULL needs: must stay the six PR jobs; extra {sorted(extra)}"
    assert "quantlib-e2e" not in needed
    assert "hierarchy-benchmark" not in needed


def test_quantlib_hard_gate_still_requires_quantlib():
    text = _workflow_text()
    assert "name: backend-quantlib-hard-gate" in text
    block = _job_block(text, "backend-quantlib")
    assert "RISKFORGE_REQUIRE_QUANTLIB" in block
    assert "RISKFORGE_PRICING_ENGINE: quantlib" in block
    assert "requirements-no-ql" not in block
