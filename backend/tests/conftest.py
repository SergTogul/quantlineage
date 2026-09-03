import os

import pytest

# Unit/API tests must not depend on an optional native QuantLib wheel being
# present in the execution environment. QuantLib has its own adapter tests.
# The R0.1.6 hard-gate job sets RISKFORGE_REQUIRE_QUANTLIB=1 so QL skips fail.
os.environ.setdefault("RISKFORGE_PRICING_ENGINE", "builtin")


def pytest_sessionfinish(session, exitstatus):
    """R0.1.6: QuantLib skips must not green the mandatory QuantLib CI job."""
    required = os.environ.get("RISKFORGE_REQUIRE_QUANTLIB", "").strip().lower() in {
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
def _reset_process_caches():
    """Isolate process-wide M5.5 LRUs across tests (curve + scenario memo)."""
    from app.pricing.curve_cache import reset_curve_construction_cache
    from app.risk.scenario_memo import reset_scenario_result_memo

    reset_curve_construction_cache()
    reset_scenario_result_memo()
    yield
    reset_curve_construction_cache()
    reset_scenario_result_memo()
