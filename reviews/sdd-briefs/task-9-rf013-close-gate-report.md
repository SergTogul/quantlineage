# Task 9 Report — RF-013 canonical identity close (remaining HTTP pin)

## Task
RF-013 canonical identity close (or remaining HTTP pin)

## Owner
Backend / API Engineer

## Status
**DONE** (CLOSE recommended; not final until independent review APPROVE)

## Summary
R0.8.3 already stopped RiskRun submit from upserting a stored book. This slice adds the missing **HTTP `global-macro` pin**: persistence-enabled `POST /api/v1/risk/runs` and `/risk/runs` with attacker trades under `id=global-macro` leave the seeded Cross-Asset book unchanged (`GET /portfolio`, SQL row, catalog `GET /portfolios/global-macro`). Other FINDINGS cells are cited, not duplicated: same-spec reproduction (R0.8.5 / RF-009 CLOSED), Postgres lifecycle (R0.8.5), typed requests (R0.8.4). **Disposition: CLOSE.** Demo snapshot/position contracts were not changed. Production pricing/risk code was not changed (`_book_for_run` attach-stored verified by a temporary upsert RED probe, then restored).

## Files changed
- `backend/tests/test_portfolio_identity.py` — Cross-Asset worker + HTTP overwrite pins
- `reviews/FINDINGS.md` — RF-013 **CLOSED** pending independent review; acceptance cells scored MET
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

Acceptance: overwrite `global-macro` **MET**; reproduce from IDs **MET** (cite R0.8.5); Postgres **MET** (cite R0.8.5); typed requests **MET** (cite R0.8.4).

Required direction: create vs update **MET**; inline calculate **MET**; versioned identities **PARTIAL** (no `portfolio_version`); server ownership **PARTIAL** (attach-stored; leftover `save`; ACLs = RF-014).

## Why CLOSE (not IN PROGRESS)
All four acceptance cells are MET. HTTP pin against the seeded Cross-Asset id was the remaining gap. Versioned/server-issued ids were never an acceptance cell; they stay named residuals. Would defend CLOSE to a second reviewer if those residuals stay PARTIAL.

## Known limitations / risks
- No `portfolio_version` / server-issued portfolio ids (first persist still client-chosen create-if-absent)
- Legacy `save` upsert remains for seed callers
- Attach ignores a differing POST body (not 409)
- SQL trade reload does not preserve insert order
- Object ACLs are RF-014
- Independent review may KEEP OPEN; CLOSED is a recommendation with placeholder

## Follow-up / next owner
- Owner: independent reviewer (Task 9 review)
- Requested action: APPROVE or KEEP OPEN against FINDINGS acceptance cells; do not restamp CLOSE without the HTTP pin
- Blocking?: no for other P1s; RF-013 CLOSED is not final until review APPROVE
