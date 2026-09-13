# Task C3 Report — Intent / orchestration / clarification (Wave C G3)

## Task
Wave C C3: map the C3 intent taxonomy onto the C1 allowlist (`TOOL_CONTRACTS` only). Ambiguity clarifies. Model/`route` output cannot create arbitrary tool names. Tool failure must not invent VaR/ES/DV01. Do not mark G3 DONE. No `docs/mcp.md`. No C4 explanation cards. No C5 UI.

## Owner
AI Orchestration Engineer (one implementer).

## Status
**C3 IN_PROGRESS** (implementer complete; independent G3 review not claimed). G3 remains **NOT_STARTED**.

## Summary
Extended keyword `RiskQueryEngine.route` so C1 names are reachable without an LLM: instrument discovery → `search_instruments`, history → `get_market_history` (clarifies without instrument/range), portfolio risk enqueue → `run_portfolio_risk` (RF-019 `get_var_es` / `get_portfolio_summary` unchanged), named stress → `run_stress` (RF-019 worst-stress unchanged), enqueue contributors → `get_top_risk_contributors` (RF-019 `get_contributors` still pinned), compare → `compare_risk_runs`, risk-change → `explain_risk_change`, provenance → `get_run_provenance`. Missing t0/t1 still clarifies and does not invent run ids. Unknown model tool names still fail `validate_tool_call`. `ValueError` / missing method returns a typed ungrounded clarification with no digits. Optional `principal` is forwarded through `_execute_tool` into `execute_allowlisted_tool`.

## Commits
Included in this Wave C C3 commit (`feat(wave-c): map C3 intents onto allowlisted tools`).

## Files changed
- `backend/app/risk/query.py` — C3 keyword routing, `RiskQueryPlan.tool_args`, tool-failure grounding, `principal` on `answer` / `answer_with_model` / `_execute_tool`
- `backend/tests/test_wave_c_orchestration.py` (new)
- `docs/expantion/quantlineage_wave_c/TRACKER.md` (G2 DONE / C3 IN_PROGRESS; G3 still NOT_STARTED)
- `docs/expantion/quantlineage_wave_c/C3_IMPLEMENTER_REPORT.md` (this tracked copy)
- `.superpowers/sdd/task-c3-report.md` (local; `.superpowers/sdd/` is not part of the commit)

## Public / interface changes
- `RiskQueryPlan.tool_args` carries extracted allowlisted args
- Keyword `route()` can select C1 `RiskToolName` values, still gated by `validate_tool_call`
- `answer(..., *, principal=None)` and `answer_with_model(..., *, principal=None)`
- `_execute_tool(..., *, principal=None)` → `execute_allowlisted_tool`
- `DeterministicRiskAssistantModel` forwards `plan.tool_args`
- No HTTP routes added. No `docs/mcp.md`. No C4 card formatter. No C5 UI
- G3 not marked DONE

## Numerical conventions
- Unchanged. Orchestration dumps service payloads; it does not compute VaR/ES/DV01/stress.
- Ungrounded paths (`SAFE_UNGROUNDED_ANSWER`, tool-failure text, missing-id clarifications) contain no digits.

## Tests added/updated
- `test_c3_each_intent_routes_to_allowlisted_tool_or_clarification`
- `test_c3_search_apple_executes_search_instruments`
- `test_c3_history_without_instrument_or_range_clarifies`
- `test_c3_history_with_instrument_and_range_executes`
- `test_c3_missing_t0_t1_clarifies_and_does_not_invent_run_ids`
- `test_c3_compare_with_two_run_ids_executes`
- `test_c3_equity_down_stress_uses_allowlisted_scenario`
- `test_c3_run_portfolio_risk_and_enqueue_contributors`
- `test_c3_provenance_without_run_id_clarifies`
- `test_c3_provenance_with_run_id_executes`
- `test_c3_two_possible_tools_clarify_without_execution`
- `test_c3_unknown_model_tool_name_refused_without_numbers`
- `test_c3_tool_valueerror_does_not_invent_var`
- `test_c3_missing_method_does_not_invent_var`
- `test_c3_keyword_path_forwards_principal_into_submit`
- Existing RF-019 `tests/test_ai_query_orchestration.py`, C1, and MCP suites still passing

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_wave_c_orchestration.py tests/test_ai_query_orchestration.py tests/test_wave_c_mcp.py tests/test_wave_c_tool_contracts.py
.venv/bin/ruff check app/risk/query.py tests/test_wave_c_orchestration.py
```

## Results
- Backend C3 + RF-019 + C1 + MCP: **58 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Ruff on touched Python: **All checks passed**
- Frontend: not in scope
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes**
- Unexplained failures or skips: none
- CI is green: not started (C3 local; G3 not claimed)

## Known limitations / risks
- Keyword routing remains heuristic. Collision clarification covers discovery+history and compare+explain; other overlapping phrasings still first-match.
- `get_data_quality` and `get_key_rate_dv01` are allowlisted for `answer_with_model` / MCP but are not C3 taxonomy keyword routes.
- HTTP `PortfolioService.query` still does not pass `principal`; the kwarg is available on the engine for MCP/callers that already have an identity.
- Scenario aliases cover the named DEFAULT_SCENARIOS ids plus equity-down / rates-up / vol-up phrasing; unnamed “run stress” clarifies rather than silently defaulting.

## Follow-up / next owner
- Owner: Independent reviewer (G3), then C4 grounded explanations
- Requested action: review intent routing and grounding; do not mark G3 DONE from this implementer report. C4 must not invent numbers when formatting provenance cards.
- Blocking?: no
