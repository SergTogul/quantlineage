# Task 5 Brief — RF-007 close gate

**Plan:** `reviews/sdd-briefs/r0-continuation-plan.md`  
**Owner agent:** QA & Quant Validation Engineer — read `docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`, `AGENTS.md`, `docs/agents/WORKFLOW.md`, `docs/agents/DEFINITION_OF_DONE.md`  
Lead Architect will apply your recommendation after task review.  
**Finding:** RF-007 — currently **IN PROGRESS**. You may recommend **CLOSED** with P1 residuals **or** keep **IN PROGRESS** with a crisp residual list. Do not rubber-stamp.  
**BASE:** `1458a22` (Task 4 APPROVE)

## Context

Tasks 1–4 of this SDD wave are APPROVE:

| Slice | Commit | Review |
|---|---|---|
| R0.6.3 QuantLib reuse | `35bf9fa` | `reviews/sdd-briefs/task-1-r0.6.3-review.md` |
| R0.6.4 anti-cache | `68c302a` | `reviews/sdd-briefs/task-2-r0.6.4-review.md` |
| R0.6.6 contribution reuse | `8afd4e4` | `reviews/sdd-briefs/task-3-r0.6.6-review.md` |
| R0.6.5 process partition (choice B) | `1458a22` | `reviews/sdd-briefs/task-4-r0.6.5-review.md` |

Earlier: R0.6.1 identity bench, R0.6.2 stream, RF-015 HEAVY→RiskRun CLOSED.

## Your job (no production-code feature work)

1. Read FINDINGS RF-007 required direction (7 bullets) and acceptance evidence (benchmark matrix).
2. Score each required-direction bullet MET / PARTIAL / UNMET against the landed slices (docs + tests in repo; do not re-implement).
3. Score acceptance evidence: what is recorded vs still missing (N=100/1k, RSS, scenarios/sec, builtin vs QuantLib, warm vs cold).
4. **Recommendation:**
   - **CLOSE** only if required direction is honestly met and remaining bench gaps are the same class of P1 residual as RF-008 (limits/drilldown) — i.e. architecture is in place, N×S cost is *explainable and bounded as a RiskRun job*, goldens still match.
   - **KEEP OPEN** if N×S rebuild is still the unaddressed root cause or acceptance benches are required for close.
5. Update `reviews/FINDINGS.md` RF-007 status per your recommendation (if CLOSE, name P1 residuals; if KEEP OPEN, crisp remaining list). Update `reviews/REMEDIATION_MILESTONE.md` § R0.6 exit / R0.6.3–R0.6.6 pending-review → COMPLETE with review pointers.
6. Write `reviews/r0.6-rf007-close-gate-report.md`.
7. **Commit** one docs commit (`docs(r0.6): ...`). Do not change pricing/risk algorithms.

## Out of scope

- Implementing N=100/1k benches unless you conclude they are a one-file pin already almost present
- C++ / fake SLAs
- Closing other findings

## Report contract

Write full report to: `reviews/sdd-briefs/task-5-rf007-close-gate-report.md`  
Return only: status, commit SHA(s), recommendation CLOSE or KEEP OPEN, one-line rationale.
