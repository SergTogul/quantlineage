# Task 6 Brief — RF-007 acceptance benches

**Plan:** `reviews/sdd-briefs/r0-continuation-plan.md`  
**Owner agent:** QA & Quant Validation Engineer — read `docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`, `AGENTS.md`, `docs/agents/WORKFLOW.md`, `docs/agents/DEFINITION_OF_DONE.md`  
**Finding:** RF-007 — keep **IN PROGRESS** (do not CLOSED in this slice unless the full FINDINGS matrix is honestly recorded)  
**BASE:** `6e3dbdc`  
**Prior:** Task 5 KEEP OPEN. Missing: RSS, scenarios/sec, builtin-vs-QuantLib **UNMET**; N×S / wall / warm-cold **PARTIAL** at 1×120 builtin only (`benchmarks/run_full_reval_bench.py` hard-codes `N_POSITIONS=1`, `N_OBS=120`).

## Goal

Record FINDINGS RF-007 acceptance evidence **without inventing SLAs**:

- N trades × S scenarios (at least one configuration **above** 1×120; PR-safe default e.g. N=10 × S=50 or similar — not 1k in PR)
- wall time (record `wall_ms`; pytest may assert it is a finite number, **not** a performance floor)
- peak RSS
- scenarios/sec (record only; do not gate CI on it)
- builtin vs QuantLib at the **same** N×S (QuantLib path skip-or-run if QuantLib unavailable, matching existing hard-gate patterns)
- warm vs cold (two recorded wall_ms on the same fixture; no SLA)
- identical numerical results to pre-change goldens / existing `pnl_checksum`

## Requirements

1. Extend `benchmarks/run_full_reval_bench.py` and `backend/tests/test_full_reval_bench.py` (and/or a sibling nightly-safe test) so the payload includes the fields above.
2. Do **not** fail CI on slow machines via wall-time/RSS floors.
3. Keep R0.6.1 identity checksum unless you document a fixture change.
4. Update FINDINGS RF-007 residual line (still IN PROGRESS) and milestone (R0.6.1 extension / new § if needed).
5. Write `reviews/r0.6.7-acceptance-benches-report.md`.
6. **Commit** one focused commit (`test(r0.6): ...` or `feat(r0.6): ...`).

## Out of scope

- Closing RF-007 (unless matrix is complete including QuantLib; still prefer leave IN PROGRESS for Task 7 close re-gate)
- Fake SLAs
- N=1k in the default PR test
- C++ kernel expansion
- In-process QuantLib threads

## Suggested tests

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py
```
Plus any new bench tests. Skip rules must not hide missing fields when the bench runs.

## Report contract

Write full report to: `reviews/sdd-briefs/task-6-rf007-benches-report.md`  
Return only: status, commit SHA(s), one-line test summary, which matrix cells are now MET vs still UNMET, concerns.
