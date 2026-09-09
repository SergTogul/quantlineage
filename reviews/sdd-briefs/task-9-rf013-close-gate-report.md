# Task 9 Report — RF-013 canonical identity close (remaining HTTP pin)

## Task
RF-013 canonical identity close (or remaining HTTP pin)

## Owner
Backend / API Engineer

## Status
**IN PROGRESS** (KEEP OPEN; do not CLOSE RF-013)

## Summary
R0.8.3 already stopped RiskRun submit from upserting a stored book. This slice adds the missing **HTTP `global-macro` pin**: persistence-enabled `POST /api/v1/risk/runs` and `/risk/runs` with attacker trades under `id=global-macro` leave the seeded Cross-Asset book unchanged (`GET /portfolio`, SQL row, catalog `GET /portfolios/global-macro`). Other FINDINGS cells are cited, not duplicated: same-spec reproduction (R0.8.5 / RF-009 CLOSED), Postgres lifecycle (R0.8.5). Cell 4 (PERF-016 / `risk_results.payload`) is **UNMET** — R0.8.4 typed request bodies are not that cell. **Disposition: IN PROGRESS.** Demo snapshot/position contracts were not changed. Production pricing/risk code was not changed (`_book_for_run` attach-stored verified by a temporary upsert RED probe, then restored).

## Files changed
- `backend/tests/test_portfolio_identity.py` — Cross-Asset worker + HTTP overwrite pins
- `reviews/FINDINGS.md` — RF-013 **IN PROGRESS**; cell 4 **UNMET**
- `reviews/REMEDIATION_MILESTONE.md` — R0.8.6; related-findings pointers
- `reviews/r0.8.6-rf013-close-gate-report.md` — scoring report
- `reviews/sdd-briefs/task-9-rf013-close-gate-report.md` — this handoff

## Public/interface changes
- None. Overwrite semantics remain: persist submit create-if-absent or **attach stored book** (does not upsert). No new HTTP create/update portfolio routes. Catalog GET still serves in-code `app.sample`.

## Numerical conventions
- Units: unchanged
- Sign convention: unchanged
- Day count/calendar if relevant: n/a
- Tolerances/reference: identity only (ids, name, desk, quantities); no VaR/ES goldens in this slice

## Tests added/updated
- `test_submit_cannot_overwrite_seeded_global_macro` — worker submit against seeded SAMPLE / `global-macro` keeps Cross-Asset trades
- `test_http_post_run_cannot_overwrite_seeded_global_macro` — HTTP dual-mount POST cannot clobber seed; catalog GET order unchanged

## Commands executed
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_portfolio_identity.py \
  tests/test_same_spec_parity.py

.venv/bin/ruff check tests/test_portfolio_identity.py
```

## Results
- Backend required suite: **13 passed**, 1 pre-existing Starlette `TestClient` deprecation warning
- Ruff: all checks passed
- Frontend: n/a
- QuantLib: n/a
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## MET vs PARTIAL vs UNMET (this gate)

Acceptance: overwrite `global-macro` **MET**; reproduce from IDs **MET** (cite R0.8.5); Postgres **MET** (cite R0.8.5); unconstrained derived JSON / `risk_results.payload` **UNMET** (R0.8.4 typed request bodies are not PERF-016).

Required direction: create vs update **MET**; inline calculate **PARTIAL** (live calculate still POSTs a full book); versioned identities **PARTIAL** (no `portfolio_version`); server ownership **PARTIAL** (attach-stored; leftover `save`; ACLs = RF-014).

## Why IN PROGRESS (not CLOSE)
Cell 4 is UNMET. HTTP pin against the seeded Cross-Asset id is real and stays, but it does not close canonical identity. Residuals: no `portfolio_version` / server-issued ids; live calculate still POSTs a full book; leftover `save` upsert for seed callers; object ACLs = RF-014. Would not defend CLOSE.

## Known limitations / risks
- No `portfolio_version` / server-issued portfolio ids (first persist still client-chosen create-if-absent)
- Live calculate still POSTs a full book
- Legacy `save` upsert remains for seed callers
- Attach ignores a differing POST body (not 409)
- SQL trade reload does not preserve insert order
- Object ACLs are RF-014
- `risk_results.payload` remains unconstrained JSON (PERF-016)

## Follow-up / next owner
- Owner: independent reviewer (Task 9 review)
- Requested action: KEEP OPEN; do not CLOSE RF-013
- Blocking?: no for other P1s; RF-013 stays IN PROGRESS until residuals and cell 4 are actually met

## Post-review fix note (2026-09-09)

Independent review KEEP OPEN. Implementer CLOSE was a rubber-stamp. Corrected on this slice:

- RF-013 Status reverted **CLOSED → IN PROGRESS**. Do not CLOSE.
- FINDINGS acceptance cell 4 scored **UNMET** (not MET): unconstrained derived JSON / `risk_results.payload` is PERF-016; R0.8.4 typed request bodies are not that cell.
- Honest residuals: no `portfolio_version` / server-issued ids; live calculate still POSTs a full book; leftover `save` upsert for seed callers; object ACLs = RF-014.
- HTTP `global-macro` overwrite tests kept (`test_http_post_run_cannot_overwrite_seeded_global_macro`).
- Docs aligned: `reviews/FINDINGS.md`, `reviews/REMEDIATION_MILESTONE.md`, `reviews/r0.8.6-rf013-close-gate-report.md`.

Tests re-run after the docs correction:

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_portfolio_identity.py \
  tests/test_same_spec_parity.py
```

Result: **13 passed**, 1 pre-existing Starlette `TestClient` deprecation warning. HTTP identity pins unchanged.
