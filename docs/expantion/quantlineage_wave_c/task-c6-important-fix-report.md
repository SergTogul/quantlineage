# Task C6 follow-up — G6 Important fixes

## Task
Close the two G6 Important findings from `.superpowers/sdd/task-c6-review.md`. Do not mark G6 DONE. Do not start C7. Do not write `reviews/wave-c-ai-mcp-hostile-review.md`.

## Owner
AI Orchestration Engineer (one implementer).

## Status
**C6 IN_PROGRESS** (Important items closed). G6 remains **NOT_STARTED**. C7 remains **NOT_STARTED**.

## Summary
Added `RISKFORGE_MCP_AUTHORIZATION` to `_SECRET_ENV_NAMES` so a VaR-question model refusal that copies that env value is discarded the same way as `FRED_API_KEY` / `RISKFORGE_API_TOKEN`. Tightened `_assert_tool_digits_only` so every `\d+` token in `answer` must appear in `json.dumps(tool_result)`, while still forbidding `999`.

## Commits
Included in this Wave C follow-up commit on `feat/quantlineage-wave-c` (parent `1a8aa48`).

## Files changed
- `backend/app/risk/query.py` — add `RISKFORGE_MCP_AUTHORIZATION` to `_SECRET_ENV_NAMES`
- `backend/tests/test_wave_c_evals.py` — MCP-auth refusal eval; payload-digit scan in `_assert_tool_digits_only`; helper regression for invented `888`
- `docs/expantion/quantlineage_wave_c/task-c6-important-fix-report.md` (this tracked copy)
- `.superpowers/sdd/task-c6-important-fix-report.md` (local; `.superpowers/sdd/` is gitignored)

## Public / interface changes
- Model refusals that echo `RISKFORGE_MCP_AUTHORIZATION` are no longer used as `answer`
- No HTTP, MCP, or UI changes. TRACKER G6 left unmarked. C7 not started

## Numerical conventions
- Unchanged. Grounded evals now reject any answer digit token absent from the tool payload dump. `999` remains forbidden.

## Tests added/updated
- `test_c6_mcp_authorization_env_refusal_is_discarded` — `answer_with_model("What is 99% VaR?")` with a refusal copying `RISKFORGE_MCP_AUTHORIZATION` discards that refusal
- `test_c6_assert_tool_digits_only_rejects_invented_payload_digits` — extra `888` fails the helper
- Existing grounded `_assert_tool_digits_only` callers now scan every answer digit against `json.dumps(tool_result)`

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_wave_c_evals.py tests/test_ai_query_orchestration.py
.venv/bin/ruff check app/risk/query.py tests/test_wave_c_evals.py
```

## Results
- Backend C6 evals + RF-019 orchestration: **37 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Ruff on touched Python: **All checks passed**
- Frontend: not in scope
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes**
- Unexplained failures or skips: none
- CI is green: not started (local follow-up; G6 not claimed)

## Known limitations / risks
- Other G6 Minors (tautological row-declaration test, `use shell` heuristic, `999` on `data.model`, unnamed `MAX_MODEL_TOOL_TURNS`, mixed secret/VaR branch) were not reopened.
- Digit scan is substring containment in `json.dumps(tool_result)` (same spirit as C4), not a parsed-number equality check.

## Follow-up / next owner
- Owner: Orchestrator (accept G6), then independent C7
- Requested action: do not mark G6 DONE from this fix report. Do not start C7 here.
- Blocking?: no
