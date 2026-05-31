# Task 16 Report — RF-010 split HTTP request/response DTOs out of domain (R0.9.1)

## Task
RF-010 / R0.9.1 — split HTTP request/response DTOs out of domain

## Owner
Backend / API Engineer (`docs/agents/07_BACKEND_API_ENGINEER.md`)

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-010)

## Summary
Obvious HTTP request/response bodies were moved from `backend/app/domain/models.py`
to `backend/app/api/schemas/` (`transport.py`, re-exported from `__init__.py`).
Domain entities (`Position`, `Portfolio`, `MarketSnapshot`, `StressScenario`,
risk *result* types, `RiskRun`) stay in domain. Domain does not import FastAPI
or `app.api`. JSON field names, `FiniteFloat`, and existing `extra='forbid'`
behavior are unchanged. No DI container; no one-file-per-class churn. Demo
snapshot ids and numerical methodology were not touched.

**Disposition: IN PROGRESS** — R0.9.2 typed risk results and R0.9.3 lifespan
composition remain. Dual-use engine/service inputs (`AttributionRequest`,
`RiskChangeAttributionRequest`, `WhatIfRequest`) were left in domain.

TDD: domain pin failed first (`HTTP transport types still in domain.models`);
`app.api.schemas` import failed until the move. Then green.

## Files changed
- `backend/app/api/schemas/transport.py` — HTTP bodies + parse/dump helpers
- `backend/app/api/schemas/__init__.py` — package re-exports
- `backend/app/domain/models.py` — HTTP bodies removed
- `backend/app/api/__init__.py` — R0.9.1 note
- `backend/app/api/stress.py` — schema imports
- `backend/app/api/risk.py` — `RiskQueryRequest` from schemas
- `backend/app/api/limits.py` — `LimitDrilldownRequest` from schemas
- `backend/app/api/risk_runs.py` — `RiskRunCreateRequest` / `RiskRunView`
- `backend/app/services/portfolio_service.py`
- `backend/app/services/risk_factories.py`
- `backend/app/services/risk_run_worker.py`
- `backend/app/risk/query.py` — `RiskQueryResponse` from schemas
- `backend/tests/test_domain_transport_split.py` — new pin
- `backend/tests/test_limit_drilldown.py`
- `backend/tests/test_risk_run_spec.py`
- `backend/tests/test_ai_query_orchestration.py`
- `reviews/FINDINGS.md` — RF-010 **IN PROGRESS** with R0.9.1 residual
- `reviews/REMEDIATION_MILESTONE.md` — R0.9.1 COMPLETE; finding stays open
- `reviews/r0.9.1-split-transport-schemas-report.md`
- `reviews/sdd-briefs/task-16-rf010-split-schemas-report.md` — this handoff

## Public/interface changes
- HTTP DTOs import from `app.api.schemas` instead of `app.domain.models`
- Wire JSON field names unchanged
- OpenAPI component names unchanged (`CustomStressRequest`, `RiskRunView`, …)
- Formal Scenario wire remains in `app.api.scenario_wire`

## Numerical conventions
- Units: n/a (schema ownership move only)
- Sign convention: n/a
- Day count/calendar if relevant: n/a
- Tolerances/reference: n/a — no VaR/stress formula change

## Tests added/updated
- `test_domain_package_does_not_import_fastapi` — domain has no FastAPI / `app.api` imports
- `test_domain_models_does_not_define_http_transport_bodies` — denylist of HTTP bodies
- `test_http_transport_bodies_live_in_api_schemas` — names exported from `app.api.schemas`
- `test_moved_http_bodies_keep_forbid_and_json_field_names` — field names + RiskRun `extra='forbid'`

Left in domain (not HTTP-only): `AttributionRequest`, `RiskChangeAttributionRequest`,
`WhatIfRequest` / `WhatIfChange`.

## Commands executed
TDD red (new file, before production change): 3 failed as expected
(HTTP names still in `domain.models`; `app.api.schemas` missing). 1 already-green
pin (domain does not import FastAPI).

Brief (required):

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_domain_transport_split.py \
  tests/test_api_error_model.py tests/test_risk_run_api.py \
  tests/test_stress.py tests/test_finite_scalars.py
```

Covering:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_limit_drilldown.py tests/test_risk_run_spec.py \
  tests/test_ai_query_orchestration.py tests/test_api_typed_models.py \
  tests/test_risk_run_factories.py tests/test_api_router_decomposition.py
```

Ruff:

```bash
.venv/bin/ruff check app/api/schemas app/api/stress.py app/api/risk.py \
  app/api/limits.py app/api/risk_runs.py app/api/__init__.py \
  app/domain/models.py app/services/portfolio_service.py \
  app/services/risk_factories.py app/services/risk_run_worker.py \
  app/risk/query.py tests/test_domain_transport_split.py \
  tests/test_limit_drilldown.py tests/test_risk_run_spec.py \
  tests/test_ai_query_orchestration.py
```

## Results
- Backend required suite: **74 passed**, 1 warning
- Covering import-site suite: **95 passed**, 1 warning
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
74 passed, 1 warning in 7.17s
```

The warning is pre-existing (`StarletteDeprecationWarning` from FastAPI TestClient
httpx). No skips.

## Known limitations / risks
- `AttributionRequest`, `RiskChangeAttributionRequest`, and `WhatIfRequest` remain
  dual-use (HTTP body + engine/service input) in domain — left by design this slice
- `app.risk.query` now imports HTTP `RiskQueryResponse` from `api.schemas`
  (application/result typing is R0.9.2)
- `PortfolioService.limit_drilldown` still takes the HTTP `LimitDrilldownRequest`
- `RiskEngine.calculate` remains an untyped dict (R0.9.2)
- Process-global `PortfolioService` orchestration remains (R0.9.3)
- Formal Scenario wire DTOs stay in `app.api.scenario_wire` (already API-owned)

## Follow-up / next owner
- Owner: Backend / Architecture
- Requested action: R0.9.2 typed risk results; then R0.9.3 lifespan composition.
  Do not CLOSE RF-010.
- Blocking?: no
