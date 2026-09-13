"""R0.9.1 / RF-010: HTTP request/response bodies live in api/schemas, not domain."""
from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parents[1] / "app" / "domain"
MODELS_PATH = DOMAIN_ROOT / "models.py"

# Obvious HTTP bodies. Dual-use engine/service inputs (AttributionRequest,
# RiskChangeAttributionRequest, WhatIfRequest) stay in domain for this slice.
HTTP_TRANSPORT_NAMES = frozenset(
    {
        "CustomStressRequest",
        "ReverseStressRequest",
        "MultiFactorReverseStressRequest",
        "ScenarioComparisonRequest",
        "LimitDrilldownRequest",
        "RiskQueryRequest",
        "RiskQueryResponse",
        "RiskRunRequestBody",
        "SummaryRiskRunRequest",
        "VarRiskRunRequest",
        "DashboardRiskRunRequest",
        "GenericRiskRunRequest",
        "StressEvaluateRiskRunRequest",
        "StressRunRequest",
        "ReverseStressRiskRunRequest",
        "ReverseStressMultiRiskRunRequest",
        "StressCompareRiskRunRequest",
        "QueryRiskRunRequest",
        "AttributionRiskRunRequest",
        "ChangeAttributionRiskRunRequest",
        "EsRiskRunRequest",
        "VarCompareRiskRunRequest",
        "AttributionDemoRiskRunRequest",
        "RiskRunCompareRequest",
        "RiskRunCreateRequest",
        "RiskRunResultView",
        "RiskRunView",
        "parse_risk_run_request",
        "dump_risk_run_request",
        "RISK_RUN_REQUEST_SCHEMAS",
    }
)


def _top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_domain_package_does_not_import_fastapi() -> None:
    offenders: list[str] = []
    for path in sorted(DOMAIN_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                if module == "fastapi" or module.startswith("fastapi.") or module.startswith("app.api"):
                    offenders.append(f"{path.name}:{module}")
    assert not offenders, f"domain must not import fastapi/api transport: {offenders}"


def test_domain_models_does_not_define_http_transport_bodies() -> None:
    leftover = HTTP_TRANSPORT_NAMES & _top_level_names(MODELS_PATH)
    assert not leftover, f"HTTP transport types still in domain.models: {sorted(leftover)}"


def test_http_transport_bodies_live_in_api_schemas() -> None:
    from app.api import schemas

    missing = [name for name in sorted(HTTP_TRANSPORT_NAMES) if not hasattr(schemas, name)]
    assert not missing, f"api.schemas missing HTTP transport names: {missing}"


def test_moved_http_bodies_keep_forbid_and_json_field_names() -> None:
    from app.api.schemas import (
        CustomStressRequest,
        RiskQueryRequest,
        RiskRunCreateRequest,
        RiskRunRequestBody,
    )

    assert set(CustomStressRequest.model_fields) == {"portfolio", "scenarios"}
    assert set(RiskQueryRequest.model_fields) == {"portfolio", "question"}
    assert set(RiskRunCreateRequest.model_fields) == {
        "portfolio",
        "run_type",
        "request",
        "market_snapshot_id",
    }
    assert RiskRunCreateRequest.model_config.get("extra") == "forbid"
    assert RiskRunRequestBody.model_config.get("extra") == "forbid"


def test_portfolio_service_does_not_import_api_schemas() -> None:
    """Finding 13: PortfolioService must not import HTTP transport bodies."""
    path = Path(__file__).resolve().parents[1] / "app" / "services" / "portfolio_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        for module in modules:
            if module == "app.api.schemas" or module.startswith("app.api.schemas."):
                offenders.append(module)
    assert not offenders, f"portfolio_service must not import api.schemas: {offenders}"
