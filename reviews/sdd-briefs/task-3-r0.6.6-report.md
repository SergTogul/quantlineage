# Task 3 Report — R0.6.6 Contribution reuse

## Task

R0.6.6 — Contribution reuse (avoid whole-book full reval once per factor family).

## Owner

Portfolio Risk Engineer.

## Summary

Stopped family-isolated whole-book repricing on full-reval contribution paths. ES factor helpers and scenario-attribution factor buckets reuse joint trade/scenario P&L plus one base Δ-Γ Greek split; `interaction` still reconciles to portfolio ES / stress P&L. RF-007 remains `IN PROGRESS`.

## Files Changed

- `backend/app/risk/es.py`
- `backend/app/risk/scenario_attribution.py`
- `backend/tests/test_contribution_reuse.py`
- `backend/tests/test_es_contributions.py`
- `backend/tests/test_scenario_attribution.py`
- `reviews/FINDINGS.md`
- `reviews/REMEDIATION_MILESTONE.md`
- `reviews/r0.6.6-contribution-reuse-report.md`
- `reviews/sdd-briefs/task-3-r0.6.6-report.md`

## Public / Interface Changes

- None. `ESContributionAnalytics.report` and `ScenarioAttributionEngine.decompose` signatures unchanged.
- Factor contribution *meaning* on FULL_REVAL / stress factor buckets is now Taylor-plus-residual of the joint P&L, not isolated full reval per family.

## Numerical Conventions

- Units: unchanged.
- Sign convention: unchanged.
- Day count/calendar: n/a.
- Tolerances/reference: cash-equity FULL vs LINEAR factor P&L abs `1e-12`; existing reconcile abs `1e-6` / rel `1e-8` in `test_es_contributions.py` / `test_scenario_attribution.py`. Portfolio FULL_REVAL VaR/ES identity unchanged.

## Tests Added / Updated

- Added `test_full_reval_factor_helper_does_not_apply_or_value_per_family`.
- Added `test_full_reval_panel_factor_helper_does_not_apply_per_family`.
- Added `test_full_reval_factor_pnl_matches_linear_for_cash_equity`.
- Added `test_es_full_reval_report_value_calls_do_not_scale_with_families`.
- Added `test_es_full_reval_cash_equity_matches_linear_factor_es`.
- Added `test_scenario_attribution_does_not_apply_isolated_factor_scenarios`.
- Added `test_formal_scenario_factor_reuse_reconciles_without_extra_apply`.
- Comment-only updates on existing ES / scenario-attribution convention headers.

## Commands Executed

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_contribution_reuse.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_contribution_reuse.py \
  tests/test_es_contributions.py \
  tests/test_var_methodology.py \
  tests/test_var_es_golden.py \
  tests/test_scenario_attribution.py \
  tests/test_pricing_anti_cache.py \
  tests/test_panel_contributions.py \
  tests/test_stress.py \
  tests/test_shock_units.py
.venv/bin/python -m ruff check app/risk/es.py app/risk/scenario_attribution.py tests/test_contribution_reuse.py tests/test_es_contributions.py tests/test_scenario_attribution.py
.venv/bin/python -m mypy app/risk/es.py app/risk/scenario_attribution.py
cd /Users/user/src/quantlineage && /usr/bin/git diff --check
```

`tests/test_es.py` / `tests/test_var.py` from the brief do not exist; `test_es_contributions.py` and `test_var_methodology.py` / `test_var_es_golden.py` are the focused stand-ins, plus new reuse tests.

## Results

- New reuse tests RED before implementation: per-family `value`/`apply` counts (e.g. 32 vs 2 values; isolated scenario ids).
- New reuse tests after implementation: `7 passed`.
- Brief-equivalent focused suite (new reuse tests + ES contributions + VaR methodology/golden + attribution + anti-cache + panel + stress + shock units): **79 passed**, 1 pre-existing Starlette `TestClient` deprecation warning (`test_es_api_endpoint_default_methodology`).
- Ruff on `es.py`, `scenario_attribution.py`, `test_contribution_reuse.py`: passed.
- `mypy` on touched modules: blocked by pre-existing `app/risk/historical_data.py` protocol errors (3); no diagnostics in `es.py` / `scenario_attribution.py`.
- `git diff --check`: passed.
- CI green: not started from this subtask; local focused verification above.

## Known Limitations / Risks

- RF-007 is not closed. Joint N×S full-reval pricing, R0.6.5 process partitioning, and N=100/1k benches remain.
- Factor *bucket* amounts for books with options / cross-factor effects are no longer isolated-family full revals; the difference sits in `interaction`. Portfolio ES / trade P&L unchanged.
- Equity options expose no `dv01`; rate effects of full reval vs the Greek split land in `interaction`.
- `required_factors_for_position` still omits rates on equity options; unmapped instruments (`TypeError`) fall through to Greeks (zeros if insensitive).

## Follow-Up / Handoff

- Owner: Lead Architect / Backend for R0.6.5; later RF-007 close gate.
- Requested action: independent review of R0.6.6; keep RF-007 open.
- Blocking: no for this slice.
