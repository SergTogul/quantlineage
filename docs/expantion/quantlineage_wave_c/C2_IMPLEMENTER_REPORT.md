# Task C2 Report — Thin MCP server (Wave C G2)

## Task
Wave C C2: thin MCP server that registers only `TOOL_CONTRACTS` and dispatches via `validate_tool_call` + `execute_allowlisted_tool`. No live LLM. No quant math in MCP. No `docs/mcp.md` (C5). No C3 orchestration rewrite. Do not mark G2 DONE.

## Owner
MCP Agent (one implementer).

## Status
**C2 IN_PROGRESS** (implementer complete; independent G2 review not claimed). G2 remains **NOT_STARTED**.

## Summary
Added `app.mcp` as an optional thin MCP facade over the C1 allowlist. Tool discovery is exactly `TOOL_CONTRACTS` (JSON Schema plus `numeric_source` / `http_path` / provenance text from contracts). Valid calls return the existing service payload. Unknown tools and extra keys return `ErrorBody` with RF-019 refusal strings, never estimated numbers. Shared-deployment Bearer mapping reuses RF-014 (`principal_for_bearer` / `is_shared_deployment`); `principal` is passed into `submit` (`owner=`), `get`, and `compare_runs` only when the injected callable accepts those kwargs. FastAPI `app.main` does not import MCP. Optional stdio: `python -m app.mcp`.

## Commits
Included in this Wave C C2 commit (`feat(wave-c): add thin allowlisted MCP server`).

## Files changed
- `backend/app/mcp.py` (new) — `list_tools`, `ThinMcpServer.call_tool`, JSON-RPC/stdio entry
- `backend/app/risk/tool_contracts.py` — optional `principal` plumbing; RF-019 names dispatch through the same function; dict `hits` unwrap for catalog search
- `backend/app/risk/query.py` — `_execute_tool` delegates to `execute_allowlisted_tool` (no second dispatcher)
- `backend/tests/test_wave_c_mcp.py` (new)
- `docs/expantion/quantlineage_wave_c/TRACKER.md` (G1 DONE / C2 IN_PROGRESS; G2 still NOT_STARTED)
- `docs/expantion/quantlineage_wave_c/C2_IMPLEMENTER_REPORT.md` (this tracked copy)
- `.superpowers/sdd/task-c2-report.md` (local; `.superpowers/sdd/` is gitignored)

## Public / interface changes
- `list_tools()` / `ThinMcpServer.call_tool` over `TOOL_CONTRACTS` only
- `execute_allowlisted_tool(..., *, principal=None)` — inspect-filtered `owner`/`principal` kwargs
- Optional `python -m app.mcp` JSON-RPC stdio (no extra dependency, no LLM daemon)
- No HTTP routes added. No `docs/mcp.md`. Keyword `RiskQueryEngine.route` unchanged (C3)

## Numerical conventions
- Unchanged. MCP dumps service payloads; it does not compute VaR/ES/DV01/stress.
- Units and sign conventions come from contract `numeric_source` / provenance fields and stored payloads.

## Tests added/updated
- `test_list_tools_is_allowlist_only`
- `test_valid_search_instruments_get_risk_run_and_compare`
- `test_extra_keys_and_unknown_tool_are_typed_errors`
- `test_mcp_module_has_no_llm_or_quant_formula`
- `test_fastapi_main_imports_when_mcp_unused`
- `test_shared_token_rules_pass_principal_into_worker`
- `test_domain_errors_map_to_error_body_not_numbers`
- `test_principal_omitted_when_worker_has_no_acl_kwarg`
- Existing `tests/test_wave_c_tool_contracts.py` and `tests/test_ai_query_orchestration.py` still passing

## Commands executed

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line tests/test_wave_c_mcp.py tests/test_wave_c_tool_contracts.py tests/test_ai_query_orchestration.py
.venv/bin/ruff check app/mcp.py app/risk/query.py app/risk/tool_contracts.py tests/test_wave_c_mcp.py
```

## Results
- Backend C2 + C1 + RF-019: **43 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Ruff on touched Python: **All checks passed**
- Frontend: not in scope
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes**
- Unexplained failures or skips: none
- CI is green: not started (C2 local; G2 not claimed)

## Known limitations / risks
- Default stdio composite wires worker + catalog search + rates-showcase + RF-019 PortfolioService methods. `get_market_history` / `get_data_quality` still require an injected service method (C1 dispatch honesty); missing methods map to `bad_request` / `Invalid request`, not invented levels.
- Shared-profile MCP calls need `Authorization: Bearer` (or `QUANTLINEAGE_MCP_AUTHORIZATION` for stdio). Local loopback stays unauthenticated, matching HTTP.
- Keyword router still only selects RF-019 tools; C1 names are registered for MCP / `answer_with_model`, not NL keywords (C3).
- `docs/mcp.md` and UI client config are C5.

## Follow-up / next owner
- Owner: Independent reviewer (G2), then AI Orchestration Agent (C3)
- Requested action: review thin MCP; do not mark G2 DONE from this implementer report. C3 must not invent tools or numbers.
- Blocking?: no
