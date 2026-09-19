# QuantLineage MCP (Wave C)

Thin, **allowlist-only** MCP over existing deterministic tools. The server
registers `TOOL_CONTRACTS` from `app.risk.query` and dispatches through
`validate_tool_call` + `execute_allowlisted_tool`. It does not compute VaR, ES,
DV01, stress, or other risk numbers.

**No embedded LLM.** `backend/app/mcp.py` does not import the OpenAI SDK, does
not read `OPENAI_API_KEY`, and does not host a model. External MCP clients (for
example Cursor or Claude Desktop) may attach their own LLM; QuantLineage still
only executes allowlisted tools server-side.

The FastAPI app (`app.main`) does **not** import MCP (AD-C8). Core HTTP risk
APIs run with MCP unused.

## Stdio entry

From `backend` (venv activated, `PYTHONPATH=.`):

```bash
python -m app.mcp
```

JSON-RPC 2.0 on stdin/stdout, one object per line. Methods:

- `initialize`
- `tools/list` — allowlisted tools only (name, description, JSON Schema)
- `tools/call` — `{ "name": "<tool>", "arguments": { ... } }`

Unknown tools, extra keys, and domain errors return typed `ErrorBody` payloads
inside `tools/call` (`isError: true`). They never include estimated numbers.

## Auth

Reuse existing Bearer mapping (RF-014):

- Local / loopback: unauthenticated, same as HTTP demo.
- Shared deployment: send `Authorization: Bearer …` on `tools/call`, or set
  `QUANTLINEAGE_MCP_AUTHORIZATION` for the stdio process (for example
  `Bearer <token>`).

The MCP layer does not add a second token scheme.

## Client config (Cursor / Claude Desktop style)

```json
{
  "mcpServers": {
    "quantlineage": {
      "command": "python",
      "args": ["-m", "app.mcp"],
      "cwd": "backend",
      "env": {
        "PYTHONPATH": ".",
        "QUANTLINEAGE_MCP_AUTHORIZATION": "Bearer <token-if-shared>"
      }
    }
  }
}
```

Point `command` at the same interpreter as `backend/.venv` when you are not on
PATH. Do not add network, SQL, or shell commands to this config.

## Minimal stdio client

`docs/examples/mcp_stdio_client.py` launches `python -m app.mcp`, lists tools,
and calls `search_instruments`. Run from `backend`:

```bash
PYTHONPATH=. python ../docs/examples/mcp_stdio_client.py
```

## What this is not

- Not a model host and not a place for API keys. Do not set `OPENAI_API_KEY` or
  `AI_*` in MCP client `env` — those belong on the HTTP backend
  only (see [`docs/openai_risk_assistant.md`](openai_risk_assistant.md)).
- Clients may attach their own LLM elsewhere; QuantLineage MCP still only
  executes allowlisted tools.
- Not a rewrite of MCP internals (`backend/app/mcp.py` stays the thin facade).
- Not a path to invent risk figures when a tool refuses or fails.
