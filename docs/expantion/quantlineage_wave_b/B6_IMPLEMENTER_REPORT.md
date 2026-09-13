# Task B6 Report — Historical analytics demo / polish

## Task
Wave B gate G6: 5–8 minute presenter flow data → historical analytics → SPY → drawdown/risk → contributors → KR-DV01 → T0/T1 waterfall → provenance. Clicks and talking points only. Do not mark G6 DONE.

## Owner
Frontend/Risk UX Engineer (one implementer).

## Status
**IN_PROGRESS — not DONE.** G6 is not marked DONE. Independent review and CI green are still required.

## Summary
Wrote `docs/historical_analytics_demo.md` in golden-demo style (setup, hashes, button labels, APIs, units/sign from payloads, no memorized risk numbers). Demo-blocking polish: Historical related links no longer share `#var-es`. Contributors land on `#var-es/contributors`, waterfall on `#var-es/risk-change`, KR-DV01 on `#risk-factors/kr-dv01`. Parallel DV01 is labeled **Parallel DV01 (not KR-DV01)**. Residual remains a labeled waterfall step. Setup documents in-process API because HA is HEAVY and is not a RiskRun type under Compose `RISKFORGE_EXTERNAL_WORKER=1`. TRACKER G5 DONE / B6 IN_PROGRESS included. G6 stays NOT_STARTED.

## Commits
- Tracked copy: `docs/expantion/quantlineage_wave_b/B6_IMPLEMENTER_REPORT.md` (`.superpowers/sdd/` is gitignored)

## Files changed
- `docs/historical_analytics_demo.md` (new)
- `frontend/src/lib/nav.mjs` (`SECTION_PANELS`, `hashForPanel`, `panelElementId`)
- `frontend/src/lib/nav.test.js`
- `frontend/src/App.jsx` (scroll to panel card)
- `frontend/src/App.test.jsx`
- `frontend/src/components/HistoricalAnalytics.jsx` (distinct hrefs + KR-DV01 / provenance links)
- `frontend/src/components/HistoricalAnalytics.test.jsx`
- `frontend/src/components/RiskTable.jsx` (`id="var-es-contributors"`)
- `frontend/src/components/Analytics.jsx` (`id="var-es-risk-change"`, `id="risk-factors-kr-dv01"`, Parallel DV01 label)
- `frontend/src/components/RiskVisuals.test.jsx`
- `frontend/src/components/RiskChangeAttribution.test.jsx`
- `frontend/src/styles.css` (scroll-margin on panel ids)
- `docs/expantion/quantlineage_wave_b/TRACKER.md` (G5 DONE / B6 IN_PROGRESS, already in working tree)
- `.superpowers/sdd/task-b6-report.md` (local)
- `docs/expantion/quantlineage_wave_b/B6_IMPLEMENTER_REPORT.md` (tracked copy)

## Public / interface changes
- UI-only hashes: `#var-es/contributors`, `#var-es/risk-change`, `#risk-factors/kr-dv01`. Unknown panel tails still open the section root. No new analytics engine. No B7 hostile review. Overview layouts not restyled. G5 math/minors not reopened except the shared `#var-es` landing.

## Numerical conventions
- None changed. Demo script tells presenters to read `result.units` / `benchmark.units` / `sign_convention` / `conventions.sensitivity_unit` from the payload. Display `%` on Historical remains labeled formatting of API fractions. Drawdown ≤ 0. KR vs parallel stay separate API fields.

## Tests added/updated
- `parseRoute` / `hashForPanel` / `panelElementId` for distinct panels; unknown panel → section, `panel: null`
- Historical links: four distinct hrefs (`#var-es/contributors`, `#risk-factors/kr-dv01`, `#var-es/risk-change`, `#risk-runs`)
- App scrolls to `var-es-contributors` vs `var-es-risk-change` vs `risk-factors-kr-dv01`
- Contributors / RatesShowcase / RiskChangeAttribution cards expose those ids
- Parallel DV01 still separately labeled; KR curve still must not contain “Parallel DV01”

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/frontend
npm test -- src/lib/nav.test.js src/App.test.jsx src/components/HistoricalAnalytics.test.jsx src/components/RiskVisuals.test.jsx src/components/RiskChangeAttribution.test.jsx src/components/RatesProvenance.test.jsx
npm test
npm run lint
npm run build
```

## Results
- RED: both HA links `#var-es`; App panel tests crashed on incomplete `varReport`; shared `scrollIntoView` mock
- GREEN focused: **6 files, 38 passed**
- GREEN full frontend: **26 files, 196 passed**
- ESLint: passed (`eslint src --max-warnings 0`)
- Production build: passed (`vite build`)
- Browser: not exercised in this implementer pass; verification is Vitest/MSW plus hash walk in `nav.mjs`
- CI: not started

- All applicable/affected suites required by this task: **yes** (local frontend)
- Unexplained failures or skips: none
- CI is green: **not started**

## Known limitations / risks
- G6 is **not DONE**: independent review + CI still required.
- `POST /api/v1/risk/historical-analytics` is HEAVY and is not a RiskRun type. Compose `RISKFORGE_EXTERNAL_WORKER=1` 400s the Historical page. The demo script uses in-process uvicorn. Wiring a run_type was out of scope.
- Default HA window is still `2024-01-02`–`2024-11-15`.
- G5 minors (Sharpe unit cell, in-flight previous result, `formatFraction` always ×100) were not reopened.

## Follow-up / next owner
- Owner: Lead Architect / G6 reviewer
- Requested action: independent review of B6 demo + panel hashes; do not write B7 hostile review in this gate; do not mark G6 DONE from this report
- Blocking?: no
