# Task C7 Report — Demo + hostile review (Wave C G7)

## Task
Wave C C7: demo script for search Apple → data quality → run risk → contributors → why VaR changed → stress → 10Y KR-DV01 → provenance → unsupported request; hostile review attempting every C7 attack with evidence. Wire `get_data_quality` on the query path. Do not mark G7 DONE. No git push. No live LLM.

## Owner
AI Orchestration Engineer (one implementer).

## Status
**C7 IN_PROGRESS** (implementer complete; independent G7 review not claimed). G7 remains **NOT_STARTED**. TRACKER G6 DONE / C7 IN_PROGRESS included.

## Summary
Wrote `docs/wave_c_ai_mcp_demo.md` in the Wave B demo style (clicks, HTTP/chips, relationships; no invented VaR/ES/DV01). Keyword `show data quality for {instrument_id} from {start} to {end}` now reaches `get_data_quality`. `PortfolioService.get_data_quality` reuses `validate_series` + `_fetch_catalog_series` (existing quality API). Lifespan binds `risk_run_worker` so provenance / enqueue work on in-process HTTP query. Hostile review `reviews/wave-c-ai-mcp-hostile-review.md` attempts every C7 attack; all held (no red tests).

## Commits
Included in this Wave C C7 commit (`feat(wave-c): add AI/MCP demo script and hostile review`).

## Files changed
- `backend/app/risk/query.py` — quality keyword route, quality stopwords, search+quality collision
- `backend/app/services/portfolio_service.py` — `get_data_quality`, `submit`, `get_run_provenance`, `risk_run_worker`
- `backend/app/main.py` — bind `service.risk_run_worker`
- `backend/tests/test_wave_c_orchestration.py` — C7 quality/provenance/demo-route pins
- `docs/wave_c_ai_mcp_demo.md` (new)
- `reviews/wave-c-ai-mcp-hostile-review.md` (new)
- `docs/expantion/quantlineage_wave_c/TRACKER.md` (G6 DONE / C7 IN_PROGRESS; G7 still NOT_STARTED)
- `docs/expantion/quantlineage_wave_c/README.md` — demo / hostile-review pointers
- `docs/expantion/quantlineage_wave_c/C7_IMPLEMENTER_REPORT.md` (this tracked copy)
- `.superpowers/sdd/task-c7-report.md` (local; `.superpowers/sdd/` is gitignored)

## Public/interface changes
- Keyword data-quality questions with catalog id + two ISO dates execute `get_data_quality`
- Missing quality args clarify (digit-free); no second quality engine
- `PortfolioService.get_data_quality` / `get_run_provenance` / `submit` for HTTP query dispatch
- Demo script + hostile review artifacts
- No MCP rewrite. No FastAPI MCP import. G7 not marked DONE

## Numerical conventions
- Unchanged. Demo and review copy tool payloads; they do not compute VaR/ES/DV01/stress.
- Quality identities (`content_hash`, observations) come from `validate_series`.
- Ungrounded paths remain digit-free. Grounded answers may only contain digits present on the tool payload.
- KR-DV01 units remain `per_bp` on showcase rows.

## Tests added/updated
- `test_c7_data_quality_without_instrument_clarifies`
- `test_c7_search_apple_then_quality_reaches_get_data_quality`
- `test_c7_http_query_service_executes_data_quality`
- `test_c7_http_query_service_executes_provenance`
- `test_c7_demo_questions_route_to_allowlisted_tools`
- Existing Wave C C1–C6 + RF-019 + shared-auth + frontend RiskQuery/Overview still passing

## Commands executed
```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line tests/test_wave_c_tool_contracts.py tests/test_wave_c_mcp.py tests/test_wave_c_orchestration.py tests/test_wave_c_grounding.py tests/test_wave_c_evals.py tests/test_ai_query_orchestration.py tests/test_shared_auth.py
.venv/bin/ruff check app/risk/query.py app/services/portfolio_service.py app/main.py app/mcp.py tests/test_wave_c_orchestration.py

cd /Users/user/src/quantlineage/frontend
npm test -- src/components/RiskQuery.test.jsx src/components/Overview.test.jsx
```

## Results
- Backend Wave C + RF-019 + shared auth: **100 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Ruff on touched Python: **All checks passed**
- Frontend RiskQuery + Overview: **12 passed**
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes**
- Unexplained failures or skips: none
- CI is green: not started (C7 local; no git push; G7 not claimed)

## Known limitations / risks
- HTTP quality reuses the Wave A fetch path (may contact the catalog provider). MCP stdio still lacks `get_data_quality`, so MCP cannot fetch quality that way.
- Enqueue tools need the lifespan worker; Compose `QUANTLINEAGE_EXTERNAL_WORKER=1` still refuses HEAVY query.
- KR-DV01 top-level card metric/value/unit can be `not on this payload` (G4 copy-only).
- Demo does not freeze dollar VaR, DV01, or `content_hash`.

## Follow-up / next owner
- Owner: Independent reviewer (G7), then orchestrator for CI
- Requested action: review demo honesty and named-attack evidence. Do not mark G7 DONE from this implementer report. Orchestrator owns git push / CI after G7 PASS.
- Blocking?: no
