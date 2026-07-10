"""M7.1: FastAPI surface is decomposed into APIRouter modules (paths preserved)."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

# Expected router modules after M7.1 (charter 07 layout; paths stay unversioned).
_ROUTER_MODULES = (
    "app.api.health",
    "app.api.portfolio",
    "app.api.market",
    "app.api.risk",
    "app.api.stress",
    "app.api.attribution",
    "app.api.limits",
    "app.api.risk_runs",
)

# Critical paths must remain registered (M7.2 also dual-mounts under /api/v1).
_CRITICAL_PATHS = (
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
    ("POST", "/risk/stress"),
    ("GET", "/risk/stress/scenarios"),
    ("POST", "/risk/stress/reverse"),
    ("POST", "/risk/limits"),
    ("POST", "/risk/limits/drilldown"),
    ("POST", "/risk/runs"),
    ("GET", "/risk/runs/{run_id}"),
    ("POST", "/risk/runs/compare"),
    ("POST", "/api/v1/risk/runs"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/portfolio"),
    ("POST", "/api/v1/risk/summary"),
)


@pytest.mark.parametrize("module_name", _ROUTER_MODULES)
def test_m71_router_modules_export_api_router(module_name: str) -> None:
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "router"), f"{module_name} must export router"
    assert isinstance(mod.router, APIRouter)


def test_m71_critical_paths_registered() -> None:
    from app.main import app

    openapi_paths = app.openapi()["paths"]
    flat: set[tuple[str, str]] = set()
    for path, methods in openapi_paths.items():
        for method in methods:
            if method.startswith("x-"):
                continue
            flat.add((method.upper(), path))

    missing = [item for item in _CRITICAL_PATHS if item not in flat]
    assert not missing, f"missing routes after decomposition: {missing}"


def test_m71_health_and_portfolio_smoke() -> None:
    from app.main import app

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        portfolio = client.get("/portfolio")
        assert portfolio.status_code == 200
        body = portfolio.json()
        assert "id" in body
        assert "positions" in body


def test_m71_main_does_not_declare_inline_risk_routes() -> None:
    """main.py should wire include_router only — no @app.post(\"/risk/...\") handlers."""
    main_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"))

    inline_risk = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            path = _decorator_path(dec)
            if path and path.startswith("/risk"):
                inline_risk.append((node.name, path))

    assert not inline_risk, (
        "M7.1 requires risk routes on APIRouter modules, not inline on app: "
        f"{inline_risk}"
    )


def _decorator_path(dec: ast.AST) -> str | None:
    """Extract path string from @app.get/post(\"/...\") style decorators."""
    if not isinstance(dec, ast.Call):
        return None
    if not dec.args:
        return None
    arg0 = dec.args[0]
    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
        return arg0.value
    return None
