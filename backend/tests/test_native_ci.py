"""R0.12.5 — native-smoke CI compile-line contract.

The backend-pytest "Native C++ compile and smoke" step must link both
``kernel_test.cpp`` and ``risk_kernel_capi.cpp``. The old one-file compile
is a documented fail: it does not define ``quantlineage_kernel_abi_version`` /
``quantlineage_portfolio_scenarios``. Scan YAML text like ``test_pr_full_ci.py``
(PyYAML is not a dependency).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow_text() -> str:
    return CI_YML.read_text(encoding="utf-8")


def _job_block(text: str, job_key: str) -> str:
    pattern = rf"(?ms)^  {re.escape(job_key)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)"
    match = re.search(pattern, text)
    assert match, f"CI job {job_key!r} missing from .github/workflows/ci.yml"
    return match.group(0)


def _join_backslash_continuations(block: str) -> list[str]:
    """Collapse ``g++ ... \\`` YAML run lines into single argv strings."""
    joined: list[str] = []
    buf = ""
    for line in block.splitlines():
        stripped_right = line.rstrip()
        if stripped_right.endswith("\\"):
            buf += stripped_right[:-1] + " "
            continue
        buf += stripped_right
        joined.append(buf)
        buf = ""
    if buf:
        joined.append(buf)
    return joined


def _native_smoke_kernel_test_gpp_lines(block: str) -> list[str]:
    """g++ lines that compile kernel_test (not the later -shared lib)."""
    commands = _join_backslash_continuations(block)
    return [
        cmd
        for cmd in commands
        if "g++" in cmd and "kernel_test.cpp" in cmd and "-shared" not in cmd
    ]


def test_native_smoke_gpp_lists_both_translation_units():
    text = _workflow_text()
    block = _job_block(text, "backend")
    assert "Native C++ compile and smoke" in block
    gpp_lines = _native_smoke_kernel_test_gpp_lines(block)
    assert gpp_lines, "backend native-smoke must invoke g++ on kernel_test.cpp"

    for cmd in gpp_lines:
        assert "kernel_test.cpp" in cmd
        assert "risk_kernel_capi.cpp" in cmd, (
            "native-smoke g++ argv must list risk_kernel_capi.cpp with "
            "kernel_test.cpp. The old one-file compile "
            "(g++ … native/tests/kernel_test.cpp -o /tmp/kernel_test) is a "
            "documented fail: undefined _quantlineage_kernel_abi_version and "
            "_quantlineage_portfolio_scenarios."
        )
        assert "-std=c++20" in cmd
        assert "-O2" in cmd
        assert "-pthread" in cmd
        assert "-I native/include" in cmd or "-I  native/include" in cmd
