# Agent Handoff — remaining UI close

## Task
Advance remaining Workstream 8 PARTIAL UI items to honest DoD; close Workstream 8 if evidence supports.

## Owner
Frontend / Risk UX Engineer

## Summary
Closed the five open PARTIAL items in one coherent pass:

1. ** Overview** — dedicated `Overview` with KPI strip from API summary/threats + section collage entry points + heatmap teasers (no longer a leftovers dump of full panels).
2. ** Scenario Builder** — presets, validation, loading/error, API shock preview; still `POST /risk/stress/evaluate/custom` only.
3. ** Hierarchy drill-down** — interactive Firm→trade breadcrumb + child table; selected-node metrics from hierarchy API tree.
4. ** P&L Explain** — interactive UI wired to `POST /risk/attribution` (SPY×scale request) plus optional `/attribution/demo` for illustrative marks; base/current MV + drivers + residual.
5. ** Limits** — OK/WARNING/BREACH strip, value/limit/util/warn table, per-metric + breach drill-down.

**Workstream 8 marked COMPLETE** in `ROADMAP.md` (all DONE with evidence). Non-blocking residuals documented ( Scenario wire, E2E lag, demo market path for P&L).

## Files changed
- `frontend/src/App.jsx`
- `frontend/src/api.js`
- `frontend/src/styles.css`
- `frontend/src/components/Overview.jsx` (new)
- `frontend/src/components/Analytics.jsx`
- `frontend/src/components/ScenarioBuilder.jsx`
- `frontend/src/components/RiskTable.jsx`
- `frontend/src/lib/risk.mjs`
- `frontend/src/lib/risk.test.mjs`
- `ROADMAP.md`
- `docs/agents/HANDOFF_RISK_TERMINAL_UI_CLOSE.md` (this file)

## Public/interface changes
- Frontend only: `explainPnL` / `explainPnLDemo` API client helpers; display helpers for overview/hierarchy/scenario/limits.
- No backend contract changes.

## Numerical conventions
- Units: display formatting via existing `money` / `percent`; scenario form still % / bp → API decimal / bps via `scenarioPayload`.
- No client-side risk or pricing math.

## Tests added/updated
- `hierarchyNodeAtPath` / `hierarchyChildRows` / `hierarchyNodeMetrics`
- Scenario presets + `validateScenarioForm`
- `overviewKpis` / `overviewCollage`
- `limitStatusCounts`
- `demoPnLAttributionRequest`

## Commands executed
```bash
cd frontend && npm test && npm run build
```

## Results
- Backend: not re-run (frontend-only change)
- Frontend: **56 passed**, 0 failed
- Build: **OK** (vite; 27 modules)
- QuantLib / C++: N/A

## Known limitations / risks
- P&L illustrative market move still uses `/attribution/demo` (server-built previous snapshot); position-change path uses real `/attribution`.
- Hierarchy drill uses metrics already present on `/risk/hierarchy` nodes (no separate `risk_at` re-fetch).
- Multi-factor reverse stress UI not added to Scenario Builder (single-factor Reverse Stress remains under Stress).
- Playwright E2E not expanded for new overview/drill/P&L/limits flows .
- Formal `Scenario` as stress HTTP wire type still open .

## Follow-up / next owner
- Owner: QA / E2E — cover overview collage navigation, hierarchy drill, P&L explain modes, limits per-metric drill.
- Owner: Backend (optional) — Scenario wire if UI should consume formal Scenario DTO later.
- Blocking?: no — Workstream 8 can close.
