"""R0.12.1 / RF-016 — PR-FAST CI job contract.

A green GitHub check named PR-FAST must mean deterministic goldens + frontend
unit/lint actually ran. This is not PR-FULL. The QuantLib hard-gate (R0.1.6)
must remain a separate mandatory job.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_BACKEND_TESTS = (
    "tests/test_var_es_golden.py",
    "tests/test_approx_pnl_units_golden.py",
    "tests/test_full_reval_golden.py",
    "tests/test_pricing.py",
    "tests/test_quant_properties.py",
)


def _workflow_text() -> str:
    return CI_YML.read_text(encoding="utf-8")


def _job_block(text: str, job_key: str) -> str:
    pattern = rf"(?ms)^  {re.escape(job_key)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)"
    match = re.search(pattern, text)
    assert match, f"CI job {job_key!r} missing from .github/workflows/ci.yml"
    return match.group(0)


def test_pr_fast_job_name_is_explicit():
    text = _workflow_text()
    block = _job_block(text, "pr-fast")
    assert re.search(r"(?i)name:\s*.*pr-fast", block), (
        "job pr-fast must have a display name containing PR-FAST"
    )
    assert "PR-FULL" not in block
    assert "pr-full" not in block.lower()


def test_pr_fast_runs_required_backend_goldens_and_properties():
    block = _job_block(_workflow_text(), "pr-fast")
    missing = [name for name in REQUIRED_BACKEND_TESTS if name not in block]
    assert not missing, f"PR-FAST must run {missing}"


def test_pr_fast_runs_frontend_unit_and_lint():
    block = _job_block(_workflow_text(), "pr-fast")
    assert "npm ci" in block
    assert re.search(r"npm test\b", block)
    assert "npm run lint" in block
    assert 'node-version: "20"' in block


def test_quantlib_hard_gate_not_weakened():
    text = _workflow_text()
    assert "name: backend-quantlib-hard-gate" in text
    block = _job_block(text, "backend-quantlib")
    assert "RISKFORGE_REQUIRE_QUANTLIB" in block
    assert "RISKFORGE_PRICING_ENGINE: quantlib" in block
    assert "tests/test_quantlib_golden.py" in block
    assert "tests/test_quantlib_gate.py" in block
    # Hard-gate must not strip QuantLib on install failure.
    assert "requirements-no-ql" not in block
