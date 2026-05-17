# Task 1 Brief — R0.6.3 Reuse QuantLib structures where safe

**Plan:** `reviews/sdd-briefs/r0-continuation-plan.md`  
**Owner agent:** Quant Pricing Engineer — read `docs/agents/02_QUANT_PRICING_ENGINEER.md`, `AGENTS.md`, `docs/agents/WORKFLOW.md`, `docs/agents/DEFINITION_OF_DONE.md`  
**Finding:** RF-007 — keep **IN PROGRESS** (do not CLOSED)  
**Milestone:** `reviews/REMEDIATION_MILESTONE.md` § R0.6.3  
**Workspace:** `/Users/user/src/riskforge-mvp` branch `r0-core-remediation`  
**BASE (record before start):** use current `HEAD` at dispatch time

## Goal

Evaluate and implement **safe** reuse of QuantLib structures across shocked full-revaluation scenarios:

- relinkable quotes;
- relinkable handles;
- cached instrument terms/schedules;
- cached curve structure where scenario semantics allow.

**Do not cache stale market state.**

## Requirements (verbatim intent)

1. Full-reval / shocked pricing path must not rebuild everything from scratch per (trade × scenario) when safer reuse is available.
2. Numerical results must match the pre-change / golden suite within existing tolerances (identical preferred for deterministic fixtures).
3. Document what is reused vs rebuilt and why.
4. Tests: identity/parity for full-reval P&L or VaR on a small book; optional call-count or structure-build spy if practical without brittle QuantLib internals.
5. Update FINDINGS RF-007 status line (still IN PROGRESS) and milestone § R0.6.3 COMPLETE pending review.
6. Write `reviews/r0.6.3-quantlib-reuse-report.md`.
7. **Commit** one focused commit on `r0-core-remediation` after tests pass.

## Out of scope

- New C++ kernels / expanding native VaR
- R0.6.4 cache disable (Task 2)
- Process parallelism (Task 4)
- Closing RF-007
- Frontend

## Suggested tests

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_full_reval_bench.py \
  tests/test_historical_scenario_kernel.py \
  tests/test_quantlib_*.py \
  tests/test_pricing*.py
```
Plus any new reuse/parity tests you add. Run the focused suite you touch; before commit run that suite green.

## Report contract

Write full report to: `reviews/sdd-briefs/task-1-r0.6.3-report.md`  
Return to controller only: status (DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED), commit SHA(s), one-line test summary, concerns.
