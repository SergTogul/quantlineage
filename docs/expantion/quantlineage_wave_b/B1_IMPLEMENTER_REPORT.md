# Task B1 Report — Historical analytics backend (Wave B G1)

## Task
Wave B gate G1: deterministic backend historical analytics from frozen portfolio + dataset + date range.

## Owner
Portfolio Risk Engineer (one implementer). Backend/API wiring in the same change so the result is requestable.

## Status
**IN_PROGRESS — not DONE.** Implementer evidence is below. Independent review and CI green are still required before G1 can be marked DONE.

## Summary
Added one canonical historical-analytics result that powers summary metrics and time series. Period P&L comes from the existing panel approximations (`approximate_pnl_from_panel` / `full_revaluation_pnl_from_panel`). Portfolio VaR/ES are `HistoricalRiskEngine.calculate()` numbers on the sliced window — no second quantile engine. Range changes slice the in-memory panel; they do not mutate frozen CSV/snapshots. No Yahoo/FRED HTTP. No frontend.

## Commits
- `0d52457` `feat(risk): add frozen-history wealth and drawdown analytics`
- `f66b730` `docs(wave-b): record B1 G1 implementer evidence` (tracker)
- Tracked copy: `docs/expantion/quantlineage_wave_b/B1_IMPLEMENTER_REPORT.md` (`.superpowers/sdd/` is gitignored)

## Files changed
- `backend/app/risk/historical_analytics.py` (new)
- `backend/tests/test_historical_analytics.py` (new)
- `backend/app/services/portfolio_service.py`
- `backend/app/api/risk.py`
- `backend/app/api/execution_class.py`
- `docs/expantion/quantlineage_wave_b/TRACKER.md`
- `.superpowers/sdd/task-b1-report.md` (local, gitignored)
- `docs/expantion/quantlineage_wave_b/B1_IMPLEMENTER_REPORT.md` (tracked copy of this report)

## Public / interface changes
- New dual-mounted `POST /risk/historical-analytics` and `POST /api/v1/risk/historical-analytics`.
- Request/result carry portfolio id/version, dataset id/version, snapshot id, range, frequency, methodology, and explicit annualization convention.
- Classified **HEAVY**; `FULL_REVALUATION` is methodology-bearing.

## Numerical conventions
- Units: returns / CAGR / vol / Sharpe are fractions (0.01 = 1%); VaR/ES are currency loss (≥ 0); wealth is an end-of-period index.
- Sign: drawdown is `W_t / peak_{s<=t}(W_s) - 1` with implicit start NAV `W_0 = 1` (≤ 0). Max drawdown is the most negative value.
- Annualization (tested): CAGR `W_n ** (periods_per_year / n) - 1`; vol is sample std (`ddof` from convention) × `sqrt(periods_per_year)`; default 252.
- Sharpe: `(ann_return - rf) / ann_vol`; `None` when vol is 0 (`sharpe_undefined_zero_volatility`).
- DAILY missing weekdays: `drop_with_note` (explicit `dropped_dates`) or `fail_closed`. No silent ffill.
- VaR/ES: HistoricalRiskEngine loss convention `max(0, quantile)` on the analysis window.
- Tolerances: `1e-12` linear cash-equity identities; `1e-10` CAGR/vol.

## Tests added
- constant returns (wealth + CAGR + identities)
- zero vol / Sharpe undefined
- known drawdown (implicit unit NAV peak)
- known Sharpe
- VaR/ES tail equals `HistoricalRiskEngine.calculate`
- short window (n=1)
- missing weekday drop-with-note (no ffill)
- missing weekday fail-closed
- best/worst periods
- rolling vol
- annualization `periods_per_year=12` vs 252
- API identity echo on `/api/v1/risk/historical-analytics`
- range slice does not mutate source panel

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_historical_analytics.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_historical_analytics.py tests/test_endpoint_execution_class.py tests/test_api_v1_compatibility.py tests/test_api_router_decomposition.py tests/test_api.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line tests/test_historical_analytics.py tests/test_historical_data.py tests/test_factor_panel_historical.py
.venv/bin/ruff check app/risk/historical_analytics.py app/api/risk.py app/api/execution_class.py app/services/portfolio_service.py tests/test_historical_analytics.py
```

## Results
- RED: `ModuleNotFoundError: No module named 'app.risk.historical_analytics'`
- GREEN focused analytics: **13 passed** (`tests/test_historical_analytics.py`)
- GREEN analytics + execution class: **24 passed**
- GREEN affected API/router/execution: **48 passed**, 1 Starlette TestClient deprecation warning (pre-existing)
- GREEN analytics + historical dataset/panel: **29 passed**, same warning
- Ruff on touched files: passed
- `mypy app`: pre-existing `union-attr` noise in overlay/label helpers; no diagnostics in `historical_analytics.py`
- Frontend: not in scope
- CI: not started

- All applicable/affected suites required by this task: **yes** (local)
- Unexplained failures or skips: none
- CI is green: **not started**

## Known limitations / risks
- G1 is **not DONE**: independent review + CI still required.
- Frequency is DAILY only. WEEKLY/MONTHLY resampling is out of scope.
- Wealth compounds independent snapshot P&L / MV as a return series (B0: engine paths are not a path-dependent reval walk).
- Return-series VaR is not a separate metric; portfolio VaR/ES are engine currency-loss numbers on the sliced window.
- Default missing-date policy drops absent weekdays with a note; holidays look like missing weekdays.
- `POST /historical-analytics` is HEAVY inline (refuses when external worker / `RISKFORGE_HEAVY_INLINE=0`); not a RiskRun job type yet.
- Benchmark/beta (B2), charts (B3/B5), waterfall UI (B4) are non-goals.

## Follow-up / next owner
- Owner: Independent Reviewer, then Lead Architect for G1 close.
- Requested action: hostile-ish review of percent/fraction, CAGR/vol annualization, drawdown sign, Sharpe zero-vol, P&L vs loss; then CI.
- Blocking for G1 DONE: yes (review + CI). Not blocking for B2 start if the analytics contract is treated as frozen.
