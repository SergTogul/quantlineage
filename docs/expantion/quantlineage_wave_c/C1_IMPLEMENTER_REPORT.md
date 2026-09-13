# Task C1 Report — Deterministic tool contracts (Wave C G1)

## Task
Wave C C1: freeze allowlisted JSON schemas mapped to existing application services. No MCP (C2). No new VaR/stress/DV01 math. Do not mark G1 DONE.

## Owner
AI Orchestration Engineer / Tool Contract Agent (one implementer).

## Status
**C1 IN_PROGRESS** (implementer complete; independent G1 review not claimed). G1 remains **NOT_STARTED**.

## Summary
Froze C1 tool names on `RiskToolName` / `TOOL_CONTRACTS` with typed args, extra keys forbidden, and HTTP/service mappings from `C0_INTEGRATION_MAP.md`. RF-019 tools stay on the allowlist. `compare_risk_runs` and `explain_risk_change` share `compare_runs` and `RiskChangeMetric`. `get_market_history` is instrument levels (`GET /api/v1/market/history/{id}`), not Wave B historical-analytics. Numeric portfolio/stress/contributor tools prefer RiskRun `submit` identity. Optional `get_run_provenance` included; `compare_hedge` deferred (would require binding a second book).

## Commits
Included in this Wave C C1 commit (`feat(wave-c): freeze C1 deterministic tool contracts`).

## Files changed
- `backend/app/risk/tool_contracts.py` (new) — C1 arg models, date bounds, allowlisted stress ids, service dispatch
- `backend/app/risk/query.py` — enum/allowlist/contracts; `ExplainRiskChangeArgs` aliased to `CompareRiskRunsArgs`
- `backend/tests/test_wave_c_tool_contracts.py` (new)
- `docs/expantion/quantlineage_wave_c/TRACKER.md` (C1 IN_PROGRESS + evidence; G1 still NOT_STARTED)
- `docs/expantion/quantlineage_wave_c/C1_IMPLEMENTER_REPORT.md` (this tracked copy)
- `.superpowers/sdd/task-c1-report.md` (local; `.superpowers/sdd/` is gitignored)

## Public / interface changes
- Allowlisted tool names added: `search_instruments`, `get_market_history`, `get_data_quality`, `run_portfolio_risk`, `get_risk_run`, `compare_risk_runs`, `run_stress`, `get_key_rate_dv01`, `get_top_risk_contributors`, `get_run_provenance`
- RF-019 names retained: `get_portfolio_summary`, `get_var_es`, `get_worst_stress`, `get_limits`, `get_contributors`, `explain_risk_change`
- `explain_risk_change` / `compare_risk_runs` args: `metric` is `RiskChangeMetric` (not a free string)
- `search_instruments` arg is `query` (the `search_catalog` parameter), not HTTP `q`
- `RiskToolContract` gained `http_path` and `provenance_fields` (RF-019 rows default empty)
- No HTTP routes added. No MCP. Keyword `RiskQueryEngine.route` unchanged (C3)

## Numerical conventions
- Unchanged. Tool layer dumps service payloads; it does not compute VaR/ES/DV01/stress.
- History: stored levels (`price` / `percent`); 1826-day cap and inverted range refused at schema validation (HTTP 400 today).
- KR-DV01: showcase filter only (optional tenor 2Y/5Y/10Y); units remain `per_bp` from SensitivityEngine.
- Risk-change: same `compare_runs` / `RiskChangeReport` units and residual as Wave B.

## Tests added/updated
- `test_c1_allowlist_includes_minimum_tools_and_rf019`
- `test_c1_unknown_tool_and_extra_keys_are_refused`
- `test_c1_explain_risk_change_metric_is_risk_change_metric_literal`
- `test_c1_get_market_history_is_not_historical_analytics`
- `test_c1_history_date_bounds_match_http_cap_and_inverted_range`
- `test_c1_search_instruments_uses_search_catalog_query_arg`
- `test_c1_compare_and_explain_share_compare_runs_engine`
- `test_c1_run_portfolio_risk_prefers_risk_run_identity`
- `test_c1_run_stress_allowlists_named_default_scenarios`
- `test_c1_key_rate_dv01_maps_to_rates_showcase_not_new_bump_engine`
- `test_c1_no_quantlib_formula_in_query_or_tool_module`
- Existing `tests/test_ai_query_orchestration.py` RF-019 injection/ambiguity/eval tests unchanged and passing

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line tests/test_wave_c_tool_contracts.py tests/test_ai_query_orchestration.py
.venv/bin/ruff check app/risk/query.py app/risk/tool_contracts.py tests/test_wave_c_tool_contracts.py
```

## Results
- Backend C1 + RF-019: **31 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Ruff on touched Python: **All checks passed**
- Frontend: not in scope
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes**
- Unexplained failures or skips: none
- CI is green: not started (C1 local; G1 not claimed)

## Known limitations / risks
- Keyword router still only selects RF-019 tools; C1 names are registered for `answer_with_model` / C2–C3, not NL keywords.
- `get_market_history` / `get_data_quality` / `get_key_rate_dv01` / `get_run_provenance` execute only when the injected service exposes those methods (C2 wires HTTP). Dispatch does not call Yahoo/FRED or `historical_analytics`.
- `run_stress` allowlists `DEFAULT_SCENARIOS` ids at schema time; enqueue uses `run_type=stress` (existing default library) because the stress RiskRun request blob cannot carry extra keys.
- `compare_hedge` omitted: two-book bind is not cheap without violating RF-019 (model never binds portfolio).
- History inverted/oversize ranges fail tool JSON-schema validation (refusal string), matching today’s HTTP 400 preconditions rather than emitting `ErrorBody` from the tool layer.
- `HISTORY_MAX_RANGE_DAYS = 1826` is duplicated next to `app.api.instruments.MAX_HISTORY_RANGE_DAYS` (equality tested) to avoid importing the Yahoo adapter module into the tool layer.

## Follow-up / next owner
- Owner: Independent reviewer (G1), then MCP Agent (C2)
- Requested action: review contracts; do not mark G1 DONE from this implementer report. C2 may register the same allowlist; no new math.
- Blocking?: no
