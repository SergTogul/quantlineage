# Task B4 Report — Flagship T0→T1 risk-change waterfall

## Task
Wave B gate G4: hero visual for “Why did my risk change?” from `POST /api/v1/risk/runs/compare` → `RiskChangeReport`. Frontend does not reconstruct attribution.

## Owner
Frontend/Risk UX Engineer (one implementer).

## Status
**IN_PROGRESS — not DONE.** G4 is not marked DONE. Independent review and CI green are still required.

## Summary
Flagship Compare T0/T1 now charts API waterfall steps in order: T0 risk → portfolio/trade change → market/factor changes → residual/interactions → T1 risk. Residual is always rendered from `report.residual` / `residual_name`, including when residual is 0. Identity (portfolio version, snapshot, dataset id/version, methodology, calculation config) is a T0 vs T1 table from `identity.*` plus `changed_fields` / `disclosed_changes`. Hierarchy drill is Firm→Desk→Book→Trade from `hierarchy_contributors`; factors stay a separate table from `factor_contributors`. Legacy `POST /risk/change-attribution` remains the secondary “Run attribution” path.

## Commits
- Tracked copy: `docs/expantion/quantlineage_wave_b/B4_IMPLEMENTER_REPORT.md` (`.superpowers/sdd/` is gitignored)

## Files changed
- `frontend/src/lib/riskVisuals.mjs` (`riskChangeWaterfallSteps` copies API fields)
- `frontend/src/lib/riskVisuals.test.js`
- `frontend/src/components/Analytics.jsx` (flagship waterfall, identity, drill testids; Compare T0/T1 primary)
- `frontend/src/components/RiskChangeAttribution.test.jsx`
- `frontend/src/styles.css`
- `docs/expantion/quantlineage_wave_b/TRACKER.md` (G3 DONE / B4 IN_PROGRESS, already in working tree)
- `.superpowers/sdd/task-b4-report.md` (local, gitignored)
- `docs/expantion/quantlineage_wave_b/B4_IMPLEMENTER_REPORT.md` (tracked copy)

## Public / interface changes
- None. Existing `POST /api/v1/risk/runs/compare` only. No new attribution engine. No B5 Historical Analytics page.

## Numerical conventions
- Units and `sign_convention` displayed from the payload (AD-B7).
- Waterfall values are `previous_risk`, `portfolio_trade_change`, `market_change`, `residual`, `current_risk` copied from the report.
- Display scale: bar height is `|API amount| / maxAbs` of those five fields. Not a risk measure. No running-total reconstruction.
- Residual is never computed as `total_change - portfolio_trade_change - market_change`.

## Tests added/updated
- `riskChangeWaterfallSteps` copies API fields; residual 0 is kept even when `total_change - trade - market` would be nonzero (test-side only)
- Waterfall DOM steps equal fixture `$1.0K`, `$300`, `$110`, `$10`, `$1.4K`
- Residual label + `$0` visible when `residual === 0`
- Identity renders portfolio versions, `snap-t0`, `real:public:wave-a`, methodology, lookback config
- Drill Firm→Desk→Book→Trade; factor table from `factor_contributors`; no invented EquitySpot children under trades
- Source pin: no `quantile`, `Math.sqrt`, `total_change -`, `previous_risk +`
- Existing Compare T0/T1 MSW coverage kept

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/frontend
npm test -- src/lib/riskVisuals.test.js src/components/RiskChangeAttribution.test.jsx
npm test
npm run lint
npm run build
```

## Results
- RED: missing `riskChangeWaterfallSteps`; no waterfall/identity/drill testids
- GREEN focused: **14 passed** (riskVisuals + RiskChangeAttribution + RatesProvenance)
- GREEN full frontend: **25 files, 182 passed** (second full run; first full run had a Limits.test.jsx `toBeDisabled` flake that passed in isolation and on rerun)
- ESLint: passed (`eslint src --max-warnings 0`)
- Production build: passed (`vite build`)
- Browser: IDE browser tab did not persist; verification is Vitest/MSW
- CI: not started

- All applicable/affected suites required by this task: **yes** (local frontend)
- Unexplained failures or skips: none on the passing full run
- CI is green: **not started**

## Known limitations / risks
- G4 is **not DONE**: independent review + CI still required.
- Residual appears twice (waterfall column + totals chip) so it cannot be missed; both are API `residual`.
- Waterfall bars are independent heights, not a bridging accounting waterfall (forbidden `previous_risk +` running totals).
- Live Compare T0/T1 still creates two RiskRuns then POSTs compare (unchanged). Slow on a cold book.
- Limits.test.jsx showed one parallel-run flake; not in B4 files; passed on rerun.

## Follow-up / next owner
- Owner: Lead Architect / G4 reviewer
- Requested action: independent review of B4 waterfall; do not start B5 Historical Analytics page in this gate; do not mark G4 DONE from this report
- Blocking?: no
