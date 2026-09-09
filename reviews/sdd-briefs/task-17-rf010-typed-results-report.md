# Task 17 Report — RF-010 typed RiskEngine.calculate (R0.9.2)

## Task
RF-010 / R0.9.2 — typed `RiskEngine.calculate`

## Owner
Portfolio Risk Engineer (`docs/agents/04_PORTFOLIO_RISK_ENGINEER.md`)

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-010)

## Summary
`RiskEngine.calculate` now returns existing domain `RiskSummary` instead of
`dict[str, float]`. `HistoricalRiskEngine.calculate` fills `portfolio_id` from
`portfolio.id` and keeps the same numeric keys/values as today’s dict. Callers
(`PortfolioService`, hierarchy, limits, limit drilldown, incremental VaR,
var-compare, stress comparison, risk-change attribution, tests) use the typed
object. A `.model_dump()` / FastAPI serialize remains only at HTTP/JSON edges.
VaR/ES formulas unchanged. No DI container. No FastAPI in `app.risk` /
`app.domain`.

**Disposition: IN PROGRESS** — R0.9.3 lifespan composition remains. Dual-use
engine/service inputs (`AttributionRequest`, `RiskChangeAttributionRequest`,
`WhatIfRequest`) stay in domain.

TDD: ABC annotation failed first (`dict[str, float]`); live `calculate` was a
bare dict until `RiskSummary` was returned. Then green.

## Files changed
- `backend/app/interfaces/risk.py` — ABC returns `RiskSummary`
- `backend/app/risk/historical.py` — return `RiskSummary`
- `backend/app/services/portfolio_service.py` — typed summary; limit `extra`
- `backend/app/risk/hierarchy.py` — attribute access
- `backend/app/risk/limits.py` — `RiskSummary` + optional overlay `extra`
- `backend/app/risk/incremental_var.py` — drop dict-to-summary adapter
- `backend/app/risk/var_compare.py` — attribute access
- `backend/app/risk/stress.py` — typed `_risk_summary`
- `backend/app/risk/risk_attribution.py` — `getattr` on `RiskSummary`
- `backend/tests/test_typed_risk_results.py` — new pin
- caller tests updated from dict subscript to attributes
- `reviews/FINDINGS.md` — RF-010 **IN PROGRESS** with R0.9.2 residual
- `reviews/REMEDIATION_MILESTONE.md` — R0.9.2 COMPLETE; finding stays open
- `reviews/r0.9.2-typed-risk-results-report.md`
- `reviews/sdd-briefs/task-17-rf010-typed-results-report.md` — this handoff

## Public/interface changes
- `RiskEngine.calculate(...) -> RiskSummary`
- `LimitEngine.evaluate` / `resolve_metrics` take `RiskSummary`; overlay metrics
  via optional `extra: Mapping[str, float]`
- HTTP JSON field names for `RiskSummary` unchanged

## Numerical conventions
- Units: currency P&L / loss VaR and ES (unchanged)
- Sign convention: loss = -P&L; VaR/ES floored at 0 (unchanged)
- Day count/calendar if relevant: n/a
- Tolerances/reference: `test_var_es_golden.py` abs 1e-12; incremental 1e-9

## Tests added/updated
- `test_risk_engine_abc_calculate_returns_risk_summary`
- `test_historical_engine_calculate_is_risk_summary_not_dict`
- `test_app_risk_and_domain_do_not_import_fastapi`
- Dict-subscript callers updated to attributes (`test_var_es_golden`,
  `test_incremental_var`, `test_var_compare`, hierarchy, limits, …)

## Commands executed
TDD red (new file, before production change): 2 failed as expected
(ABC return `dict[str, float]`; `calculate` returned a dict). FastAPI pin already green.

Brief (required):

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_typed_risk_results.py tests/test_omit_market.py \
  tests/test_var_es_golden.py tests/test_incremental_var.py \
  tests/test_var_compare.py tests/test_hierarchy_artifact_var.py
```

Covering:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_risk.py tests/test_limits.py tests/test_limit_drilldown.py \
  tests/test_hierarchy.py tests/test_hierarchy_node_ids.py tests/test_what_if.py \
  tests/test_var_methodology.py tests/test_full_reval_golden.py \
  tests/test_historical_data.py tests/test_demo_historical_dataset.py \
  tests/test_historical_scenario_kernel.py tests/test_factor_panel_historical.py \
  tests/test_quant_properties.py tests/test_m9_risk_properties.py
```

Also: `tests/test_stress.py tests/test_risk_attribution.py tests/test_attribution.py`

Ruff:

```bash
.venv/bin/ruff check app/interfaces/risk.py app/risk/historical.py \
  app/risk/hierarchy.py app/risk/limits.py app/risk/incremental_var.py \
  app/risk/var_compare.py app/risk/risk_attribution.py \
  app/services/portfolio_service.py tests/test_typed_risk_results.py \
  tests/test_omit_market.py tests/test_var_es_golden.py \
  tests/test_incremental_var.py tests/test_var_compare.py tests/test_limits.py
```

## Results
- Backend required suite: **54 passed**, 1 warning
- Covering caller suite: **123 passed**, 1 warning
- Stress/attribution covering: **29 passed**, 1 warning
- Ruff (changed files): All checks passed
- Frontend: not run (out of scope)
- QuantLib: not run (out of scope)
- C++: not run (out of scope)
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): yes
- Unexplained failures or skips: none
- CI is green (all required checks): not started

Exact required-suite result:

```text
54 passed, 1 warning in 5.85s
```

The warning is pre-existing (`StarletteDeprecationWarning` from FastAPI TestClient
httpx). No skips.

## Known limitations / risks
- `app.risk.query` still imports HTTP `RiskQueryResponse` from `api.schemas`
  (R0.9.1 leftover; not FastAPI)
- `AttributionRequest`, `RiskChangeAttributionRequest`, and `WhatIfRequest`
  remain dual-use in domain
- Process-global `PortfolioService` orchestration remains (R0.9.3)
- Limit overlay (`stress_loss` / injected `key_rate_dv01`) is not on `RiskSummary`

## Follow-up / next owner
- Owner: Backend / Architecture
- Requested action: R0.9.3 lifespan composition. Do not CLOSE RF-010.
- Blocking?: no
