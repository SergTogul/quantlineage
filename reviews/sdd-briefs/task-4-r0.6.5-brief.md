# Task 4 Brief — R0.6.5 Process-level scenario parallelism

**Plan:** `reviews/sdd-briefs/r0-continuation-plan.md`  
**Owner agent:** Backend/API Engineer — read `docs/agents/07_BACKEND_API_ENGINEER.md`, `AGENTS.md`, `docs/agents/WORKFLOW.md`, `docs/agents/DEFINITION_OF_DONE.md`  
Coordinate with Portfolio Risk only if full-reval loops must expose a chunked API. **Do not** use in-process threads for QuantLib (RF-002 history: process-owned Settings).  
**Finding:** RF-007 — keep **IN PROGRESS** (do not CLOSED)  
**Milestone:** `reviews/REMEDIATION_MILESTONE.md` § R0.6.5  
**Workspace:** `/Users/user/src/riskforge-mvp` branch `r0-core-remediation`  
**BASE:** `8afd4e4` (Task 3 APPROVE)

## Goal

Partition independent scenario blocks across **worker processes** when profiling shows value — **or** document with evidence that Compose `worker` / `RiskRun` already **is** the process partition for HEAVY full-reval, and add a measured **opt-in** for chunking scenario blocks if that is cheap and numerically identical.

Do **not** invent fake universal SLAs.

## Requirements

1. **Processes, not threads:** QuantLib `Settings` is process-owned. Any parallel scenario partition must be process-level (existing RiskRun worker, multiprocessing, or documented Compose worker). In-process thread pools for QuantLib pricing are disallowed.
2. Pick one of:
   - **A.** Opt-in chunked full-reval (e.g. env/`calculation_config` flag) that splits scenario indices across processes and concatenates P&L vectors with **exact** identity vs serial on a small deterministic fixture.
   - **B.** If A is not justified by existing benches / complexity: document that HEAVY full-reval already runs out-of-request-thread via RiskRun (`RF-015` CLOSED; `RISKFORGE_EXTERNAL_WORKER` / `run_type` paths) and add a **proof test** that FULL_REVALUATION summary/var is HEAVY and refused inline when the gate is on (`details.use=/risk/runs`). Record R0.6.1 bench checksum/identity as the scaling evidence. Do not add unused multiprocessing.
3. Prefer B unless you can land A with identity tests without expanding C++ or changing methodology.
4. Update FINDINGS RF-007 status line (still IN PROGRESS) and milestone § R0.6.5 COMPLETE pending review.
5. Write `reviews/r0.6.5-process-parallelism-report.md` (and a short ADR only if you choose A).
6. **Commit** one focused commit (`feat(r0.6): ...`).

## Out of scope

- Closing RF-007 (Task 5)
- Fake SLA numbers
- Threaded QuantLib
- Native kernel expansion

## Suggested tests

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_full_reval_bench.py \
  tests/test_backpressure.py \
  tests/test_endpoint_execution_class.py \
  tests/test_risk_run_api.py
```
Plus any new partition/identity tests.

## Report contract

Write full report to: `reviews/sdd-briefs/task-4-r0.6.5-report.md`  
Return only: status (DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED), commit SHA(s), one-line test summary, concerns. State whether you chose A or B.
