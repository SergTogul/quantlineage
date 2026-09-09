# Task 18 Report — RF-010 explicit application composition (R0.9.3)

## Task
RF-010 / R0.9.3 — explicit application composition

## Owner
Backend / API Engineer (`docs/agents/07_BACKEND_API_ENGINEER.md`)

## Status
**CLOSED** (four FINDINGS acceptance cells MET; independent review pending)

## Summary
Removed `app.api.deps.portfolio_service = build_portfolio_service()` at import.
Lifespan constructs one `PortfolioService` via the same factory, stores it on
`app.state`, and passes it to `RiskRunWorker`. HTTP `get_portfolio_service(request)`
reads `app.state`. `app.main.service` is a thin alias to that instance.
Legacy TestClient without lifespan falls back to the same factory (pinned; no
503). No DI container. Risk numbers unchanged.

TDD: five composition pins failed first (module-global assignment present;
Depends had no `Request`; `app.state.portfolio_service` missing). Then green.

**Disposition: CLOSED** — domain without FastAPI; schemas split; typed results;
explicit composition. Dual-use `AttributionRequest` in domain is a named residual.

## Files changed
- `backend/app/api/deps.py` — lifespan/`app.state` Depends; factory fallback
- `backend/app/main.py` — construct service + worker in lifespan; `service` alias
- `backend/app/services/risk_factories.py` — docstring
- `backend/tests/test_application_composition.py` — new pins
- `backend/tests/test_risk_run_api.py` — mutate `app.state` not module singleton
- `backend/tests/test_persistence_di.py` — same
- `backend/tests/test_workload_limits.py` — same
- `reviews/FINDINGS.md` — RF-010 **CLOSED**
- `reviews/REMEDIATION_MILESTONE.md` — R0.9.3 COMPLETE
- `reviews/r0.9.3-application-composition-report.md`
- `reviews/sdd-briefs/task-18-rf010-composition-report.md` — this handoff

## Public/interface changes
- `get_portfolio_service(request: Request) -> PortfolioService` reads `app.state`
- `app.main.service` is a dynamic alias (module `__getattr__`)
- Module-global `deps.portfolio_service` assignment removed

## Numerical conventions
- Units: unchanged
- Sign convention: unchanged
- Day count/calendar if relevant: n/a
- Tolerances/reference: no risk-number changes

## Tests added/updated
- `test_deps_does_not_assign_module_global_portfolio_service`
- `test_get_portfolio_service_takes_request_like_worker`
- `test_lifespan_sets_portfolio_service_on_app_state`
- `test_http_depends_reads_app_state_portfolio_service`
- `test_main_service_aliases_lifespan_instance`
- `test_composition_modules_do_not_import_di_container`
- `test_http_portfolio_service_fallback_without_lifespan`

## Commands executed
TDD red (new file, before production change): 5 failed as expected
(module-global assignment; no `request` param; `app.state.portfolio_service`
missing). DI-container pin and no-lifespan HTTP 200 already green (existing
singleton still served HTTP).

Brief (required):

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_application_composition.py tests/test_api_error_model.py \
  tests/test_risk_run_api.py tests/test_persistence_di.py \
  tests/test_domain_transport_split.py tests/test_typed_risk_results.py
```

Covering:

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line
```

## Results
- Backend required suite: **60 passed**, 1 warning (Starlette TestClient httpx deprecation, pre-existing)
- Full backend: **1394 passed**, 9 skipped, 1 warning in 74.66s
- Frontend: not run (out of scope)
- QuantLib: not run (out of scope)
- C++: not run (out of scope)
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): yes
- Unexplained failures or skips: none (9 skips pre-existing)
- CI is green (all required checks): not started

Exact required-suite result:

```text
60 passed, 1 warning in 11.09s
```

The warning is pre-existing (`StarletteDeprecationWarning` from FastAPI TestClient
httpx). No unexplained skips.

## Known limitations / risks
- Dual-use `AttributionRequest`, `RiskChangeAttributionRequest`, and
  `WhatIfRequest` remain in domain (named residual; not KEEP OPEN)
- TestClient without lifespan uses a lazy factory fallback distinct from a
  later lifespan instance in the same pytest process; production has one
- `PortfolioService` is still a large orchestrator (split out of scope)

## Follow-up / next owner
- Owner: Lead Architect / independent reviewer
- Requested action: independent review of RF-010 CLOSE
- Blocking?: no
