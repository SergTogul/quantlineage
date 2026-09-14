# Task C5 Report — Risk Query UI + MCP docs (Wave C G5)

## Task
Wave C C5: Risk Query UI with contextual example chips; render C4 `data.card` / `data.provenance` without client risk math; `docs/mcp.md` plus a minimal stdio/client example. Minimal keyword route so “Show USD 10Y KR-DV01.” reaches `get_key_rate_dv01`. Do not mark G5 DONE. No live LLM. No C6/C7.

## Owner
Frontend AI UX / AI Orchestration Engineer (one implementer).

## Status
**C5 IN_PROGRESS** (implementer complete; independent G5 review not claimed). G5 remains **NOT_STARTED**.

## Summary
Extended the existing `RiskQuery` block (Scenario Builder + Overview Command `#overview/command`) with clickable example chips that fill and submit. Result cards and provenance copy primitive fields from the API payload; missing identity fields are labeled `not on this payload`. Clarifications (including “Why did VaR change?” without two run ids) show the server text and no invented digits. Keyword routing maps USD 10Y KR-DV01 onto `get_key_rate_dv01` with the C1 tenor filter. `PortfolioService.build_rates_showcase` delegates to the existing rates-macro helper so HTTP `POST /risk/query` can execute that tool (same mapping as stdio MCP). Added `docs/mcp.md` and `docs/examples/mcp_stdio_client.py`. FastAPI still does not import MCP.

## Commits
Included in this Wave C C5 commit (`feat(wave-c): add Risk Query examples and MCP docs`).

## Files changed
- `frontend/src/components/ScenarioBuilder.jsx` — example chips, copied card/provenance fields
- `frontend/src/components/RiskQuery.test.jsx` (new)
- `frontend/src/components/Overview.test.jsx` — command layout chips
- `frontend/src/styles.css` — chip/card layout
- `frontend/src/lib/blockHelp.mjs` — Risk Query help copy
- `backend/app/risk/query.py` — KR-DV01 keyword route + tenor extract
- `backend/app/services/portfolio_service.py` — `build_rates_showcase` for C1 dispatch
- `backend/tests/test_wave_c_orchestration.py` — KR-DV01 keyword + HTTP execute
- `backend/tests/test_wave_c_mcp.py` — `docs/mcp.md` allowlist-only check
- `docs/mcp.md` (new)
- `docs/examples/mcp_stdio_client.py` (new)
- `docs/expantion/quantlineage_wave_c/README.md` — MCP / `#overview/command` pointers
- `docs/expantion/quantlineage_wave_c/TRACKER.md` (G4 DONE / C5 IN_PROGRESS; G5 still NOT_STARTED)
- `docs/expantion/quantlineage_wave_c/C5_IMPLEMENTER_REPORT.md` (this tracked copy)
- `.superpowers/sdd/task-c5-report.md` (local; `.superpowers/sdd/` is gitignored)

## Public / interface changes
- Risk Query example chips submit the five C5 prompts
- UI renders `data.card` / `data.provenance` as copied fields only
- Keyword `Show USD 10Y KR-DV01.` → `get_key_rate_dv01` with `tenor=10Y`
- `PortfolioService.build_rates_showcase()` for allowlisted KR-DV01 dispatch
- `docs/mcp.md` + stdio client example (`python -m app.mcp`)
- No MCP rewrite. No FastAPI MCP import. G5 not marked DONE

## Numerical conventions
- Unchanged. UI copies payload strings/numbers; unicode minus is display-only.
- KR-DV01 still comes from `build_rates_showcase` / SensitivityEngine (`per_bp`).
- Ungrounded clarifications remain digit-free.

## Tests added/updated
- `example chips fill and submit the listed prompts`
- `renders card and provenance fields copied from the payload only`
- `shows the server clarification for Why did VaR change? without inventing digits`
- Overview command layout still hosts Risk Query chips (`#overview/command`)
- `test_c5_usd_10y_kr_dv01_keyword_reaches_get_key_rate_dv01`
- `test_c5_http_query_service_executes_key_rate_dv01`
- `test_c5_mcp_docs_exist_and_omit_forbidden_tools`
- RF-019 + C3 + C4 + C1 + MCP suites still passing

## Commands executed

```bash
cd /Users/user/src/quantlineage/frontend
npm test -- src/components/RiskQuery.test.jsx src/components/Overview.test.jsx src/components/ScenarioBuilder.test.jsx src/lib/blockHelp.test.js src/lib/blockHelpWiring.test.js src/components/HedgeCompare.test.jsx src/components/ReverseStressMulti.test.jsx
npx eslint src/components/ScenarioBuilder.jsx src/components/RiskQuery.test.jsx src/components/Overview.test.jsx src/lib/blockHelp.mjs --max-warnings 0

cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_wave_c_grounding.py tests/test_wave_c_orchestration.py tests/test_ai_query_orchestration.py tests/test_wave_c_mcp.py tests/test_wave_c_tool_contracts.py
.venv/bin/ruff check app/risk/query.py app/services/portfolio_service.py tests/test_wave_c_orchestration.py tests/test_wave_c_mcp.py
```

## Results
- Backend RF-019 + C1 + C3 + C4 + MCP + C5: **67 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Ruff on touched Python: **All checks passed**
- Frontend targeted vitest: **25 passed** (RiskQuery 3, Overview 9, ScenarioBuilder 3, BlockHelp 3, wiring 1, HedgeCompare/ReverseStress 5)
- ESLint on touched frontend: **clean**
- Live `POST /api/v1/risk/query` “Show USD 10Y KR-DV01.” → `tool_name=get_key_rate_dv01`, 10Y tenor
- Live “Why did VaR change?” → clarification, digit-free, no card
- Browser MCP could not retain a tab; UI verified via vitest + live query API
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes**
- Unexplained failures or skips: none
- CI is green: not started (C5 local; G5 not claimed)

## Known limitations / risks
- Showcase KR-DV01 payload keeps values on `key_rate_dv01[]` rows; C4 top-level card `metric`/`value`/`unit` stay `not on this payload` (G4 copy-only; not reopened).
- `PortfolioService.build_rates_showcase` always uses `RATES_MACRO_PORTFOLIO` + demo snapshot, matching GET `/market/rates-showcase` and stdio MCP, not the queried book’s curve.
- Example stdio client starts `python -m app.mcp`, which constructs the default worker (same as C2).
- Browser automation did not complete an end-to-end click-through in this session.

## Follow-up / next owner
- Owner: Independent reviewer (G5), then Eval Agent (C6)
- Requested action: review UI copy-only cards, KR-DV01 keyword route, and MCP docs. Do not mark G5 DONE from this implementer report. Do not start C6/C7 here.
- Blocking?: no
