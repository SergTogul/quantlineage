# Task 15 Report — RF-014 local-demo close gate

## Task
RF-014 local-demo close gate (R0.11.7)

## Owner
QA & Quant Validation Engineer (`docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`)

## Status
**CLOSED** pending independent review APPROVE. Disposition: **CLOSE**. Shared-profile ACLs / TLS / secrets are accepted residuals (not MET).

## Summary
Independent re-score of RF-014 against FINDINGS local-demo vs shared vs production-like required direction, with file:evidence. R0.11.1–R0.11.6 APPROVE were re-checked on disk and with a focused suite (**87 passed**), not rubber-stamped. Local-demo loopback, finite numbers, payload caps, sanitization, and the shared-token gate are **MET**. Local demo stays unauthenticated. Object ACLs, TLS/reverse-proxy, and secret management are **UNMET** and recorded as R0 accepted residuals — not called MET. No IAM/TLS invented. Docs-only; no local-demo hole required a pin.

## Files changed
- `reviews/FINDINGS.md` — RF-014 **CLOSED**; residuals named not MET
- `reviews/REMEDIATION_MILESTONE.md` — R0.11 close-gate record
- `reviews/r0.11.7-rf014-close-gate-report.md` — scoring report
- `reviews/sdd-briefs/task-15-rf014-close-gate-report.md` — this handoff

## Public/interface changes
- None.

## Numerical conventions
- n/a (docs / security-boundary close gate)

## Tests added/updated
- None (docs-only). Existing RF-014 suites re-run.

## Commands executed
```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_compose_loopback.py \
  tests/test_finite_scalars.py \
  tests/test_workload_limits.py \
  tests/test_error_sanitization.py \
  tests/test_shared_auth.py \
  tests/test_container_hardening.py \
  tests/test_api_error_model.py
```

## Results
- Backend required suite: **87 passed**, 1 pre-existing Starlette `TestClient` deprecation warning, 6.85s
- Frontend: n/a
- QuantLib: n/a
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## MET vs PARTIAL vs UNMET (this gate)

**Local demo:** loopback API/frontend **MET** (`docker-compose.yml` `127.0.0.1:8000` / `5173`); Postgres loopback publish **MET** (`127.0.0.1:5432`, not `0.0.0.0`); finite numbers **MET** (`FiniteFloat`, `FactorShockWire.amount`); positions/scenarios/body caps **MET** (`workload.py` + `WorkloadBodyLimitMiddleware`); sanitization **MET** (`http_bad_request` / `Risk run failed`). Local unauthenticated **MET** by design.

**Shared / internal:** authentication **MET** (Bearer fail-closed). Object ACLs **UNMET**. TLS **UNMET**. Secret management **UNMET**. Non-root runtime **MET**. Request limits **PARTIAL** (payload yes; HTTP queue depth no).

**Production-like:** **UNMET** (not provided).

## Why CLOSE (not KEEP OPEN)
Loopback, finite numbers, caps, sanitization, and the token gate are MET on disk. KEEP OPEN would be required if those were unmet or if CLOSE could not be defended. Shared ACLs/TLS/secrets remain unimplemented; calling them MET would be a rubber-stamp. They are accepted R0 residuals because Milestone R0 is a local/demo profile, not a production IAM rollout. HTTP enqueue depth and Compose demo DB password are named leftovers, not MET.

## Known limitations / risks
- Object ACLs / IDOR with the shared token
- No TLS / reverse-proxy
- No secret manager; Compose `POSTGRES_PASSWORD=quantlineage`
- No HTTP queued-run depth cap
- `docker run -p 8000:8000` without shared flag still serves unauthenticated API (not default Compose)
- Deferred minors: `is_public_path` `..`; dual-book per-list cap; `model_copy` finite re-check

## Follow-up / next owner
- Owner: independent reviewer (Task 15 review)
- Requested action: APPROVE CLOSE or KEEP OPEN; do not treat CLOSED as final until that review
- Blocking?: no for other P1s; do not invent IAM from this handoff
