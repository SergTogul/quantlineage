# Workstream 9 Queue Residual Handoff

## Task
Resolve Redis/RQ-or-equivalent queue residual.

## Owner
Backend/API Engineer + DevOps/Platform Engineer

## Summary
Investigated the remaining Redis/RQ residual and found no MVP product/ops semantic gap requiring a new dependency. QuantLineage already has a real queue-equivalent for the current product scope: durable `risk_runs` rows in Postgres, API-side enqueue-only mode in Compose, out-of-process `python -m app.worker`, FIFO claims bounded by poll batch, and PostgreSQL `FOR UPDATE SKIP LOCKED` for multi-worker claim safety.

Redis/RQ remains an accepted deferral, not a hidden incomplete feature. It should be introduced only when QuantLineage needs semantics Postgres row claiming does not currently provide, such as priority classes, tenant fairness, retry policy/dead-lettering, or queue observability.

## Files changed
- `backend/tests/test_durable_worker.py`
- `BUILD_NOTES.md`
- `docs/adr/005-sqlalchemy-persistence.md`
- `docs/agents/HANDOFF_QUEUE_RESIDUAL_M9.md`

## Public/interface changes
- None. No API DTO, route, worker command, environment variable, dependency, or container service was added.
- Preserved `POST /risk/runs` queued acceptance semantics and `GET /risk/runs/{id}` current-state semantics.

## Numerical conventions
- Units: not applicable.
- Sign convention: not applicable.
- Day count/calendar: not applicable.
- Tolerances/reference: queue/lifecycle invariants only; no pricing/risk formulas changed.

## Tests added/updated
- `test_submit_execute_true_returns_stable_queued_acceptance_snapshot`: proves submit returns a stable `QUEUED` acceptance view with no results even when in-process execution is scheduled immediately.
- `test_poll_once_respects_batch_limit_and_leaves_excess_queued`: proves worker polling honors batch limits and leaves unclaimed FIFO backlog queued for later polls.

## Commands executed
```bash
python3.12 -m pytest -q tests/test_durable_worker.py tests/test_risk_run_api.py
python3 -m pytest -q tests/test_durable_worker.py tests/test_risk_run_api.py
python3.12 -m pip install -r requirements-dev.txt
python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest -q tests/test_durable_worker.py tests/test_risk_run_api.py
.venv/bin/ruff check app/services/risk_run_worker.py app/persistence/sqlalchemy_repos.py tests/test_durable_worker.py
.venv/bin/mypy app
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q
```

## Results
- Initial `python3.12 -m pytest ...`: failed because global Python had no `pytest`.
- Initial `python3 -m pytest ...`: failed because global Python had no `pytest`.
- Initial `python3.12 -m pip install -r requirements-dev.txt`: failed due externally managed Python environment.
- Local venv setup: succeeded.
- Focused durable worker/risk-run API tests: `20 passed, 1 warning` (existing Starlette/httpx deprecation warning).
- Ruff: `All checks passed!`
- mypy: `Success: no issues found in 82 source files`
- Full backend pytest: `659 passed, 1 warning` in 146.70s (existing Starlette/httpx deprecation warning).
- Compose/config validation: not run; no dependency, Dockerfile, or `docker-compose.yml` changes were made.
- CI is green: not run from this local task; prior GHA green evidence remains recorded in `ROADMAP.md`.

## Known limitations / risks
- Compose ships one worker by default for the demo; additional Postgres-backed replicas are claim-safe but not a complete fair scheduler.
- No priority, tenant fairness, retry/dead-letter queue, queue metrics dashboard, or Redis-backed queue observability was added.
- SQLite remains a single-writer/unit-test fallback without `SKIP LOCKED`; it is not the multi-worker production path.

## Follow-up / next owner
- Owner: DevOps/Platform Engineer if future operational queue requirements appear.
- Requested action: introduce Redis/RQ or another queue only with testable new semantics such as priority, tenant fairness, retries/dead-lettering, or queue observability.
- Blocking?: no.
