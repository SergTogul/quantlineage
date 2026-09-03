import os

import pytest

# Unit/API tests must not depend on an optional native QuantLib wheel being
# present in the execution environment. QuantLib has its own adapter tests.
os.environ.setdefault("RISKFORGE_PRICING_ENGINE", "builtin")


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
