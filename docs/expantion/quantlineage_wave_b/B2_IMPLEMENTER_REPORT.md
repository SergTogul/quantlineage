# Task B2 Report — Benchmark / relative risk (Wave B G2)

## Task
Wave B gate G2: canonical Wave A SPY benchmark identity and deterministic relative analytics on the frozen panel.

## Owner
Portfolio Risk Engineer (one implementer). Nested on the G1 analytics result; API request flag wired through the existing historical-analytics route.

## Status
**IN_PROGRESS — not DONE.** G2 is not marked DONE. Independent review and CI green are still required.

## Summary
Extended the G1 `HistoricalAnalyticsResult` with an optional nested `benchmark` object. Canonical identity is Wave A `equity:US:SPY` / `EquitySpot:SPY` from the locked factor-mapping table, read from the same sliced `HistoricalFactorPanel` (no Yahoo HTTP). Alignment is calendar-date intersection (no positional zip, no ffill). Beta denominator is `cov(r_p, r_b) / var(r_b)` with G1 sample `ddof`; zero benchmark variance fails closed. Tracking error uses the same `AnnualizationConvention` as G1. Benchmark VaR/ES is `HistoricalRiskEngine.calculate()` on a same-notional SPY book — not a second quantile engine. `include_benchmark=False` (default) preserves the G1 contract (`benchmark=None`).

## Commits
- `497ee4a` `feat(risk): add Wave A SPY benchmark relative analytics`
- Tracked copy: `docs/expantion/quantlineage_wave_b/B2_IMPLEMENTER_REPORT.md` (`.superpowers/sdd/` is gitignored)

## Files changed
- `backend/app/risk/historical_analytics.py` (G1 contract kept; nested benchmark + `align_dated_series`)
- `backend/tests/test_historical_analytics.py` (G1 suite kept green; G2 cases added)
- `backend/app/services/portfolio_service.py` (`include_benchmark` passthrough)
- `docs/expantion/quantlineage_wave_b/TRACKER.md`
- `.superpowers/sdd/task-b2-report.md` (local, gitignored)
- `docs/expantion/quantlineage_wave_b/B2_IMPLEMENTER_REPORT.md` (tracked copy of this report)

## Public / interface changes
- `HistoricalAnalyticsRequest.include_benchmark` (default `False`, extra=forbid otherwise unchanged).
- `HistoricalAnalyticsResult.benchmark: BenchmarkRelativeRisk | None` (default `None`).
- Same `POST /risk/historical-analytics` and `POST /api/v1/risk/historical-analytics` routes. No new engine, no frontend.

## Numerical conventions
- Units: excess return is fraction (`W_p - W_b`); beta and correlation are dimensionless; tracking error is annualized fraction (`std(r_p - r_b, ddof) × sqrt(periods_per_year)`); relative drawdown is `rel_t / peak(rel) - 1` with `rel = W_p / W_b` and implicit start 1 (≤ 0); benchmark VaR/ES are currency loss (≥ 0).
- Sign: relative drawdown follows G1 drawdown (peak-relative, negative or zero). Excess return is portfolio minus benchmark terminal wealth (both start at 1).
- Annualization: same `AnnualizationConvention` as G1 (default 252, sample `ddof=1`).
- Beta: `cov(r_p, r_b) / var(r_b)` with convention `ddof`; fail closed if `var(r_b)=0`.
- Alignment: exact date intersection; insufficient overlap (`< 2` dates) fails closed; missing `EquitySpot:SPY` fails closed (no substitute).
- Benchmark book: `quantity = portfolio_mv / SPY_spot` so notional matches the analysis book; engine VaR/ES on that book.
- Tolerances: `1e-12` linear identities; `1e-10` annualized TE.

## Tests added
- identical series → beta ≈ 1, TE ≈ 0, excess ≈ 0, relative drawdown ≈ 0
- uncorrelated orthogonal series → beta ≈ 0, correlation ≈ 0
- shifted dates → calendar intersection, not positional zip (would have been beta=1)
- insufficient overlap → fail closed (helper + n=1 compute)
- missing SPY factor → fail closed
- percent/fraction: beta dimensionless; TE annualized fraction; excess not 100×
- benchmark VaR/ES equals `HistoricalRiskEngine.calculate` on the SPY book
- zero `var(r_b)` → fail closed
- G1 path without flag leaves `benchmark is None`
- API identity echo with `include_benchmark=true` (no provider HTTP)

## Commands executed

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_historical_analytics.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_historical_analytics.py tests/test_endpoint_execution_class.py tests/test_api_v1_compatibility.py tests/test_api_router_decomposition.py tests/test_api.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line tests/test_historical_analytics.py tests/test_historical_data.py tests/test_factor_panel_historical.py
.venv/bin/ruff check app/risk/historical_analytics.py app/services/portfolio_service.py tests/test_historical_analytics.py
```

## Results
- RED: `ImportError: cannot import name 'WAVE_A_BENCHMARK_FACTOR'`
- GREEN focused analytics: **23 passed** (`tests/test_historical_analytics.py`)
- GREEN analytics + execution/API/router: **58 passed**, 1 Starlette TestClient deprecation warning (pre-existing)
- GREEN analytics + historical dataset/panel: **39 passed**, same warning
- Ruff on touched files: passed
- Frontend: not in scope
- CI: not started

- All applicable/affected suites required by this task: **yes** (local)
- Unexplained failures or skips: none
- CI is green: **not started**

## Known limitations / risks
- G2 is **not DONE**: independent review + CI still required.
- `include_benchmark` defaults to `False` so G1 AAA-only panels and the existing API test stay valid. Callers must opt in.
- Opt-in still fail-closes if SPY is missing from the sliced panel or the snapshot has no non-zero SPY spot.
- Benchmark VaR/ES is same-notional 1-name SPY book engine risk, not return-series quantile risk.
- Date intersection with a rectangular panel equals the G1 sliced window; shifted-date protection is in `align_dated_series` (used by the compute path).
- G1 minors not reopened: LINEAR vs DELTA_GAMMA `compute()` default; n<2 vol=0.0; rf unit implicit; Sharpe uses CAGR numerator.

## Follow-up / next owner
- Owner: Independent Reviewer, then Lead Architect for G2 close.
- Requested action: hostile-ish review of beta denominator, TE annualization, percent/fraction, relative-drawdown sign, benchmark date mismatch; then CI.
- Blocking for G2 DONE: yes (review + CI).
