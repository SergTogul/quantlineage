# Task C0 Report — Inventory deterministic services (Wave C)

## Task
Wave C C0: map every C1 proposed AI/MCP tool to an existing application service / HTTP route. Docs-only. Do not mark G1 DONE. No MCP (C2). No production risk-math changes.

## Owner
AI Orchestration Engineer (one implementer). Lead Architect inventory; C1 owns schemas.

## Status
**C0 DONE.** G1 remains **NOT_STARTED**. Independent review of this map is the next gate input, not a G1 close.

## Summary
Wrote `docs/expantion/quantlineage_wave_c/C0_INTEGRATION_MAP.md` mapping the ten C1 tools plus optional `compare_hedge` / `get_run_provenance` onto existing RF-019 `RiskQueryEngine` / `TOOL_CONTRACTS`, Wave A catalog/history/quality routes, Wave B `POST /risk/runs/compare` and rates-showcase KR-DV01, and RiskRun lifecycle. No parallel risk engine. No MCP server. No UI.

## Commits
Recorded after commit (this file is included in the Wave C pack commit).

## Files changed
- `docs/expantion/quantlineage_wave_c/C0_INTEGRATION_MAP.md` (new)
- `docs/expantion/quantlineage_wave_c/TRACKER.md` (C0 DONE; G1 still NOT_STARTED)
- `docs/expantion/quantlineage_wave_c/C0_IMPLEMENTER_REPORT.md` (this tracked copy)
- Wave C pack previously untracked: `README.md`, `01_ARCHITECTURE_DECISIONS.md`, `02_TASKS.md`, `CURSOR_ORCHESTRATOR_PROMPT.md`, `CURSOR_FIRST_MESSAGE.txt`, `SUBAGENT_RULES.md`
- `.superpowers/sdd/task-c0-report.md` (local; `.superpowers/sdd/` is gitignored)

## Public / interface changes
None. Inventory only.

## Numerical conventions (documented, not changed)
- VaR/ES: currency loss; `HistoricalRiskEngine` uses `max(0, quantile(-pnl))`.
- Stress `pnl`: currency; negative = loss.
- KR-DV01: currency P&L per +1bp; 1bp = 1e-4 decimal; long rates typically negative. Demo USD 2Y/5Y/10Y via `GET /market/rates-showcase`.
- Risk-change: VaR/ES positive `total_change` = more loss-risk; stress metric is P&L; residual always present.
- Contributors: `risk_amount` = component VaR; `contribution_pct` is percent.
- History: stored levels (`price` / `percent`); no return conversion in the history tool.

## Tests added/updated
None required. Reuse evidence: existing RF-019 query tests.

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line tests/test_ai_query_orchestration.py
```

## Results
- Backend RF-019: **20 passed**, 1 pre-existing Starlette TestClient deprecation warning
- Frontend: not in scope
- QuantLib / C++ / build: not in scope
- All applicable/affected suites required by this task: **yes** (docs-only; documented reuse tests pass)
- Unexplained failures or skips: none
- CI is green: not started (docs-only C0; no production code)

## Known limitations / risks
- `compare_risk_runs` and `explain_risk_change` share one engine (`RiskRunWorker.compare_runs`). C1 must not split math.
- RF-019 sync tools (`summary` / `var` / `contributors`) omit RiskRun identity; C4 wants run/dataset/snapshot — C1 should prefer `POST /risk/runs`.
- `ExplainRiskChangeArgs.metric` is a free `str`; HTTP compare uses `RiskChangeMetric` literal — C1 should tighten.
- `GET /market/rates-showcase` is the rates-macro **demo book**, not an arbitrary portfolio KR-DV01 API.
- `get_market_history` is instrument levels; Wave B `POST /risk/historical-analytics` is portfolio wealth — do not conflate.
- History/quality HTTP can hit Yahoo/FRED unless tests inject fakes; C2 must not expose a general HTTP tool.
- Keyword `RiskQueryEngine` never executes `explain_risk_change` without ids (clarifies). Preserve that.
- RF-019 `get_limits` / `get_worst_stress` / `get_portfolio_summary` / `get_var_es` are not C1 names; they remain existing allowlist entries to fold or keep.

## Follow-up / next owner
- Owner: Tool Contract Agent (C1)
- Requested action: freeze JSON schemas against this map; still no MCP
- Blocking?: no (C0 complete; G1 not claimed)
