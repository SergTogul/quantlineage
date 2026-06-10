# Task 22 Report — RF-013 typed risk_results.payload (R0.8.7)

## Task
RF-013 / R0.8.7 — typed `risk_results.payload`

## Owner
Backend / API Engineer (`docs/agents/07_BACKEND_API_ENGINEER.md`)

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-013)

## Summary
Persisted derived results now validate against a known schema per `result_type` (`extra='forbid'`). `SqlAlchemyRiskRunRepository.add_result`, `InMemoryRiskRunRepository.add_result`, and `RiskRunService.complete` fail closed on unknown types and extra keys. Existing domain/API result models are reused (VaR, stress, reverse, summary, dashboard, query, …); list run types keep the worker `{"items": [...]}` envelope. Physical JSON column remains; unconstrained `dict[str, Any]` writes are rejected. FINDINGS cell 4 is **MET**. **Disposition: IN PROGRESS** — `portfolio_version` / server-issued ids, live full-book calculate, leftover `save` upsert, and RF-014 ACLs remain.

TDD: unknown-type and extra-key pins failed first (writes were accepted). Then green. Stub lifecycle payloads were replaced with valid `RiskSummary` JSON so existing lifecycle / same-spec / `global-macro` pins still pass.

## Files changed
- `backend/app/persistence/result_payloads.py` — schema map + `parse_result_payload`
- `backend/app/persistence/sqlalchemy_repos.py` — validate on `add_result`
- `backend/app/persistence/memory_repos.py` — validate on `add_result`
- `backend/app/persistence/models.py` — comment only (no Alembic)
- `backend/app/services/risk_run_service.py` — validate on `complete`
- `backend/tests/test_result_payload_schema.py` — new pins
- `backend/tests/test_persistence.py`, `test_risk_run.py`, `test_risk_run_lifecycle.py`, `test_risk_run_api.py` — valid summary payloads
- `reviews/FINDINGS.md` — RF-013 **IN PROGRESS**; cell 4 **MET**
- `reviews/REMEDIATION_MILESTONE.md` — R0.8.7 COMPLETE; finding stays open
- `reviews/r0.8.7-typed-result-payload-report.md`
- `reviews/sdd-briefs/task-22-rf013-typed-payload-report.md` — this handoff

## Public/interface changes
- `parse_result_payload(result_type, payload) -> dict` (persistence write gate)
- `add_result` / `complete` reject unknown `result_type` (`ValueError`) and extra/invalid keys (`ValidationError` / `ValueError`)
- No HTTP path change. No table rewrite. No VaR/demo snapshot identity change

## Numerical conventions
- Units: unchanged
- Sign convention: unchanged
- Day count/calendar if relevant: n/a
- Tolerances/reference: same-spec exact payload equality (`test_same_spec_parity.py`); schema validate does not re-dump stored JSON

## Tests added/updated
- `test_unknown_result_type_fails_closed_on_sqlalchemy_add_result`
- `test_unknown_result_type_fails_closed_on_memory_add_result`
- `test_extra_keys_fail_on_sqlalchemy_add_result`
- `test_extra_keys_fail_on_complete`
- `test_known_summary_payload_round_trips_sqlalchemy`
- `test_known_summary_payload_round_trips_via_complete`
- `test_payload_schemas_cover_supported_run_types`
- `test_execute_run_type_payload_validates` (summary/var/stress/factors/dashboard)

## Commands executed
TDD red (new file, before production change):

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_result_payload_schema.py
```

Result: **4 failed, 2 passed** (unknown type / extra keys did not raise).

Brief + covering (after implement):

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_result_payload_schema.py \
  tests/test_persistence.py \
  tests/test_risk_run.py \
  tests/test_risk_run_lifecycle.py \
  tests/test_risk_run_api.py \
  tests/test_same_spec_parity.py \
  tests/test_portfolio_identity.py \
  tests/test_durable_worker.py
```

Note: brief named `tests/test_risk_run_service.py` and `tests/test_risk_run_worker.py`; those files are not in the tree. Lifecycle/API/durable-worker modules cover the same paths.

```bash
.venv/bin/ruff check \
  app/persistence/result_payloads.py \
  app/persistence/sqlalchemy_repos.py \
  app/persistence/memory_repos.py \
  app/persistence/models.py \
  app/services/risk_run_service.py \
  tests/test_result_payload_schema.py \
  tests/test_risk_run.py \
  tests/test_risk_run_lifecycle.py \
  tests/test_risk_run_api.py
```

## Results
- Backend required suite: **112 passed**, 1 pre-existing Starlette `TestClient` deprecation warning
- Ruff: all checks passed (changed files)
- Frontend: n/a
- QuantLib: n/a
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## MET vs PARTIAL vs UNMET (this gate)

Acceptance: overwrite `global-macro` **MET** (cite R0.8.6); reproduce from IDs **MET** (cite R0.8.5); Postgres **MET** (cite R0.8.5); unconstrained derived JSON / `risk_results.payload` **MET** (this slice). R0.8.4 typed request bodies are not this cell.

Required direction: create vs update **MET**; inline calculate **PARTIAL**; versioned identities **PARTIAL**; server ownership **PARTIAL**.

## Why IN PROGRESS (not CLOSE)
Cell 4 is MET. Residuals remain: no `portfolio_version` / server-issued ids; live calculate still POSTs a full book; leftover `save` upsert for seed callers; object ACLs = RF-014. Would not defend CLOSE.

## Known limitations / risks
- No `portfolio_version` / server-issued portfolio ids
- Live calculate still POSTs a full book
- Legacy `save` upsert remains for seed callers
- Physical JSON column remains (size/object-store is not this slice)
- Nested domain models that default `extra='ignore'` rely on dump-vs-raw extra-key reject

## Follow-up / next owner
- Owner: independent reviewer (Task 22 review)
- Requested action: KEEP OPEN; do not CLOSE RF-013
- Blocking?: no for other P1s; next RF-013 slice is `portfolio_version` / server-issued ids (or live calculate / leftover `save`)
