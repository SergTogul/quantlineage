"""M7.2: public routers dual-mounted at legacy paths and /api/v1/..."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# Critical OpenAPI paths must exist on both prefixes (risk_runs already had v1).
_DUAL_MOUNTED_PATHS = (
    ("GET", "/health"),
    ("GET", "/portfolio"),
    ("GET", "/portfolios"),
    ("GET", "/portfolios/{portfolio_id}"),
    ("POST", "/market/snapshot"),
    ("POST", "/risk/summary"),
    ("POST", "/risk/var"),
    ("POST", "/risk/es"),
    ("POST", "/risk/var/compare"),
    ("POST", "/risk/what-if"),
    ("POST", "/risk/hierarchy"),
    ("POST", "/risk/attribution"),
    ("POST", "/risk/change-attribution"),
    ("POST", "/risk/query"),
    ("POST", "/risk/contributors"),
    ("POST", "/risk/stress"),
    ("GET", "/risk/stress/scenarios"),
    ("POST", "/risk/stress/reverse"),
    ("POST", "/risk/limits"),
    ("POST", "/risk/limits/drilldown"),
    ("POST", "/risk/runs"),
    ("GET", "/risk/runs/{run_id}"),
    ("POST", "/risk/runs/compare"),
)

_API_V1 = "/api/v1"


def _v1_path(path: str) -> str:
    return f"{_API_V1}{path}"


def test_m72_openapi_registers_legacy_and_v1_paths() -> None:
    from app.main import app

    openapi_paths = app.openapi()["paths"]
    flat: set[tuple[str, str]] = set()
    for path, methods in openapi_paths.items():
        for method in methods:
            if method.startswith("x-"):
                continue
            flat.add((method.upper(), path))

    missing: list[tuple[str, str]] = []
    for method, path in _DUAL_MOUNTED_PATHS:
        if (method, path) not in flat:
            missing.append((method, path))
        v1 = (method, _v1_path(path))
        if v1 not in flat:
            missing.append(v1)

    assert not missing, f"M7.2 dual-mount missing routes: {missing}"


def test_m72_risk_runs_not_triple_mounted() -> None:
    """Unify cleanly: /risk/runs and /api/v1/risk/runs only — no /api/v1/api/v1/..."""
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/risk/runs" in paths
    assert "/api/v1/risk/runs" in paths
    assert "/api/v1/api/v1/risk/runs" not in paths
    assert "/api/v1/risk/api/v1/risk/runs" not in paths


@pytest.mark.parametrize(
    "legacy_path,v1_path",
    [
        ("/health", "/api/v1/health"),
        ("/portfolio", "/api/v1/portfolio"),
        ("/portfolios", "/api/v1/portfolios"),
        ("/risk/stress/scenarios", "/api/v1/risk/stress/scenarios"),
    ],
)
def test_m72_get_critical_paths_match(legacy_path: str, v1_path: str) -> None:
    from app.main import app

    with TestClient(app) as client:
        legacy = client.get(legacy_path)
        versioned = client.get(v1_path)
        assert legacy.status_code == 200
        assert versioned.status_code == 200
        assert legacy.json() == versioned.json()


def test_m72_post_risk_summary_legacy_and_v1() -> None:
    from app.main import app

    with TestClient(app) as client:
        portfolio = client.get("/portfolio").json()
        legacy = client.post("/risk/summary", json=portfolio)
        versioned = client.post("/api/v1/risk/summary", json=portfolio)
        assert legacy.status_code == 200
        assert versioned.status_code == 200
        assert legacy.json() == versioned.json()


def test_m72_post_market_snapshot_legacy_and_v1() -> None:
    from app.main import app

    with TestClient(app) as client:
        portfolio = client.get("/portfolio").json()
        legacy = client.post("/market/snapshot", json=portfolio)
        versioned = client.post("/api/v1/market/snapshot", json=portfolio)
        assert legacy.status_code == 200
        assert versioned.status_code == 200
        # Snapshot ids may differ; shape keys must match.
        assert set(legacy.json().keys()) == set(versioned.json().keys())


def test_m72_post_risk_limits_legacy_and_v1() -> None:
    from app.main import app

    with TestClient(app) as client:
        portfolio = client.get("/portfolio").json()
        legacy = client.post("/risk/limits", json=portfolio)
        versioned = client.post("/api/v1/risk/limits", json=portfolio)
        assert legacy.status_code == 200
        assert versioned.status_code == 200
        assert legacy.json() == versioned.json()
