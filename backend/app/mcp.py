"""Wave C G2 — thin MCP server over TOOL_CONTRACTS.

Registers allowlisted tools only. Dispatches through ``validate_tool_call`` and
``execute_allowlisted_tool``. No live LLM. No pricing-library or VaR / stress /
DV01 formulas. FastAPI ``app.main`` does not import this module (AD-C8).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from pydantic import BaseModel

from app.api.acl import PortfolioAccessDenied
from app.api.auth import (
    UNAUTHORIZED_MESSAGE,
    is_shared_deployment,
    principal_for_bearer,
)
from app.api.errors import (
    PUBLIC_BAD_REQUEST_MESSAGE,
    PUBLIC_FORBIDDEN_MESSAGE,
    error_payload,
)
from app.risk.query import (
    TOOL_CONTRACTS,
    tool_json_schemas,
    validate_tool_call,
)
from app.risk.tool_contracts import execute_allowlisted_tool
from app.services.risk_run_service import RiskRunNotFound


class McpCallResult(BaseModel):
    """Typed MCP tool outcome. Failures are ErrorBody, never estimated numbers."""

    ok: bool
    tool_name: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class ThinMcpServer(BaseModel):
    """In-process MCP facade. Portfolio is bound here, never by the caller/model."""

    model_config = {"arbitrary_types_allowed": True}

    service: Any
    portfolio: Any = None

    def list_tools(self) -> list[dict[str, Any]]:
        return list_tools()

    def call_tool(
        self,
        name: str | None,
        arguments: dict[str, Any] | None = None,
        *,
        authorization: str | None = None,
    ) -> McpCallResult:
        principal, auth_error = _principal_or_error(authorization)
        if auth_error is not None:
            return McpCallResult(ok=False, tool_name=name, error=auth_error)

        checked = validate_tool_call(name, arguments or {})
        if not checked.allowed or checked.tool_name is None:
            return McpCallResult(
                ok=False,
                tool_name=name,
                error=_refusal_error(checked.refusal),
            )
        try:
            payload = execute_allowlisted_tool(
                checked.tool_name.value,
                self.portfolio,
                self.service,
                checked.args,
                principal=principal,
            )
        except PortfolioAccessDenied:
            return McpCallResult(
                ok=False,
                tool_name=checked.tool_name.value,
                error=error_payload(code="forbidden", message=PUBLIC_FORBIDDEN_MESSAGE),
            )
        except RiskRunNotFound as exc:
            return McpCallResult(
                ok=False,
                tool_name=checked.tool_name.value,
                error=error_payload(
                    code="not_found",
                    message=f"risk run not found: {exc.run_id}",
                ),
            )
        except ValueError:
            return McpCallResult(
                ok=False,
                tool_name=checked.tool_name.value,
                error=error_payload(code="bad_request", message=PUBLIC_BAD_REQUEST_MESSAGE),
            )
        return McpCallResult(
            ok=True,
            tool_name=checked.tool_name.value,
            result=payload,
        )


def list_tools() -> list[dict[str, Any]]:
    """Discover TOOL_CONTRACTS only — names, JSON schemas, methodology/unit text."""
    schemas = tool_json_schemas()
    tools: list[dict[str, Any]] = []
    for contract in TOOL_CONTRACTS.values():
        name = contract.name.value
        schema = schemas[name]
        description = _tool_description(contract)
        tools.append(
            {
                "name": name,
                "description": description,
                "inputSchema": schema,
                "json_schema": schema,
                "numeric_source": contract.numeric_source,
                "http_path": contract.http_path,
                "provenance_fields": list(contract.provenance_fields),
                "service_method": contract.service_method,
            }
        )
    return tools


def handle_jsonrpc(
    message: dict[str, Any],
    *,
    server: ThinMcpServer,
    authorization: str | None = None,
) -> dict[str, Any] | None:
    """Minimal JSON-RPC 2.0 handler for optional stdio (C5 documents the entry)."""
    if not isinstance(message, dict):
        return _rpc_error(None, -32600, "Invalid Request")
    rpc_id = message.get("id")
    method = message.get("method")
    if message.get("jsonrpc") != "2.0" or not method:
        return _rpc_error(rpc_id, -32600, "Invalid Request")
    if method == "notifications/initialized" or (
        rpc_id is None and str(method).startswith("notifications/")
    ):
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "quantlineage", "version": "0.3.0"},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "tools": [
                    {
                        "name": item["name"],
                        "description": item["description"],
                        "inputSchema": item["inputSchema"],
                    }
                    for item in server.list_tools()
                ]
            },
        }
    if method == "tools/call":
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return _rpc_error(rpc_id, -32602, "Invalid params")
        outcome = server.call_tool(
            params.get("name"),
            params.get("arguments") or {},
            authorization=authorization,
        )
        body = outcome.result if outcome.ok else outcome.error
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(body, default=str)}],
                "isError": not outcome.ok,
            },
        }
    return _rpc_error(rpc_id, -32601, "Method not found")


def main() -> int:
    """Optional stdio entry: ``python -m app.mcp``. Does not start an LLM daemon."""
    authorization = os.environ.get("QUANTLINEAGE_MCP_AUTHORIZATION")
    server = ThinMcpServer(service=_default_service(), portfolio=_default_portfolio())
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_rpc_error(None, -32700, "Parse error")) + "\n")
            sys.stdout.flush()
            continue
        response = handle_jsonrpc(message, server=server, authorization=authorization)
        if response is not None:
            sys.stdout.write(json.dumps(response, default=str) + "\n")
            sys.stdout.flush()
    return 0


def _tool_description(contract: Any) -> str:
    provenance = ", ".join(contract.provenance_fields) or "none"
    return (
        f"{contract.description} "
        f"numeric_source={contract.numeric_source}. "
        f"http_path={contract.http_path or 'none'}. "
        f"provenance_fields={provenance}."
    )


def _principal_or_error(authorization: str | None) -> tuple[str | None, dict[str, Any] | None]:
    """Reuse RF-014 shared-token rules. Local demo stays unauthenticated."""
    if not is_shared_deployment():
        return None, None
    principal = principal_for_bearer(authorization)
    if principal is None:
        return None, error_payload(code="unauthorized", message=UNAUTHORIZED_MESSAGE)
    return principal, None


def _refusal_error(refusal: str | None) -> dict[str, Any]:
    message = refusal or PUBLIC_BAD_REQUEST_MESSAGE
    code = "validation_error" if "JSON-schema" in message else "bad_request"
    return error_payload(code=code, message=message)


def _rpc_error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _default_portfolio():
    from app.sample import SAMPLE_PORTFOLIO

    return SAMPLE_PORTFOLIO


def _default_service():
    """Lazy process wiring for stdio. Tests inject fixtures instead."""
    from app.services.risk_factories import build_portfolio_service
    from app.services.risk_run_worker import RiskRunWorker

    portfolio_service = build_portfolio_service()
    worker = RiskRunWorker(portfolio_service)
    worker.ensure_running()
    portfolio_service.risk_run_compare = worker.compare_runs
    return _StdioToolService(portfolio_service=portfolio_service, worker=worker)


class _StdioToolService:
    """Delegates MCP getattr names to existing worker / catalog / showcase helpers."""

    def __init__(self, *, portfolio_service: Any, worker: Any) -> None:
        self._portfolio_service = portfolio_service
        self._worker = worker

    def search_catalog(self, query: str):
        from app.market.catalog.service import search_catalog

        return search_catalog(query)

    def get(self, run_id: str, *, principal: str | None = None):
        return self._worker.get(run_id, principal=principal)

    def submit(self, **kwargs: Any):
        return self._worker.submit(**kwargs)

    def compare_runs(self, t0_run_id: str, t1_run_id: str, **kwargs: Any):
        return self._worker.compare_runs(t0_run_id, t1_run_id, **kwargs)

    def get_run_provenance(self, run_id: str, *, principal: str | None = None):
        view = self._worker.get(run_id, principal=principal)
        provenance = getattr(view, "provenance", None)
        if provenance is None:
            raise RiskRunNotFound(run_id)
        return provenance

    def build_rates_showcase(self):
        from app.risk.rates_showcase import build_rates_showcase
        from app.sample import RATES_MACRO_PORTFOLIO, demo_market_snapshot

        book = RATES_MACRO_PORTFOLIO
        return build_rates_showcase(
            book, demo_market_snapshot(book), self._portfolio_service.pricing
        )

    def summary(self, portfolio):
        return self._portfolio_service.summary(portfolio)

    def var_report(self, portfolio):
        return self._portfolio_service.var_report(portfolio)

    def threat_evaluation(self, portfolio):
        return self._portfolio_service.threat_evaluation(portfolio)

    def limits(self, portfolio):
        return self._portfolio_service.limits(portfolio)

    def contributors(self, portfolio):
        return self._portfolio_service.contributors(portfolio)


if __name__ == "__main__":
    raise SystemExit(main())
