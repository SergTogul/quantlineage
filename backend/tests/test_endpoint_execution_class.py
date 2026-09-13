"""R0.10.1 / RF-015: interactive vs heavy endpoint classification contract."""

from __future__ import annotations

import pytest

from app.api.execution_class import (
    ENDPOINT_EXECUTION_CLASS,
    LISTED_HEAVY_ROUTES,
    ExecutionClass,
    classify,
    is_interactive_only,
    normalize_path,
)
from app.main import app

# R0.10.1 / RF-015 examples that must exist and must not be interactive-only.
_MILESTONE_HEAVY: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/risk/var"),  # FULL_REVALUATION
        ("POST", "/risk/es"),  # FULL_REVALUATION + contribution
        ("POST", "/risk/var/compare"),  # includes FULL_REVALUATION
        ("POST", "/risk/hierarchy"),  # large hierarchy
        ("POST", "/risk/stress/reverse/multi"),  # reverse multi-factor
        ("POST", "/risk/what-if"),  # expensive what-if
        ("POST", "/risk/stress/evaluate"),  # large scenario evaluation
        ("POST", "/risk/stress/evaluate/custom"),
        ("POST", "/risk/stress/formal/evaluate/custom"),
        ("POST", "/risk/contributors"),  # heavy contribution analysis
        ("POST", "/risk/change-attribution"),
    }
)

def _is_owned(path: str) -> bool:
    return path == "/health" or path.startswith(
        ("/portfolio", "/portfolios", "/market", "/risk")
    )


def _openapi_owned_routes() -> set[tuple[str, str]]:
    owned: set[tuple[str, str]] = set()
    for path, methods in app.openapi()["paths"].items():
        canonical = normalize_path(path)
        if not _is_owned(canonical):
            continue
        for method in methods:
            if method.startswith("x-"):
                continue
            owned.add((method.upper(), canonical))
    return owned


def test_listed_heavy_routes_match_milestone_examples() -> None:
    assert LISTED_HEAVY_ROUTES == _MILESTONE_HEAVY


def test_listed_heavy_routes_exist_in_openapi() -> None:
    registered = _openapi_owned_routes()
    missing = sorted(LISTED_HEAVY_ROUTES - registered)
    assert not missing, f"listed heavy routes missing from OpenAPI: {missing}"


def test_listed_heavy_routes_are_not_interactive_only() -> None:
    for method, path in sorted(LISTED_HEAVY_ROUTES):
        assert classify(method, path) is ExecutionClass.HEAVY, f"{method} {path}"
        assert not is_interactive_only(method, path), f"{method} {path} marked interactive-only"


def test_completed_run_get_is_interactive() -> None:
    assert classify("GET", "/risk/runs/{run_id}") is ExecutionClass.INTERACTIVE
    assert classify("GET", "/api/v1/risk/runs/{run_id}") is ExecutionClass.INTERACTIVE
    assert is_interactive_only("GET", "/risk/runs/{run_id}")


def test_lightweight_summary_and_small_drilldown_are_interactive() -> None:
    assert classify("POST", "/risk/summary") is ExecutionClass.INTERACTIVE
    assert classify("POST", "/risk/factors") is ExecutionClass.INTERACTIVE
    assert classify("POST", "/risk/limits/drilldown") is ExecutionClass.INTERACTIVE
    assert is_interactive_only("POST", "/risk/factors")
    assert is_interactive_only("POST", "/risk/limits/drilldown")


def test_full_revaluation_is_never_interactive_only() -> None:
    assert classify("POST", "/risk/var", methodology="FULL_REVALUATION") is ExecutionClass.HEAVY
    assert classify("POST", "/risk/summary", methodology="FULL_REVALUATION") is ExecutionClass.HEAVY
    assert not is_interactive_only("POST", "/risk/summary")


def test_dual_mount_shares_classification() -> None:
    assert classify("POST", "/api/v1/risk/hierarchy") is ExecutionClass.HEAVY
    assert classify("POST", "/api/v1/risk/summary") is ExecutionClass.INTERACTIVE
    assert normalize_path("/api/v1/risk/what-if") == "/risk/what-if"


def test_dashboard_batch_is_heavy() -> None:
    assert classify("POST", "/risk/dashboard") is ExecutionClass.HEAVY
    assert classify("POST", "/api/v1/risk/dashboard") is ExecutionClass.HEAVY
    assert not is_interactive_only("POST", "/risk/dashboard")


def test_wave_a_public_market_routes_are_interactive() -> None:
    assert classify("GET", "/market/history/{instrument_id}") is ExecutionClass.INTERACTIVE
    assert classify("GET", "/market/snapshots/{snapshot_id}") is ExecutionClass.INTERACTIVE
    assert classify("POST", "/market/snapshots/from-public-data") is ExecutionClass.INTERACTIVE
    assert classify("GET", "/api/v1/market/history/{instrument_id}") is ExecutionClass.INTERACTIVE
    assert is_interactive_only("GET", "/market/history/{instrument_id}")
    assert is_interactive_only("POST", "/market/snapshots/from-public-data")


def test_every_owned_route_is_classified() -> None:
    registered = _openapi_owned_routes()
    mapped = {(method, normalize_path(path)) for method, path in ENDPOINT_EXECUTION_CLASS}
    missing = sorted(registered - mapped)
    extra = sorted(mapped - registered)
    assert not missing, f"registered routes missing from classification map: {missing}"
    assert not extra, f"classification map entries not in OpenAPI: {extra}"


def test_unclassified_route_raises() -> None:
    with pytest.raises(KeyError, match="unclassified"):
        classify("DELETE", "/risk/unknown")
