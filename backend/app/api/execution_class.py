"""Interactive vs heavy HTTP execution class (R0.10.1 / RF-015).

Classification contract only. This module does not enqueue work, reject
requests, change numerical methods, or add auth. R0.10.2 owns dashboard
batching; R0.10.3 owns queue/backpressure.

Cheap / interactive: completed-run GET, lightweight summary (default
LINEAR / DELTA_GAMMA), small factor or limit drilldown, catalog / health.

Heavy / RiskRun: FULL_REVALUATION, large hierarchy, reverse multi-factor,
expensive what-if, large scenario evaluation, heavy contribution analysis.

Canonical keys are unversioned paths. ``/api/v1`` dual-mounts share the
same class via ``normalize_path``.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping

API_V1_PREFIX = "/api/v1"
FULL_REVALUATION = "FULL_REVALUATION"


class ExecutionClass(str, Enum):
    INTERACTIVE = "interactive"
    HEAVY = "heavy"


# Routes whose query/body methodology can select FULL_REVALUATION.
METHODOLOGY_BEARING_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/risk/summary"),
        ("POST", "/risk/var"),
        ("POST", "/risk/es"),
        ("POST", "/risk/what-if"),
        ("POST", "/risk/stress/compare"),
        ("POST", "/risk/stress/formal/compare"),
    }
)

# R0.10.1 / RF-015 listed heavy examples. Must exist and must not be
# treated as interactive-only.
LISTED_HEAVY_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/risk/var"),
        ("POST", "/risk/es"),
        ("POST", "/risk/var/compare"),
        ("POST", "/risk/hierarchy"),
        ("POST", "/risk/stress/reverse/multi"),
        ("POST", "/risk/what-if"),
        ("POST", "/risk/stress/evaluate"),
        ("POST", "/risk/stress/evaluate/custom"),
        ("POST", "/risk/stress/formal/evaluate/custom"),
        ("POST", "/risk/contributors"),
        ("POST", "/risk/change-attribution"),
    }
)

ENDPOINT_EXECUTION_CLASS: Mapping[tuple[str, str], ExecutionClass] = {
    ("GET", "/health"): ExecutionClass.INTERACTIVE,
    ("GET", "/portfolio"): ExecutionClass.INTERACTIVE,
    ("GET", "/portfolios"): ExecutionClass.INTERACTIVE,
    ("GET", "/portfolios/{portfolio_id}"): ExecutionClass.INTERACTIVE,
    ("PUT", "/portfolios/{portfolio_id}"): ExecutionClass.INTERACTIVE,
    ("GET", "/risk/runs/{run_id}"): ExecutionClass.INTERACTIVE,
    ("GET", "/risk/runs/{run_id}/provenance"): ExecutionClass.INTERACTIVE,
    ("GET", "/risk/stress/scenarios"): ExecutionClass.INTERACTIVE,
    ("GET", "/risk/stress/scenarios/formal"): ExecutionClass.INTERACTIVE,
    ("POST", "/market/snapshot"): ExecutionClass.INTERACTIVE,
    ("GET", "/market/rates-showcase"): ExecutionClass.INTERACTIVE,
    ("GET", "/market/history/{instrument_id}"): ExecutionClass.INTERACTIVE,
    ("GET", "/market/snapshots/{snapshot_id}"): ExecutionClass.INTERACTIVE,
    ("POST", "/market/snapshots/from-public-data"): ExecutionClass.INTERACTIVE,
    ("POST", "/risk/summary"): ExecutionClass.INTERACTIVE,
    ("POST", "/risk/factors"): ExecutionClass.INTERACTIVE,
    ("POST", "/risk/limits/drilldown"): ExecutionClass.INTERACTIVE,
    ("POST", "/risk/var"): ExecutionClass.HEAVY,
    ("POST", "/risk/es"): ExecutionClass.HEAVY,
    ("POST", "/risk/var/compare"): ExecutionClass.HEAVY,
    ("POST", "/risk/what-if"): ExecutionClass.HEAVY,
    ("POST", "/risk/hierarchy"): ExecutionClass.HEAVY,
    ("POST", "/risk/query"): ExecutionClass.HEAVY,
    ("POST", "/risk/contributors"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/custom"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/formal/custom"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/evaluate"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/evaluate/custom"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/formal/evaluate/custom"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/reverse"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/reverse/multi"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/compare"): ExecutionClass.HEAVY,
    ("POST", "/risk/stress/formal/compare"): ExecutionClass.HEAVY,
    ("POST", "/risk/attribution"): ExecutionClass.HEAVY,
    ("POST", "/risk/attribution/demo"): ExecutionClass.HEAVY,
    ("POST", "/risk/change-attribution"): ExecutionClass.HEAVY,
    ("POST", "/risk/limits"): ExecutionClass.HEAVY,
    ("POST", "/risk/runs"): ExecutionClass.HEAVY,
    ("POST", "/risk/runs/compare"): ExecutionClass.HEAVY,
    ("POST", "/risk/dashboard"): ExecutionClass.HEAVY,
}


def normalize_path(path: str) -> str:
    """Strip the ``/api/v1`` dual-mount prefix when present."""
    if path == API_V1_PREFIX:
        return "/"
    prefix = API_V1_PREFIX + "/"
    if path.startswith(prefix):
        return path[len(API_V1_PREFIX) :]
    return path


def canonical_route(method: str, path: str) -> tuple[str, str]:
    return method.upper(), normalize_path(path)


def _methodology_token(methodology: object | None) -> str | None:
    if methodology is None:
        return None
    value = getattr(methodology, "value", methodology)
    return str(value).strip().upper()


def classify(
    method: str,
    path: str,
    *,
    methodology: object | None = None,
) -> ExecutionClass:
    """Return the execution class for a dual-mounted route.

    ``methodology=FULL_REVALUATION`` upgrades methodology-bearing routes to
    HEAVY even when the static map marks the default path INTERACTIVE
    (lightweight ``POST /risk/summary``).
    """
    key = canonical_route(method, path)
    if _methodology_token(methodology) == FULL_REVALUATION and key in METHODOLOGY_BEARING_ROUTES:
        return ExecutionClass.HEAVY
    try:
        return ENDPOINT_EXECUTION_CLASS[key]
    except KeyError as exc:
        raise KeyError(f"unclassified route: {key[0]} {key[1]}") from exc


def is_interactive_only(method: str, path: str) -> bool:
    """True when the route is INTERACTIVE and cannot become HEAVY.

    Methodology-bearing routes (including lightweight summary) return False
    because ``FULL_REVALUATION`` is a listed heavy class.
    """
    key = canonical_route(method, path)
    if key in METHODOLOGY_BEARING_ROUTES:
        return False
    return classify(method, path) is ExecutionClass.INTERACTIVE
