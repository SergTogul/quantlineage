# Task 7 Brief — RF-007 remaining acceptance (reconstruction QuantLib + N=100)

**Owner:** QA & Quant Validation (`docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`) coordinating with Quant Pricing if a tiny option fixture is needed.  
**Finding:** RF-007 — keep **IN PROGRESS** until this slice is independently APPROVE **and** the close matrix is honestly MET/PARTIAL as below. Do not rubber-stamp CLOSE.  
**BASE:** current HEAD after leftover SDD commit.

## Why this exists

The last close gate KEEP OPEN’d because:
- QuantLib path was cash equity (`quantity * spot`), not reconstruction
- peak RSS is process-lifetime `ru_maxrss` (QuantLib includes prior builtin)
- N=100 / 1k UNMET in default PR

## Required

1. **Builtin vs QuantLib reconstruction:** same N×S full-reval on a book that actually uses QuantLib instruments (e.g. European equity options / bonds), not `quantity * spot`. Record wall_ms, scenarios/sec, identity checksum. Skip-or-run if QuantLib missing (existing hard-gate pattern).
2. **Isolated RSS:** measure peak RSS in a way that does not include the other impl’s prior run (subprocess or separate pytest process). Label honestly if still PARTIAL.
3. **N=100:** record at least N=100 × modest S (e.g. 50) **outside default PR** (`RISKFORGE_NIGHTLY` or `CI` labeled job — skip locally unless env set; fail in nightly if missing). N=1k optional same skip rule. No wall-time SLA floors.
4. Update FINDINGS residual scores honestly. Still do **not** CLOSE unless a follow-up close-gate (this task may leave IN PROGRESS if N=1k still unmet — N=100 nightly + reconstruction QL is the bar to re-attempt close).
5. Write `reviews/r0.6.8-reconstruction-benches-report.md`.
6. **Commit** (`test(r0.6): ...`).

## Out of scope
- Fake SLAs
- C++ kernels
- Intra-run multiprocessing (Option A)

## Tests
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py
```

## Report
`reviews/sdd-briefs/task-7-rf007-reconstruction-benches-report.md`  
Return: status, SHA, MET vs UNMET, concerns.
