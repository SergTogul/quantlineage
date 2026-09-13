# Task B5 Report — Historical Analytics UI

## Task
Wave B gate G5: one coherent Historical Analytics page powered by `POST /api/v1/risk/historical-analytics`. Frontend requests, formats, and charts. No financial recalculation. Do not mark G5 DONE.

## Owner
Frontend/Risk UX Engineer (one implementer).

## Status
**IN_PROGRESS — not DONE.** G5 is not marked DONE. Independent review and CI green are still required.

## Summary
Added a `historical-analytics` nav section. The page issues a new POST when start/end change, always with `include_benchmark: true`. Identity, summary, cumulative/wealth, drawdown, rolling vol, nested SPY benchmark, and VaR/ES come from one result. Sharpe `null` displays as undefined. Drawdown series uses API values ≤ 0. Fraction display (`0.0248` → `2.48%`) is labeled with `result.units`. Links go to `#var-es` for existing contributors and risk-change; those blocks are not recomputed here. 400 (missing SPY / overlap) is an error with no client beta.

## Commits
- Tracked copy: `docs/expantion/quantlineage_wave_b/B5_IMPLEMENTER_REPORT.md` (`.superpowers/sdd/` may be gitignored)

## Files changed
- `frontend/src/lib/nav.mjs` (new section)
- `frontend/src/lib/nav.test.js`
- `frontend/src/App.jsx`
- `frontend/src/api.js` (`historicalAnalytics`)
- `frontend/src/api.test.js`
- `frontend/src/components/HistoricalAnalytics.jsx` (new)
- `frontend/src/components/HistoricalAnalytics.test.jsx` (new)
- `frontend/src/components/RiskVisuals.jsx` (`DatedSeriesChart`)
- `frontend/src/lib/riskVisuals.mjs` (`datedSeriesChart` display scale)
- `frontend/src/lib/riskVisuals.test.js`
- `frontend/src/lib/risk.mjs` (overview collage tile)
- `frontend/src/lib/risk.test.js`
- `frontend/src/lib/blockHelp.mjs`
- `frontend/src/lib/blockHelp.test.js`
- `frontend/src/lib/blockHelpWiring.test.js`
- `frontend/src/styles.css`
- `docs/expantion/quantlineage_wave_b/TRACKER.md` (G4 DONE / B5 IN_PROGRESS, already in working tree)
- `.superpowers/sdd/task-b5-report.md` (local)
- `docs/expantion/quantlineage_wave_b/B5_IMPLEMENTER_REPORT.md` (tracked copy)

## Public / interface changes
- UI-only: new hash `#historical-analytics`. Existing `POST /api/v1/risk/historical-analytics` contract unchanged. No new analytics engine. No B6 demo doc. G4 minors not reopened.

## Numerical conventions
- Returns / CAGR / vol / Sharpe: fractions from the API. Display `%` is `value * 100` with the `units` label (`fraction` / `annualized_fraction`).
- Drawdown: fraction of peak, ≤ 0 (`fraction_of_peak_negative`).
- VaR/ES: currency loss via existing `money()` formatter; unit `currency_loss`.
- Benchmark beta dimensionless; TE `annualized_fraction`; excess `fraction`. Chart Y is min/max of API series for SVG layout only.
- Sharpe `null` → `undefined`, not `0`.

## Tests added/updated
- POST body includes range, portfolio identity, `include_benchmark: true`
- Changing end date fires a new POST (payload not reused)
- Summary shows `2.48%` with unit `fraction` for fixture `0.0248`
- Sharpe `null` → undefined
- Drawdown chart `data-value` = `[0, -0.083, -0.02]`
- Nested SPY block; 400 → alert, no client beta
- Source pin: no `quantile`, `Math.sqrt`, `** (`, Sharpe/beta/TE formulas
- Nav section in `NAV_SECTIONS`; AppNav lists all
- `datedSeriesChart` copies API values

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/frontend
npm test -- src/components/HistoricalAnalytics.test.jsx
npm test
npm run lint
npm run build
```

## Results
- RED: missing page/module; `historicalAnalytics` not a function; nav/help/collage/chart helpers absent
- GREEN focused HistoricalAnalytics: **8 passed**
- GREEN full frontend: **26 files, 192 passed**
- ESLint: passed (`eslint src --max-warnings 0`)
- Production build: passed (`vite build`)
- Live API probe (not a test): `POST /api/v1/risk/historical-analytics` with default book `2024-10-01`–`2024-11-15` returned 200, nested benchmark present
- Browser: IDE browser tab did not persist; verification is Vitest/MSW + curl probe
- CI: not started

- All applicable/affected suites required by this task: **yes** (local frontend)
- Unexplained failures or skips: none
- CI is green: **not started**

## Known limitations / risks
- G5 is **not DONE**: independent review + CI still required.
- Endpoint is HEAVY and is **not** a RiskRun type. When `RISKFORGE_HEAVY_INLINE=0` / external worker, the page surfaces the 400 refuse; it does not invent a run_type.
- Default window is `2024-01-02`–`2024-11-15` (packaged demo coverage). A range change always POSTs again; stale responses are dropped by a request seq.
- Display `%` is formatting only; hostile review should still attack percent/fraction confusion.
- No B6 demo walkthrough.

## Follow-up / next owner
- Owner: Lead Architect / G5 reviewer
- Requested action: independent review of B5 UI; do not start B6 demo docs in this gate; do not mark G5 DONE from this report
- Blocking?: no
