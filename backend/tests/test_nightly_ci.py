"""R0.12.4 / RF-016 — nightly workflow contract.

Heavier checks live in ``.github/workflows/nightly.yml`` (schedule +
workflow_dispatch). They must not appear in PR-FULL ``needs:`` and must not
trigger on ``pull_request``. Scan YAML text (no PyYAML), same style as
``test_pr_full_ci.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
NIGHTLY_YML = REPO_ROOT / ".github" / "workflows" / "nightly.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _job_block(text: str, job_key: str) -> str:
    pattern = rf"(?ms)^  {re.escape(job_key)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)"
    match = re.search(pattern, text)
    assert match, f"CI job {job_key!r} missing from workflow"
    return match.group(0)


def _needs_ids(block: str) -> set[str]:
    inline = re.search(r"needs:\s*\[([^\]]+)\]", block)
    if inline:
        return {
            part.strip().strip("'\"")
            for part in inline.group(1).split(",")
            if part.strip()
        }
    listed = re.search(r"(?ms)^    needs:\n((?:      - .+\n?)+)", block)
    if listed:
        return set(re.findall(r"^      - (\S+)", listed.group(1), re.M))
    raise AssertionError("PR-FULL job must declare needs:")


def _on_block(text: str) -> str:
    match = re.search(r"(?ms)^on:\n(.*?)(?=^[A-Za-z]|\Z)", text)
    assert match, "nightly.yml must have a top-level on: block"
    return match.group(0)


def test_nightly_workflow_file_exists():
    assert NIGHTLY_YML.is_file(), "expected .github/workflows/nightly.yml"


def test_nightly_triggers_are_schedule_and_dispatch_not_pull_request():
    on_block = _on_block(_text(NIGHTLY_YML))
    assert "workflow_dispatch" in on_block
    assert "schedule:" in on_block
    assert "pull_request" not in on_block


def test_pr_full_needs_does_not_include_nightly():
    block = _job_block(_text(CI_YML), "pr-full")
    needed = _needs_ids(block)
    leaked = [job_id for job_id in needed if "nightly" in job_id.lower()]
    assert not leaked, f"PR-FULL needs: must not include nightly jobs; found {leaked}"
    assert not re.search(r"(?im)^      - \S*nightly", block), (
        "PR-FULL needs: list must not name a nightly job id"
    )


def test_nightly_runs_native_benchmark_binary():
    text = _text(NIGHTLY_YML)
    assert "backend/native/src/benchmark.cpp" in text
    assert "g++" in text
    assert "--exposures" in text
    assert "echo-only" not in text.lower()


def test_nightly_runs_postgres_two_worker():
    text = _text(NIGHTLY_YML)
    assert "tests/test_postgres_two_worker.py" in text
    assert "postgres:16-alpine" in text
    block = _job_block(text, "postgres-two-worker")
    assert "continue-on-error" not in block
    assert "RISKFORGE_NIGHTLY" in block


def test_nightly_native_asserts_checksum_identity_not_sla():
    block = _job_block(_text(NIGHTLY_YML), "native-benchmark")
    assert "check_m6_sla.py" not in block
    assert "checksum" in block
    assert "cpp_header" in block
    assert "SLA-sized" not in block
    assert not re.search(r"(?im)^      - name:.*SLA", block)


def test_two_worker_fails_when_ci_set_and_dsn_unreachable(monkeypatch):
    """CI + offered postgresql DSN must fail-closed, not skip-green."""
    from tests.test_postgres_two_worker import require_live_postgres

    monkeypatch.setenv("CI", "1")
    monkeypatch.delenv("RISKFORGE_NIGHTLY", raising=False)
    monkeypatch.setenv(
        "RISKFORGE_DATABASE_URL",
        "postgresql+psycopg://riskforge:riskforge@127.0.0.1:1/riskforge",
    )
    with pytest.raises(pytest.fail.Exception):
        require_live_postgres()


def test_two_worker_skips_locally_when_dsn_unreachable(monkeypatch):
    """Local-optional skip when CI and RISKFORGE_NIGHTLY are unset."""
    from tests.test_postgres_two_worker import require_live_postgres

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("RISKFORGE_NIGHTLY", raising=False)
    monkeypatch.setenv(
        "RISKFORGE_DATABASE_URL",
        "postgresql+psycopg://riskforge:riskforge@127.0.0.1:1/riskforge",
    )
    with pytest.raises(pytest.skip.Exception):
        require_live_postgres()
