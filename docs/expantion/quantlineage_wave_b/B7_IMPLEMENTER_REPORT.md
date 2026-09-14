# Task B7 Report — Wave B hostile review + full regression (G7)

## Task
Wave B gate G7: hostile review of named analytics attacks, pins/smallest fixes for confirmed holes, full backend pytest + frontend test+lint. Do not mark G7 DONE.

## Owner
QA & Quant Validation Engineer (one implementer). Smallest production fix for the confirmed stale-UI hole in the same change.

## Status
**IN_PROGRESS — not DONE.** Implementer hostile review is written. Independent review and CI green are still required. G7 stays NOT_STARTED.

## Summary
Attacked every B7 named item with file:line evidence. A red test is a blocker. Confirmed hole: Historical Analytics kept a previous range on screen while a newer POST was in flight (seq already dropped out-of-order applies). Smallest fix: show result/error only when portfolio id/version + start + end match the controls. Added distinguishing pins for inverted beta and TE annualization (`std × sqrt(ppy)`, not 252 and not ×ppy). TRACKER G6 DONE / B7 IN_PROGRESS included. G7 not marked DONE.

## Commits
- `5576b7f` `fix(ui): hide stale historical analytics after a range change`
- Tracked copy: `docs/expantion/quantlineage_wave_b/B7_IMPLEMENTER_REPORT.md` (`.superpowers/sdd/` is gitignored)

## Files changed
- `reviews/wave-b-analytics-hostile-review.md` (new)
- `backend/tests/test_historical_analytics.py` (beta inversion + TE ppy pins)
- `frontend/src/components/HistoricalAnalytics.jsx` (request-keyed display)
- `frontend/src/components/HistoricalAnalytics.test.jsx` (stale in-flight + slower-first)
- `docs/expantion/quantlineage_wave_b/TRACKER.md` (G6 DONE / B7 IN_PROGRESS)
- `.superpowers/sdd/task-b7-report.md` (local, gitignored)
- `docs/expantion/quantlineage_wave_b/B7_IMPLEMENTER_REPORT.md` (tracked copy)

## Public / interface changes
- None. HTTP contract unchanged. UI still POSTs the same body; it simply does not render a result that belongs to a different range/book.

## Numerical conventions
- Unchanged. Returns / CAGR / vol / TE are fractions; drawdown ≤ 0; VaR/ES currency loss; beta `cov(r_p, r_b) / var(r_b)`; TE `std × sqrt(ppy)`.
- Display `%` remains labeled formatting of API fractions (`0.0248` → `2.48%`).

## Tests added/updated
- `test_beta_denominator_is_cov_over_var_benchmark_not_inverted` (2× series → beta=2, not 0.5)
- `test_tracking_error_annualizes_std_times_sqrt_periods_per_year` (ppy=12 vs 252 vs ×12)
- HA: slower first POST must not overwrite a later range
- HA: previous range result must leave the screen while the newer POST is in flight (RED then GREEN)

## Commands executed
```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short
.venv/bin/ruff check tests/test_historical_analytics.py app/risk/historical_analytics.py

cd /Users/user/src/quantlineage/frontend
npm test -- src/components/HistoricalAnalytics.test.jsx
npm test && npm run lint
```

Local Playwright E2E (`e2e/`) was not run: `e2e/node_modules` is missing. PR-FULL E2E is the CI job.

## Results
- RED: HA in-flight previous result (`does not keep the previous range result on screen…`); missing beta-inversion / TE-ppy pins
- GREEN focused HA after fix: **10 passed**
- GREEN full backend: **1778 passed**, 9 skipped, 1 Starlette TestClient deprecation warning (pre-existing), 153.55s
- GREEN full frontend: **26 files, 198 passed**
- ESLint: passed (`eslint src --max-warnings 0`)
- Ruff on touched analytics files: passed
- CI: started after push of `feat/quantlineage-wave-b` (see follow-up)

- All applicable/affected suites required by this task: **yes** (local pytest + frontend test/lint)
- Unexplained failures or skips: none (9 backend skips pre-existing)
- CI is green: **not yet** (implementer records URL; G7 not DONE)

## Known limitations / risks
- G7 is **not DONE**: independent review + CI still required.
- Sharpe unit cell still shows `annualized_fraction` from `units.volatility` (value not ×100). Medium/low; not a named-attack failure.
- `compute_historical_analytics` default methodology LINEAR vs HTTP DELTA_GAMMA. Not a named attack.
- Shifted-date zip vs intersection is pinned on `align_dated_series`; rectangular panels make compute-path dates identical.
- Historical Analytics remains HEAVY and is not a RiskRun type.
- Working tree still has unrelated dirty Wave A / README / market-history files; they were not staged.

## Follow-up / next owner
- Owner: Independent Reviewer, then Lead Architect for G7 close.
- Requested action: independent hostile review of `reviews/wave-b-analytics-hostile-review.md`; wait for GitHub Actions PR-FULL green; do **not** mark G7 DONE from this report.
- Blocking for G7 DONE: yes (review + CI).
