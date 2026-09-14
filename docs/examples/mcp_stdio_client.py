#!/usr/bin/env python3
"""Minimal stdio client for ``python -m app.mcp``. No live LLM.

Run from ``backend``::

    PYTHONPATH=. python ../docs/examples/mcp_stdio_client.py

Auth for shared deployments: export ``QUANTLINEAGE_MCP_AUTHORIZATION``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


def _rpc(proc: subprocess.Popen[str], method: str, params: dict[str, Any] | None, rpc_id: int) -> dict[str, Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        message["params"] = params
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("MCP stdio closed")
    return json.loads(line)


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", ".")
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        init = _rpc(
            proc,
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "quantlineage-example"}},
            1,
        )
        listed = _rpc(proc, "tools/list", None, 2)
        call = _rpc(
            proc,
            "tools/call",
            {"name": "search_instruments", "arguments": {"query": "AAPL"}},
            3,
        )
        print(json.dumps({"initialize": init.get("result"), "tools": listed.get("result"), "call": call.get("result")}, indent=2, default=str))
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
