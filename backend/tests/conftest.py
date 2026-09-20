import os
import shutil
import subprocess
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_ai: opt-in live OpenAI smoke test; requires OPENAI_API_KEY and "
        "RUN_LIVE_AI_TESTS=1 (excluded from normal CI).",
    )

# Unit/API tests must not depend on an optional native QuantLib wheel being
# present in the execution environment. QuantLib has its own adapter tests.
# The R0.1.6 hard-gate job sets QUANTLINEAGE_REQUIRE_QUANTLIB=1 so QL skips fail.
os.environ.setdefault("QUANTLINEAGE_PRICING_ENGINE", "builtin")


def pytest_sessionfinish(session, exitstatus):
    """R0.1.6: QuantLib skips must not green the mandatory QuantLib CI job."""
    required = os.environ.get("QUANTLINEAGE_REQUIRE_QUANTLIB", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not required:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    skipped = reporter.stats.get("skipped", [])
    ql_skips = []
    for report in skipped:
        node = getattr(report, "nodeid", "")
        reason = str(getattr(report, "longrepr", "")).lower()
        if "quantlib" in node.lower() or "quantlib" in reason:
            ql_skips.append(node)
    if ql_skips:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def _isolate_ai_env_from_workspace_dotenv(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Keep normal tests free of a developer workspace ``.env`` AI config.

    ``load_application_dotenv`` uses ``override=False``, so clearing env vars
    alone is not enough: lifespan would reload ``AI_PROVIDER`` from ``.env``.
    Opt-in ``live_ai`` tests keep the real environment.
    """
    if request.node.get_closest_marker("live_ai"):
        return
    for name in (
        "OPENAI_API_KEY",
        "AI_PROVIDER",
        "OPENAI_MODEL",
        "AI_TIMEOUT_SECONDS",
        "AI_MAX_OUTPUT_TOKENS",
        "AI_MAX_TOOL_ROUNDS",
        "AI_MAX_TOOL_CALLS",
        "AI_ASSISTANT_LOOP",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.ai.factory.load_application_dotenv", lambda: None)
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "load_application_dotenv", lambda: None)


@pytest.fixture(autouse=True)
def _reset_process_caches():
    """Isolate process-wide M5.5 LRUs across tests (curve + scenario memo)."""
    from app.pricing.curve_cache import reset_curve_construction_cache
    from app.risk.scenario_memo import reset_scenario_result_memo

    reset_curve_construction_cache()
    reset_scenario_result_memo()
    yield
    reset_curve_construction_cache()
    reset_scenario_result_memo()


@pytest.fixture(scope="session")
def native_scenario_lib(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build ``libriskkernel`` once per session (once per xdist worker).

    Native ABI tests share this artifact. ``test_cpp_kernel_compiles_and_executes``
    still compiles ``kernel_test`` from scratch as an explicit compile smoke.
    """
    if not shutil.which("g++"):
        pytest.skip("g++ unavailable")
    root = Path(__file__).resolve().parents[1] / "native"
    out_dir = tmp_path_factory.mktemp("native_scenario_lib")
    lib_name = (
        "libriskkernel.dylib" if os.uname().sysname == "Darwin" else "libriskkernel.so"
    )
    lib = out_dir / lib_name
    subprocess.run(
        [
            "g++",
            "-std=c++20",
            "-O3",
            "-shared",
            "-fPIC",
            "-pthread",
            "-I",
            str(root / "include"),
            str(root / "src" / "risk_kernel_capi.cpp"),
            "-o",
            str(lib),
        ],
        check=True,
    )
    return lib
