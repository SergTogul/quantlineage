# Task 8 Brief — RF-007 close gate (after reconstruction benches)

**Owner:** QA & Quant Validation (`docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`) acting as independent close gate.  
**Finding:** RF-007  
**BASE:** `78c1d0e`  
**Prior:** Task 5 KEEP OPEN. Task 7 APPROVE (`reviews/sdd-briefs/task-7-rf007-reconstruction-benches-review.md`).

## Why this exists

Task 5 KEEP OPEN’d because cash-equity QuantLib, process-lifetime RSS, and N=100/1k were unmet. Task 7 recorded reconstruction-honest European-option benches, isolated RSS subprocesses, and nightly N=100×50. This slice **re-evaluates CLOSE vs KEEP OPEN**. Do not re-stamp the rejected CLOSE. Do not rubber-stamp CLOSED if residuals still fail the FINDINGS required direction / acceptance evidence.

## Required

1. Read `reviews/FINDINGS.md` RF-007 (required direction + acceptance evidence), `reviews/r0.6-rf007-close-gate-report.md`, `reviews/r0.6.8-reconstruction-benches-report.md`, Task 7 report+review.
2. Score each required-direction item and each acceptance-matrix cell **MET / PARTIAL / UNMET** with file:evidence. Do not invent SLAs.
3. Disposition: **CLOSE** only if P0 required direction is honestly met (PARTIAL process-chunk option A may be documented as a **P1 residual**, same as Task 4). **KEEP OPEN** if reconstruction, N×S recording, or identity is still unmet, or if you would not defend CLOSE to a second reviewer.
4. N=1k remaining UNMET is not automatically a KEEP OPEN if N=100 nightly is recorded and FINDINGS never set a fake 1k SLA. Peak RSS remaining PARTIAL (`ru_maxrss` in an isolated child) must be scored honestly — CLOSE is allowed only if you treat that as documented measurement limit, not as “MET”.
5. Update FINDINGS + `reviews/REMEDIATION_MILESTONE.md` to match the disposition. If CLOSE, status **CLOSED** with independent-review placeholder (controller will not close until this task’s review APPROVE).
6. Write `reviews/r0.6.9-rf007-close-gate-report.md`.
7. **Commit** (`docs(r0.6): ...`). Do not change production/pricing code.

## Out of scope
- New benches (that was Task 7)
- C++ kernels, Option A multiprocessing, fake SLAs
- Closing other findings

## Tests
None required unless you change code. If you only change docs, say so.

## Report
`reviews/sdd-briefs/task-8-rf007-close-gate-report.md`  
Return: status, SHA, CLOSE vs KEEP OPEN, matrix scores, concerns.
