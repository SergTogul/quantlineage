"""Wave C G2 — thin MCP server over TOOL_CONTRACTS. No LLM, no quant math."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

from app.api.acl import PortfolioAccessDenied
from app.api.auth import ENV_API_TOKEN, ENV_API_TOKENS, ENV_SHARED_DEPLOYMENT
from app.risk.query import TOOL_CONTRACTS, RiskToolName
from app.sample import SAMPLE_PORTFOLIO
from app.services.risk_run_service import RiskRunNotFound

_MCP_MODULE = Path(__file__).resolve().parents[1] / "app" / "mcp.py"
_MAIN_MODULE = Path(__file__).resolve().parents[1] / "app" / "main.py"

_BANNED_QUANT = ("QuantLib", "quantlib", "BlackScholes", "Actual365", "ql.")
_BANNED_LLM = ("openai", "anthropic", "litellm", "langchain")
_FORBIDDEN_TOOLS = frozenset(
    {"shell", "shell_exec", "sql", "filesystem", "http", "http_request", "invent_var"}
)


class _McpFixtureService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.principals: list[str | None] = []

    def search_catalog(self, query: str):
        self.calls.append(("search_catalog", query))
        return {
            "hits": [
                {
                    "instrument_id": "equity:US:AAPL",
                    "display_name": "Apple Inc.",
                    "provider": "catalog",
                    "source_symbol": "AAPL",
                }
            ]
        }

    def get(self, run_id: str, *, principal: str | None = None):
        self.calls.append(("get", run_id, principal))
        self.principals.append(principal)
        if run_id == "missing":
            raise RiskRunNotFound(run_id)
        if run_id == "forbidden":
            raise PortfolioAccessDenied("book-1")
        return {
            "id": run_id,
            "status": "COMPLETED",
            "run_type": "var",
            "market_snapshot_id": "snap-1",
            "methodology": "DELTA_GAMMA",
        }

    def compare_runs(
        self,
        t0_run_id: str,
        t1_run_id: str,
        *,
        metric: str = "var_99",
        principal: str | None = None,
    ):
        self.calls.append(("compare_runs", t0_run_id, t1_run_id, metric, principal))
        self.principals.append(principal)
        return {
            "t0_run_id": t0_run_id,
            "t1_run_id": t1_run_id,
            "metric": metric,
            "previous_risk": 100.0,
            "current_risk": 140.0,
            "total_change": 40.0,
            "residual": 1.0,
            "unit": "currency",
            "sign_convention": "loss",
        }

    def submit(
        self,
        *,
        portfolio,
        run_type: str = "summary",
        request=None,
        market_snapshot_id=None,
        owner=None,
    ):
        self.calls.append(("submit", run_type, owner))
        self.principals.append(owner)
        return {
            "id": "run-new",
            "portfolio_id": portfolio.id,
            "status": "QUEUED",
            "run_type": run_type,
            "owner": owner,
            "request": request or {},
            "market_snapshot_id": market_snapshot_id,
        }


def _server(service=None):
    from app.mcp import ThinMcpServer

    return ThinMcpServer(service=service or _McpFixtureService(), portfolio=SAMPLE_PORTFOLIO)


def _clear_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_SHARED_DEPLOYMENT, raising=False)
    monkeypatch.delenv(ENV_API_TOKEN, raising=False)
    monkeypatch.delenv(ENV_API_TOKENS, raising=False)


def test_list_tools_is_allowlist_only() -> None:
    from app.mcp import list_tools

    tools = list_tools()
    names = {item["name"] for item in tools}
    allowlist = {name.value for name in TOOL_CONTRACTS}
    assert names <= allowlist
    assert names == allowlist
    assert names.isdisjoint(_FORBIDDEN_TOOLS)
    schemas = {item["name"]: item["inputSchema"] for item in tools}
    for name, schema in schemas.items():
        contract = TOOL_CONTRACTS[RiskToolName(name)]
        row = next(item for item in tools if item["name"] == name)
        assert row["numeric_source"] == contract.numeric_source
        assert row["http_path"] == contract.http_path
        assert row["provenance_fields"] == contract.provenance_fields
        assert contract.numeric_source in row["description"]
        assert schema["type"] == "object"
        assert schema.get("additionalProperties") is False


def test_valid_search_instruments_get_risk_run_and_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth(monkeypatch)
    service = _McpFixtureService()
    server = _server(service)

    search = server.call_tool("search_instruments", {"query": "AAPL"})
    assert search.ok
    assert search.error is None
    assert search.result["hits"][0]["instrument_id"] == "equity:US:AAPL"
    assert service.calls[0] == ("search_catalog", "AAPL")

    run = server.call_tool("get_risk_run", {"run_id": "run-t1"})
    assert run.ok
    assert run.result["id"] == "run-t1"
    assert run.result["status"] == "COMPLETED"

    compare = server.call_tool(
        "compare_risk_runs",
        {"t0_run_id": "run-t0", "t1_run_id": "run-t1", "metric": "var_99"},
    )
    assert compare.ok
    assert compare.result["residual"] == 1.0
    assert compare.result["unit"] == "currency"
    assert service.calls[-1][0] == "compare_runs"


def test_extra_keys_and_unknown_tool_are_typed_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth(monkeypatch)
    service = _McpFixtureService()
    server = _server(service)

    extra = server.call_tool("search_instruments", {"query": "AAPL", "url": "http://evil"})
    assert not extra.ok
    assert extra.result is None
    assert extra.error is not None
    assert extra.error["code"] == "validation_error"
    assert "JSON-schema" in extra.error["message"]

    unknown = server.call_tool("invent_var", {"value": 99})
    assert not unknown.ok
    assert unknown.result is None
    assert unknown.error["code"] == "bad_request"
    assert "allowlist" in unknown.error["message"].lower()
    assert service.calls == []


def test_mcp_module_has_no_llm_or_quant_formula() -> None:
    text = _MCP_MODULE.read_text(encoding="utf-8")
    for token in (*_BANNED_QUANT, *_BANNED_LLM):
        assert token not in text, f"{token} found in MCP module"
    tree = ast.parse(text)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(_BANNED_LLM)
    assert "QuantLib" not in imported
    sys.modules.pop("app.mcp", None)
    sys.modules.pop("openai", None)
    importlib.import_module("app.mcp")
    assert "openai" not in sys.modules


def test_c5_mcp_docs_exist_and_omit_forbidden_tools() -> None:
    docs = Path(__file__).resolve().parents[2] / "docs" / "mcp.md"
    assert docs.is_file()
    text = docs.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "python -m app.mcp" in lowered
    assert "riskforge_mcp_authorization" in lowered
    assert "allowlist" in lowered
    for banned in ("shell_exec", "sql tool", "filesystem tool", "general http", "yahoo"):
        assert banned not in lowered
    assert "live llm" not in lowered or "no live llm" in lowered


def test_fastapi_main_imports_when_mcp_unused() -> None:
    source = _MAIN_MODULE.read_text(encoding="utf-8")
    assert "app.mcp" not in source
    assert "from app import mcp" not in source
    sys.modules.pop("app.mcp", None)
    from app.main import app

    assert app.title
    assert "app.mcp" not in sys.modules


def test_shared_token_rules_pass_principal_into_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_SHARED_DEPLOYMENT, "1")
    monkeypatch.setenv(ENV_API_TOKEN, "mcp-secret")
    service = _McpFixtureService()
    server = _server(service)

    denied = server.call_tool("get_risk_run", {"run_id": "run-t1"})
    assert not denied.ok
    assert denied.error["code"] == "unauthorized"
    assert service.calls == []

    ok = server.call_tool(
        "get_risk_run",
        {"run_id": "run-t1"},
        authorization="Bearer mcp-secret",
    )
    assert ok.ok
    assert service.principals[-1] == "shared"

    compare = server.call_tool(
        "compare_risk_runs",
        {"t0_run_id": "run-t0", "t1_run_id": "run-t1"},
        authorization="Bearer mcp-secret",
    )
    assert compare.ok
    assert service.principals[-1] == "shared"

    submitted = server.call_tool(
        "run_portfolio_risk",
        {"run_type": "var"},
        authorization="Bearer mcp-secret",
    )
    assert submitted.ok
    assert ("submit", "var", "shared") in service.calls


def test_domain_errors_map_to_error_body_not_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth(monkeypatch)
    server = _server()
    missing = server.call_tool("get_risk_run", {"run_id": "missing"})
    assert not missing.ok
    assert missing.result is None
    assert missing.error["code"] == "not_found"
    assert "missing" in missing.error["message"]
    assert "var_99" not in (missing.error["message"] or "")

    forbidden = server.call_tool("get_risk_run", {"run_id": "forbidden"})
    assert not forbidden.ok
    assert forbidden.result is None
    assert forbidden.error["code"] == "forbidden"


def test_principal_omitted_when_worker_has_no_acl_kwarg(monkeypatch: pytest.MonkeyPatch) -> None:
    """C1 fixtures without principal still execute (inspect-filter)."""
    from app.risk.tool_contracts import execute_allowlisted_tool

    _clear_auth(monkeypatch)

    class _NoPrincipal:
        def get(self, run_id: str):
            return {"id": run_id, "status": "COMPLETED"}

        def compare_runs(self, t0_run_id: str, t1_run_id: str, metric: str = "var_99"):
            return {"t0_run_id": t0_run_id, "t1_run_id": t1_run_id, "metric": metric, "residual": 0.0}

        def submit(self, *, portfolio, run_type: str = "summary", request=None, market_snapshot_id=None):
            return {"id": "x", "run_type": run_type, "status": "QUEUED"}

    service = _NoPrincipal()
    got = execute_allowlisted_tool(
        "get_risk_run", SAMPLE_PORTFOLIO, service, {"run_id": "r1"}, principal="alice"
    )
    assert got["id"] == "r1"
    compared = execute_allowlisted_tool(
        "compare_risk_runs",
        SAMPLE_PORTFOLIO,
        service,
        {"t0_run_id": "a", "t1_run_id": "b", "metric": "var_99"},
        principal="alice",
    )
    assert compared["residual"] == 0.0
    queued = execute_allowlisted_tool(
        "run_portfolio_risk",
        SAMPLE_PORTFOLIO,
        service,
        {"run_type": "summary"},
        principal="alice",
    )
    assert queued["status"] == "QUEUED"
