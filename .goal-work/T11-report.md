# T11 — Secret and boundary regression tests

## Status

Complete.

## Changes

- Added `backend/tests/test_ai_security.py` with sentinel-key absence checks (API, repr, errors, logs), frontend source scan, MCP credential scan, zero-tool boundary cases (unknown/extra/injection), and network-free deterministic mode proof.
- Updated `docs/ai/TASKS.md` T11 checks to use `tests/test_wave_c_mcp.py` (repository MCP test filename).

## Acceptance

| Criterion | Result |
|-----------|--------|
| Sentinel key absent from API, exceptions, reprs, logs | Parametrized assertions on settings, `/api/v1/risk/query`, provider errors, caplog |
| Frontend has no `OPENAI_API_KEY` or `VITE_OPENAI` | `frontend/src` source scan |
| MCP tool lists/args contain no model credential | `list_tools()` JSON scan in `test_ai_security.py`; existing allowlist tests in `test_wave_c_mcp.py` |
| Unknown/extra/injection execute zero tools | MCP + deterministic/model-path parametrized cases |
| Deterministic mode network-free | `socket.socket` blocked; `OpenAI` ctor not called |

## Checks

```bash
cd backend
python3 -m pytest tests/test_ai_security.py tests/test_wave_c_mcp.py tests/test_ai_query_orchestration.py -q
cd ../frontend
npm test -- --run src/components/RiskQuery.test.jsx
```

Result: 46 backend passed, 5 frontend passed.

Commit: `e41a299`.

## Concerns

- Frontend scan is static (source text); bundle analysis deferred to T13/T15 gates.
- MCP credential check is structural; live stdio MCP is covered indirectly via `test_wave_c_mcp.py`.
