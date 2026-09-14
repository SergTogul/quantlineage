# Task C4 Report — Grounded explanations / provenance (Wave C G4)

## Task
Wave C C4: numeric risk answers are grounded cards copied from tool payloads. Missing identity fields are omitted or labeled `not on this payload` — never invented. `explain_risk_change` / `compare_risk_runs` summarize stored `RiskChangeReport` fields, including residual, without recomputing. Do not mark G4 DONE. No `docs/mcp.md`. No C5 UI. No G3 minors.

## Owner
AI Orchestration Engineer (one implementer).

## Status
**C4 IN_PROGRESS** (implementer complete; independent G4 review not claimed). G4 remains **NOT_STARTED**.

## Summary
Finished the paused C4 draft. `_grounded_tool_response` now attaches `data["card"]` and `data["provenance"]` copied from the allowlisted tool payload (including nested RiskRun `results[].payload` and `request` when those keys exist). `_format_answer` dumps those keys into the answer text. Sync RF-019 VaR/ES still has no RiskRun id; the card says `not on this payload` instead of fabricating one. Risk-change answers list T0/T1, total, portfolio/trade, market, stored residual, contributors, and disclosed changes from the fixture only. Residual is never `total − explained`. Formatter does not call VaR/ES/DV01/stress engines.

## Commits
Included in this Wave C C4 commit (`feat(wave-c): ground answers on tool payload cards`).

## Files changed
- `backend/app/risk/query.py` — grounded card/provenance copy, risk-change waterfall formatter, missing-field sentinel
- `backend/tests/test_wave_c_grounding.py` (new)
- `docs/expantion/quantlineage_wave_c/TRACKER.md` (G3 DONE / C4 IN_PROGRESS; G4 still NOT_STARTED)
- `docs/expantion/quantlineage_wave_c/C4_IMPLEMENTER_REPORT.md` (this tracked copy)
- `.superpowers/sdd/task-c4-report.md` (local; `.superpowers/sdd/` is not part of the commit)

## Public / interface changes
- `RiskQueryResponse.data` gains `card` and `provenance` on successful tool execution (C5 can render later)
- Answer text includes metric/value/unit/sign/run/as_of/methodology/dataset when those keys exist on the payload
- Missing fields are `not on this payload` (or omitted from copy) — no invented run ids, dates, units, or numbers
- No HTTP routes added. No `docs/mcp.md`. No C5 UI. No G3 routing/injection changes
- G4 not marked DONE

## Numerical conventions
- Unchanged. Formatter copies payload keys; it does not compute VaR/ES/DV01/stress.
- Risk-change residual is the stored residual. Missing residual is labeled missing, never estimated as `total − explained`.
- RF-019 fixture digits `444` / `555` / `40` / `1` preserved. Ungrounded paths remain digit-free.
- Display still uses existing `_fmt` (`:,.0f`) for numeric payload values.

## Tests added/updated
- `test_c4_numeric_answers_copy_metric_value_unit_sign_run_asof_methodology_dataset`
- `test_c4_missing_identity_fields_are_not_invented`
- `test_c4_explain_risk_change_lists_waterfall_from_fixture_only` (also `compare_risk_runs`; dispatch is C1 `compare_runs`)
- `test_c4_missing_residual_and_unit_are_not_estimated`
- `test_c4_get_risk_run_card_copies_run_identity`
- `test_c4_ungrounded_paths_remain_digit_free`
- Existing RF-019 `tests/test_ai_query_orchestration.py`, C3, C1, and MCP suites still passing

## Commands executed

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_wave_c_grounding.py tests/test_wave_c_orchestration.py tests/test_ai_query_orchestration.py tests/test_wave_c_mcp.py tests/test_wave_c_tool_contracts.py
.venv/bin/ruff check app/risk/query.py tests/test_wave_c_grounding.py
```

## Results
- Backend C4 + C3 + RF-019 + C1 + MCP: **64 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Ruff on touched Python: **All checks passed**
- Frontend: not in scope
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes**
- Unexplained failures or skips: none
- CI is green: not started (C4 local; G4 not claimed)

## Known limitations / risks
- RF-019 sync `get_var_es` / contributors / worst-stress payloads still have no `risk_run_id`; cards label that missing rather than wrapping them in a RiskRun.
- `RiskChangeReport.identity.t0/t1` as_of/methodology/snapshot ids stay nested on `card["identity"]`. Top-level provenance does not flatten a single as_of from T0 or T1 (that would invent one run identity).
- `_payload_run_id` treats payload `id` as a run id, which is correct for `get_risk_run` / submit tools. Non-run payloads in `_NUMERIC_TOOLS` should not carry an unrelated `id`.
- RF-019 contributor percent still defaults missing `contribution_pct` to `0.0` in the pre-existing sentence formatter (G3-era; not changed here).
- C5 still needs to render `data["card"]` / `data["provenance"]`; this task only dumps them.

## Follow-up / next owner
- Owner: Independent reviewer (G4), then C5 Risk Query UI / `docs/mcp.md`
- Requested action: review copy-only grounding and residual handling; do not mark G4 DONE from this implementer report. C5 must render cards without recomputing risk.
- Blocking?: no
