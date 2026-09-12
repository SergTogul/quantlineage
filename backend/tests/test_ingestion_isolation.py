"""G1: quant core must not import Yahoo/FRED adapters; adapters stay off FastAPI."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN_ADAPTERS = frozenset(
    {
        "app.market.ingestion.yahoo",
        "app.market.ingestion.fred",
    }
)
QUANT_PACKAGES = ("risk", "pricing")
CORE_MODULES = (
    "app.risk.historical",
    "app.risk.historical_data",
    "app.risk.factor_panel",
    "app.pricing",
)


def _import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_risk_and_pricing_sources_do_not_import_provider_adapters() -> None:
    offenders: list[str] = []
    for package in QUANT_PACKAGES:
        for py in (APP_ROOT / package).rglob("*.py"):
            imported = _import_targets(py)
            hit = imported & FORBIDDEN_ADAPTERS
            if hit:
                offenders.append(f"{py.relative_to(APP_ROOT.parent)}: {sorted(hit)}")
    assert not offenders, "quant core imported provider adapters:\n" + "\n".join(offenders)


def test_importing_quant_core_does_not_load_adapter_modules() -> None:
    """Runtime check: importing risk/pricing must not pull adapter modules.

    Other ingestion tests may already have loaded adapters; drop them first so
    this pin observes the import graph of the quant modules themselves.
    """
    for name in list(sys.modules):
        if name == "app.market.ingestion" or name.startswith("app.market.ingestion."):
            del sys.modules[name]
        if name in CORE_MODULES or name.startswith("app.risk.") or name.startswith("app.pricing."):
            del sys.modules[name]

    import app.pricing  # noqa: F401
    import app.risk.factor_panel  # noqa: F401
    import app.risk.historical  # noqa: F401
    import app.risk.historical_data  # noqa: F401

    loaded = sorted(name for name in FORBIDDEN_ADAPTERS if name in sys.modules)
    assert loaded == [], f"quant import loaded adapters: {loaded}"


def test_ingestion_models_and_protocols_do_not_import_httpx_or_fastapi() -> None:
    for rel in (
        "market/ingestion/models.py",
        "market/ingestion/errors.py",
        "market/ingestion/protocols.py",
    ):
        imported = _import_targets(APP_ROOT / rel)
        roots = {name.split(".", 1)[0] for name in imported}
        assert "httpx" not in roots, rel
        assert "fastapi" not in roots, rel
        assert "app.market.ingestion.yahoo" not in imported
        assert "app.market.ingestion.fred" not in imported


def test_adapters_do_not_import_risk_pricing_or_fastapi() -> None:
    for rel in (
        "market/ingestion/yahoo.py",
        "market/ingestion/fred.py",
        "market/ingestion/http.py",
        "market/ingestion/normalize.py",
    ):
        imported = _import_targets(APP_ROOT / rel)
        assert "fastapi" not in {name.split(".", 1)[0] for name in imported}, rel
        for name in imported:
            assert not name.startswith("app.risk"), f"{rel} imports {name}"
            assert not name.startswith("app.pricing"), f"{rel} imports {name}"
