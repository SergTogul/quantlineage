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
PLAYWRIGHT_CONFIG = REPO_ROOT / "e2e" / "playwright.config.js"

NIGHTLY_JOB_IDS = (
    "native-benchmark",
    "postgres-two-worker",
    "full-reval-sample",
    "quantlib-e2e",
    "hierarchy-benchmark",
    "full-reval-n100",
)


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
    listed = re.search(r"(?m)^    needs:\n((?:      - \S+\n)+)", block)
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
    leaked_ids = [job_id for job_id in NIGHTLY_JOB_IDS if job_id in needed]
    assert not leaked_ids, f"PR-FULL needs: must not include nightly job ids; found {leaked_ids}"
    assert "quantlib-e2e" not in needed
    assert "hierarchy-benchmark" not in needed
    assert "full-reval-n100" not in needed
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


def test_nightly_runs_quantlib_critical_e2e():
    text = _text(NIGHTLY_YML)
    block = _job_block(text, "quantlib-e2e")
    assert "r0-critical-journey.spec.ts" in block
    assert "playwright" in block
    assert "RISKFORGE_PRICING_ENGINE: quantlib" in block
    assert "RISKFORGE_REQUIRE_QUANTLIB" in block
    assert "RISKFORGE_NIGHTLY" in block
    assert "pip install -r requirements.txt" in block
    assert "import QuantLib" in block
    assert "requirements-no-ql" not in block
    assert "continue-on-error" not in block
    assert "echo-only" not in block.lower()
    assert "check_m6_sla.py" not in block
    assert "tests/test_qa024_ql_demo_range.py" in block


def test_playwright_config_honors_pricing_engine_env():
    text = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")
    assert "process.env.RISKFORGE_PRICING_ENGINE" in text
    assert re.search(
        r"process\.env\.RISKFORGE_PRICING_ENGINE\s*\|\|\s*'builtin'",
        text,
    ), "PR e2e must default to builtin; nightly may override to quantlib"
    assert not re.search(
        r"RISKFORGE_PRICING_ENGINE:\s*'builtin'",
        text,
    ), "must not unconditionally overwrite RISKFORGE_PRICING_ENGINE to builtin"


def test_require_quantlib_fails_when_nightly_and_missing(monkeypatch):
    """RISKFORGE_NIGHTLY=1 + missing QuantLib must fail, not skip-green."""
    from tests.quantlib_gate import require_quantlib_for_nightly

    monkeypatch.setenv("RISKFORGE_NIGHTLY", "1")
    monkeypatch.delenv("RISKFORGE_REQUIRE_QUANTLIB", raising=False)

    def _missing():
        raise ImportError("simulated missing QuantLib")

    with pytest.raises(pytest.fail.Exception):
        require_quantlib_for_nightly(_importer=_missing)


def test_require_quantlib_skips_locally_when_missing(monkeypatch):
    """Local-optional skip when RISKFORGE_NIGHTLY and REQUIRE_QUANTLIB are unset."""
    from tests.quantlib_gate import require_quantlib_for_nightly

    monkeypatch.delenv("RISKFORGE_NIGHTLY", raising=False)
    monkeypatch.delenv("RISKFORGE_REQUIRE_QUANTLIB", raising=False)
    monkeypatch.delenv("CI", raising=False)

    def _missing():
        raise ImportError("simulated missing QuantLib")

    with pytest.raises(pytest.skip.Exception):
        require_quantlib_for_nightly(_importer=_missing)


def test_nightly_runs_hierarchy_benchmark():
    text = _text(NIGHTLY_YML)
    block = _job_block(text, "hierarchy-benchmark")
    assert "benchmarks/run_hierarchy_bench.py" in block
    assert "--json" in block
    assert "hierarchy_python" in block
    assert "checksum" in block
    assert "n_nodes" in block
    assert "n_positions" in block
    assert "RISKFORGE_NIGHTLY" in block
    assert "continue-on-error" not in block
    assert "echo-only" not in block.lower()
    assert "check_m6_sla.py" not in block


def test_nightly_hierarchy_asserts_identity_not_sla():
    block = _job_block(_text(NIGHTLY_YML), "hierarchy-benchmark")
    assert "check_m6_sla.py" not in block
    assert "checksum" in block
    assert "6a9c1124e91805528f550cfe4ae922f19155342cbac3c0d4947bdc95aa82ef75" in block
    assert "64000" in block
    assert "SLA-sized" not in block
    assert not re.search(r"(?im)^      - name:.*SLA", block)
    assert not re.search(r"throughput\s*>\s*0", block)
    assert "wall_ms >=" not in block


def test_hierarchy_bench_script_is_identity_not_sla():
    path = REPO_ROOT / "benchmarks" / "run_hierarchy_bench.py"
    assert path.is_file(), "expected benchmarks/run_hierarchy_bench.py"
    text = path.read_text(encoding="utf-8")
    assert "HierarchyEngine" in text
    assert "checksum" in text
    assert not re.search(r"(?m)^\s*(import |from ).*check_m6_sla", text)
    assert not re.search(r"check_m6_sla\.py\s", text)
    assert not re.search(r"throughput\s*>\s*0", text)
    assert "6a9c1124e91805528f550cfe4ae922f19155342cbac3c0d4947bdc95aa82ef75" in text
    assert "EXPECTED_N_NODES" in text
    assert "EXPECTED_MARKET_VALUE" in text


def test_nightly_runs_full_reval_n100():
    text = _text(NIGHTLY_YML)
    block = _job_block(text, "full-reval-n100")
    assert "tests/test_nightly_full_reval_n100.py" in block
    assert "RISKFORGE_NIGHTLY" in block
    assert "continue-on-error" not in block
    assert "echo-only" not in block.lower()
    assert "check_m6_sla.py" not in block
    assert not re.search(r"wall_ms\s*[><]=?\s*\d", block)
    assert not re.search(r"peak_rss_kib\s*[><]=?\s*\d", block)
    assert not re.search(r"throughput\s*>\s*0", block)
    assert "SLA-sized" not in block


def test_nightly_full_reval_n100_is_identity_not_sla():
    path = REPO_ROOT / "backend" / "tests" / "test_nightly_full_reval_n100.py"
    assert path.is_file(), "expected backend/tests/test_nightly_full_reval_n100.py"
    text = path.read_text(encoding="utf-8")
    assert "RISKFORGE_NIGHTLY" in text
    assert "skipif" in text
    assert "n_positions" in text
    assert "100" in text
    assert "50" in text
    assert not re.search(r"(?m)^\s*(import |from ).*check_m6_sla", text)
    assert not re.search(r"check_m6_sla\.py\s", text)
    assert not re.search(r"throughput\s*>\s*0", text)
    assert not re.search(r"wall_ms\s*[><]=?\s*\d", text)


def _job_ids(text: str) -> tuple[str, ...]:
    match = re.search(r"(?ms)^jobs:\n(.*)\Z", text)
    assert match, "workflow must have a jobs: block"
    return tuple(re.findall(r"(?m)^  ([A-Za-z0-9_-]+):", match.group(1)))


def _invokes_check_m6_sla(block: str) -> bool:
    return bool(
        re.search(
            r"(?m)^\s+(run:|.+\|\s*$|.*\b(?:python|python3)\b).*\bcheck_m6_sla\.py\b",
            block,
        )
        or re.search(r"(?m)^\s+.*\bbenchmarks/check_m6_sla\.py\b", block)
    )


def test_ubuntu_latest_jobs_do_not_run_check_m6_sla():
    """Host-specific SLA-K1/K2 floors flake on ubuntu-latest. Do not invent them."""
    for path in (CI_YML, NIGHTLY_YML):
        text = _text(path)
        for job_id in _job_ids(text):
            block = _job_block(text, job_id)
            if not re.search(r"(?m)^\s+runs-on:\s*ubuntu-latest\s*$", block):
                continue
            assert not _invokes_check_m6_sla(block), (
                f"{path.name} job {job_id!r} runs on ubuntu-latest and must not "
                "invoke benchmarks/check_m6_sla.py"
            )


def test_labeled_sla_job_is_absent_honest_residual():
    """No self-hosted runner is registered; do not fake a labeled SLA job.

    If a later owner adds a labeled job, it must run check_m6_sla.py, must not
    use ubuntu-latest, must not set continue-on-error, and must stay out of
    PR-FULL needs:. Until then nightly.yml must document PARTIAL.
    """
    text = _text(NIGHTLY_YML)
    sla_jobs = [
        job_id
        for job_id in _job_ids(text)
        if _invokes_check_m6_sla(_job_block(text, job_id))
    ]
    assert not sla_jobs, (
        f"labeled SLA jobs found {sla_jobs}; pin runs-on / continue-on-error "
        "separately rather than inventing ubuntu-latest floors"
    )
    assert "RF-016 residual: labeled-runner SLA-K1/K2 is PARTIAL" in text
    assert "actions/runners total_count=0" in text
    assert "continue-on-error" not in text


def test_sla_k_harness_exists_with_documented_floors():
    path = REPO_ROOT / "benchmarks" / "check_m6_sla.py"
    assert path.is_file(), "expected benchmarks/check_m6_sla.py"
    text = path.read_text(encoding="utf-8")
    assert "MIN_SERIAL_SPEEDUP_VS_PYTHON = 50.0" in text
    assert "MIN_PARALLEL_VS_SERIAL = 1.3" in text
    assert 'WORKLOAD = "10k_x_1k"' in text
    assert "SLA-K1" in text
    assert "SLA-K2" in text


def test_sla_k_docs_exist_and_do_not_claim_ubuntu_ci_floors():
    perf = REPO_ROOT / "docs" / "performance.md"
    results = REPO_ROOT / "benchmarks" / "RESULTS.md"
    assert perf.is_file(), "expected docs/performance.md"
    assert results.is_file(), "expected benchmarks/RESULTS.md"
    perf_text = perf.read_text(encoding="utf-8")
    results_text = results.read_text(encoding="utf-8")
    assert "SLA-K1" in perf_text and "SLA-K2" in perf_text
    assert "SLA-K1" in results_text and "SLA-K2" in results_text
    assert "check_m6_sla.py" in perf_text
    assert "not a CI hard gate on arbitrary runner hardware" in perf_text
    assert "RF-016 residual: labeled-runner SLA-K1/K2 is PARTIAL" in perf_text
    assert "actions/runners total_count=0" in perf_text


def test_pr_full_needs_does_not_include_sla_k():
    block = _job_block(_text(CI_YML), "pr-full")
    needed = _needs_ids(block)
    leaked = [
        job_id
        for job_id in needed
        if "sla" in job_id.lower() or "m6" in job_id.lower()
    ]
    assert not leaked, f"PR-FULL needs: must not include SLA jobs; found {leaked}"
    assert "check_m6_sla.py" not in _text(CI_YML)
