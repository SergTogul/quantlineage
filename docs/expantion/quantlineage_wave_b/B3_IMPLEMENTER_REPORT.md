# Task B3 Report — Institutional risk visuals (Wave B G3)

## Task
Wave B gate G3: make existing backend risk artifacts visually readable (bars, heatmaps, KR-DV01 tenor curve). Frontend requests, formats, sorts, and charts only.

## Owner
Frontend/Risk UX Engineer (one implementer).

## Status
**IN_PROGRESS — not DONE.** G3 is not marked DONE. Independent review and CI green are still required.

## Summary
Added presentation-only contribution bars on Component VaR (`POST /risk/contributors` via dashboard `contributors`) and ES `by_risk_factor` (`POST /api/v1/risk/es`). Kept hierarchy / factor concentration heatmaps and filled Risk Factors on the Overview function-key layout. Stress P&L heatmap still colors API `pnl` (scenario P&L, not inverted loss). KR-DV01 is an SVG+CSS tenor chart from `key_rate_dv01`; Parallel DV01 stays a separately labeled field from `parallel_dv01` (never mixed or summed in the browser). VaR/ES trend was skipped: completed RiskRuns do not expose a list/time-series of VaR/ES metrics.

## Commits
- Tracked copy: `docs/expantion/quantlineage_wave_b/B3_IMPLEMENTER_REPORT.md` (`.superpowers/sdd/` is gitignored)

## Files changed
- `frontend/src/lib/riskVisuals.mjs` (display scale helpers)
- `frontend/src/lib/riskVisuals.test.js`
- `frontend/src/components/RiskVisuals.jsx` (bars + KR-DV01 tenor chart)
- `frontend/src/components/RiskVisuals.test.jsx`
- `frontend/src/components/RiskTable.jsx` (contributor bars)
- `frontend/src/components/Analytics.jsx` (tenor curve, ES factor bars, parallel DV01 label)
- `frontend/src/components/OverviewLayouts.jsx` (factor heatmap on function-key Risk Factors)
- `frontend/src/components/RatesProvenance.test.jsx` (getAllByText for duplicated tenor labels; source pin kept)
- `frontend/src/styles.css`
- `docs/expantion/quantlineage_wave_b/TRACKER.md` (G2 DONE / B3 IN_PROGRESS, already in working tree)
- `.superpowers/sdd/task-b3-report.md` (local, gitignored)
- `docs/expantion/quantlineage_wave_b/B3_IMPLEMENTER_REPORT.md` (tracked copy)

## Public / interface changes
- None. Existing APIs only. No new VaR engine, no B4 waterfall rewrite, no B5 Historical Analytics page.

## Numerical conventions
- Units: contributor `risk_amount` and ES `component_es` are currency; `contribution_pct` is API percent; KR-DV01 and Parallel DV01 are currency P&L per +1bp as labeled by API `conventions.sensitivity_unit`.
- Sign: stress heatmap uses API `pnl` (negative = loss). KR/parallel DV01 pass API sign through.
- Display scale: bar width / tenor height is `|API amount| / maxAbs` of the visible series. Not a risk measure. KR tenors are not summed.
- VaR/ES trend: skipped (see limitations).

## Tests added
- contributionBarPct / contributionBarRows pass through API amounts and percents
- keyRateDv01Chart maps each tenor independently (test-side sum ≠ maxAbs)
- Contributors bars render API `risk_amount` / `contribution_pct`
- ES `by_risk_factor` bars render API `component_es` / `contribution_pct` (MSW)
- KR-DV01 tenor curve renders API KR values; Parallel DV01 separately labeled
- Stress P&L heatmap shows `-$9.0K` from `pnl: -9000`, not inverted loss
- Factor exposure heatmap visible on Risk Factors component and default Overview
- Source pin: no `bps_to_decimal`, `0.0001`, VaR z-values/`Math.sqrt`, or KR/parallel client sums
- RatesProvenance source pin kept (`bps_to_decimal|0.0001 *|key_rate_dv01 +`)

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/frontend
npm test -- src/lib/riskVisuals.test.js src/components/RiskVisuals.test.jsx src/components/RatesProvenance.test.jsx
npm test
npm run lint
```

## Results
- RED: missing `riskVisuals.mjs`; no `contribution-bar` / `kr-dv01-tenor-curve` testids
- GREEN focused: **89 passed** (riskVisuals + RiskVisuals + RatesProvenance + Overview + heatmap + risk helpers)
- GREEN full frontend: **25 files, 176 passed**
- ESLint: passed (`eslint src --max-warnings 0`)
- Browser: IDE browser tab did not persist; verification is Vitest/MSW
- CI: not started

- All applicable/affected suites required by this task: **yes** (local frontend)
- Unexplained failures or skips: none
- CI is green: **not started**

## Known limitations / risks
- G3 is **not DONE**: independent review + CI still required.
- **VaR/ES trend skipped.** There is no `GET /risk/runs` list. `GET /risk/runs/{id}` and `/provenance` carry lifecycle and lineage, not a stored VaR/ES series. Result payloads are per-run named blobs. Did not invent a time-series store (AD-B1 / brief).
- Overview default status blotter already had FactorExposureHeatmap; function-key layout now shows it when Risk Factors is focused. Other overview compositions were not restyled.
- `money()` still rounds KR values under $1k to integers (existing formatter).

## Follow-up / next owner
- Owner: Lead Architect / G3 reviewer
- Requested action: independent review of B3 visuals; do not start B4 waterfall rewrite or B5 page in this gate
- Blocking?: no
