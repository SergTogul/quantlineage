# Task C6 Report — Eval harness + adversarial cases (Wave C G6)

## Task
Wave C C6: repeatable pytest eval harness covering every C6 adversarial row. Deterministic tool truth wins; unsupported paths fail or clarify; never invent VaR/ES/DV01. No live LLM. Do not mark G6 DONE. No C7 hostile-review file. No UI restyle.

## Owner
AI Orchestration Engineer (one implementer).

## Status
**C6 IN_PROGRESS** (implementer complete; independent G6 review not claimed). G6 remains **NOT_STARTED**.

## Summary
Added `backend/tests/test_wave_c_evals.py` as the G6 eval harness. Each C6 row has a failing-closed assertion (digit-free ungrounded, or tool-payload digits only). The harness reuses `_FixtureService` / `_ScriptedModel`, `validate_tool_call`, `RiskQueryEngine`, and `ThinMcpServer`. No live LLM.

Harness gaps that were not already locked by RF-019/C3/C4 required three small fail-closed production fixes: `RiskRunNotFound` becomes `_TOOL_FAILURE_ANSWER` (no estimated VaR); `estimate_var` / `shell` prompt text is refused before VaR routing; API-key/secret prompts and model refusals are refused without echoing secrets; oversized string args fail `validate_tool_call` (`TOOL_ARG_MAX_CHARS = 4096`). AD-C13 is locked by a one-turn looping scripted model. AD-C14 is locked by history/tool-failure evals. MCP unknown tools stay typed `ErrorBody`.

## Commits
Included in this Wave C C6 commit (`feat(wave-c): add adversarial eval harness for G6`).

## Files changed
- `backend/tests/test_wave_c_evals.py` (new) — C6 eval harness
- `backend/app/risk/query.py` — fake-tool / secret refuse, oversized-arg check, secret-leak filter, `RiskRunNotFound` typed failure
- `backend/app/risk/tool_contracts.py` — `TOOL_ARG_MAX_CHARS` on string fields
- `docs/expantion/quantlineage_wave_c/TRACKER.md` (G5 DONE / C6 IN_PROGRESS; G6 still NOT_STARTED)
- `docs/expantion/quantlineage_wave_c/C6_IMPLEMENTER_REPORT.md` (this tracked copy)
- `.superpowers/sdd/task-c6-report.md` (local; `.superpowers/sdd/` is gitignored)

## Public / interface changes
- Keyword `estimate_var` / hidden `shell` prompts refuse without executing a risk tool
- API-key / secret prompts refuse; model refusals that echo secrets are discarded
- Stale/missing RiskRun ids through `RiskQueryEngine` return the existing digit-free tool-failure clarification instead of raising
- String tool args longer than 4096 characters fail `validate_tool_call` (JSON schema `maxLength` plus a walk in `validate_tool_call`)
- No HTTP routes added. No MCP rewrite. No UI. G6 not marked DONE

## Numerical conventions
- Unchanged. Eval and orchestration still dump service payloads; they do not compute VaR/ES/DV01/stress.
- Ungrounded paths remain digit-free. Grounded answers may only contain digits present on the tool payload.
- Units are copied (`USD`, `per_bp`) or labeled `not on this payload`; they are never converted.

## Tests added/updated
- `test_c6_missing_data_hallucination`
- `test_c6_ambiguous_portfolios_runs`
- `test_c6_prompt_injection`
- `test_c6_fake_hidden_tool_request`
- `test_c6_api_key_secret_request`
- `test_c6_advisory_trading_request`
- `test_c6_misleading_user_supplied_numbers`
- `test_c6_unit_traps`
- `test_c6_stale_mismatched_run_ids`
- `test_c6_malformed_oversized_tool_args`
- `test_c6_ad_c13_one_turn_no_tool_loop`
- `test_c6_ad_c14_tool_failure_has_no_hidden_estimate`
- `test_c6_mcp_unknown_tool_is_typed_error_body`
- `test_c6_g3_g4_minors_remain_fail_closed`
- `test_c6_harness_declares_every_required_row`
- Existing RF-019 + C1 + C3 + C4 + MCP suites still passing

## Commands executed

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_wave_c_evals.py tests/test_wave_c_grounding.py tests/test_wave_c_orchestration.py tests/test_ai_query_orchestration.py tests/test_wave_c_mcp.py tests/test_wave_c_tool_contracts.py
.venv/bin/ruff check app/risk/query.py app/risk/tool_contracts.py tests/test_wave_c_evals.py
```

## Results
- Backend C6 + RF-019 + C1 + C3 + C4 + MCP: **82 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Ruff on touched Python: **All checks passed**
- Frontend: not in scope
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes**
- Unexplained failures or skips: none
- CI is green: not started (C6 local; G6 not claimed)

## Known limitations / risks
- Secret/fake-tool keyword markers are heuristic. A mixed prompt that mentions an API key together with VaR now refuses entirely (fail-closed) rather than answering VaR and stripping the secret.
- Marker `password` is a substring of `passwords`; the canned secret refusal is returned directly and is digit-free.
- KR-DV01 nested `per_bp` still lives on `key_rate_dv01[]` rows; top-level card unit remains `not on this payload` (G4 copy-only, not reopened).
- AD-C13 is enforced by one-shot `answer_with_model` (complete() exactly once). There is no named `MAX_MODEL_TOOL_TURNS` constant.
- Oversized-arg cap is 4096 characters per string field, not the HTTP 1 MiB body cap.

## Follow-up / next owner
- Owner: Independent reviewer (G6), then C7 demo + hostile review
- Requested action: review eval coverage and the small fail-closed production fixes; do not mark G6 DONE from this implementer report. Do not start C7 here.
- Blocking?: no
