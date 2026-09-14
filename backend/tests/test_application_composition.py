"""R0.9.3 / RF-010: PortfolioService is composed in lifespan, not a module singleton."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient

from app.api.deps import get_portfolio_service
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEPS_PATH = BACKEND_ROOT / "app" / "api" / "deps.py"
MAIN_PATH = BACKEND_ROOT / "app" / "main.py"
DI_CONTAINER_MODULES = frozenset(
    {
        "dependency_injector",
        "injector",
        "punq",
        "lagom",
        "wireup",
        "that_depends",
    }
)
# Renamed caches such as ``_legacy_portfolio_service = build_portfolio_service()``.
FORBIDDEN_SERVICE_CACHE_MARKERS = (
    "_legacy_portfolio_service",
    "fallback_portfolio_service",
)


@pytest.fixture
def clear_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTLINEAGE_DATABASE_URL", raising=False)


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _top_level_assign_calls(path: Path) -> list[tuple[str, str]]:
    """Return (target_name, called_func) for module-level ``x = func(...)``.

    Includes annotated assignments so ``_cache: T = build_portfolio_service()``
    cannot sneak past a pin that only walks ``ast.Assign``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    for node in tree.body:
        value: ast.expr | None = None
        names: list[str] = []
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            value = node.value
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.target, ast.Name)
        ):
            value = node.value
            names = [node.target.id]
        if value is None:
            continue
        called = _call_name(value.func)
        if called is None:
            continue
        found.extend((name, called) for name in names)
    return found


def _calls_named(path: Path, func_name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) == func_name:
            return True
    return False


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".", 1)[0])
    return modules


def test_deps_does_not_assign_module_global_portfolio_service() -> None:
    """HTTP composition must not call ``build_portfolio_service`` in deps at all.

    Any name counts (``portfolio_service``, ``_legacy_portfolio_service``, …).
    """
    for path in (DEPS_PATH, MAIN_PATH):
        source = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_SERVICE_CACHE_MARKERS:
            assert marker not in source, (
                f"module-global service cache still present in {path.name}: {marker}"
            )
    assigned = _top_level_assign_calls(DEPS_PATH)
    offenders = [
        f"{name} = {called}()"
        for name, called in assigned
        if called == "build_portfolio_service"
    ]
    assert not offenders, f"module-global service singleton still present: {offenders}"
    assert not _calls_named(DEPS_PATH, "build_portfolio_service"), (
        "deps.py must not call build_portfolio_service (lifespan in main.py owns that)"
    )


def test_get_portfolio_service_takes_request_like_worker() -> None:
    params = inspect.signature(get_portfolio_service).parameters
    assert "request" in params, "get_portfolio_service must read app.state from Request"
    source = inspect.getsource(get_portfolio_service)
    assert "HTTP_503_SERVICE_UNAVAILABLE" in source
    assert "fallback" not in source.lower()


def test_lifespan_sets_portfolio_service_on_app_state(clear_db_url: None) -> None:
    from app.main import app

    with TestClient(app) as client:
        svc = getattr(client.app.state, "portfolio_service", None)
        assert isinstance(svc, PortfolioService)
        worker = client.app.state.risk_run_worker
        assert worker._portfolio_service is svc


def test_http_depends_reads_app_state_portfolio_service(clear_db_url: None) -> None:
    """Depends(get_portfolio_service) returns the lifespan instance, not a bypass singleton."""
    from app.main import app

    @app.get("/_test/composition/portfolio-service")
    def _probe(
        request: Request,
        service: PortfolioService = Depends(get_portfolio_service),
    ) -> dict[str, bool]:
        return {
            "is_app_state": service is request.app.state.portfolio_service,
            "is_worker": service is request.app.state.risk_run_worker._portfolio_service,
        }

    try:
        with TestClient(app) as client:
            resp = client.get("/_test/composition/portfolio-service")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["is_app_state"] is True
            assert body["is_worker"] is True
    finally:
        app.router.routes = [
            route
            for route in app.router.routes
            if getattr(route, "path", None) != "/_test/composition/portfolio-service"
        ]


def test_main_service_aliases_lifespan_instance(clear_db_url: None) -> None:
    from app import main

    with TestClient(main.app) as client:
        assert main.service is client.app.state.portfolio_service


def test_composition_modules_do_not_import_di_container() -> None:
    for path in (DEPS_PATH, MAIN_PATH):
        imported = _imported_modules(path)
        hit = imported & DI_CONTAINER_MODULES
        assert not hit, f"{path.name} imports DI container: {sorted(hit)}"


def test_http_portfolio_service_without_lifespan_is_503(clear_db_url: None) -> None:
    """TestClient without lifespan must fail closed (503), not a module-global cache."""
    from app import main
    from app.main import app

    state_attrs = (
        "portfolio_service",
        "risk_run_worker",
        "scenario_definition_repo",
        "market_snapshot_repo",
        "limit_definition_repo",
        "session_factory",
        "persistence_enabled",
    )
    saved = {
        attr: getattr(app.state, attr)
        for attr in state_attrs
        if hasattr(app.state, attr)
    }
    try:
        for attr in state_attrs:
            if hasattr(app.state, attr):
                delattr(app.state, attr)

        assert getattr(app.state, "portfolio_service", None) is None
        with pytest.raises(AttributeError, match="lifespan"):
            _ = main.service

        client = TestClient(app)
        assert getattr(client.app.state, "portfolio_service", None) is None
        resp = client.post(
            "/risk/summary",
            json=SAMPLE_PORTFOLIO.model_dump(mode="json"),
        )
        assert resp.status_code == 503, resp.text
    finally:
        for attr, value in saved.items():
            setattr(app.state, attr, value)
