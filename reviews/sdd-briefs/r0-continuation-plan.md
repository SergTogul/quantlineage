# Milestone R0 Continuation Plan (SDD)

Branch: `r0-core-remediation`  
Authoritative: `reviews/FINDINGS.md`, `reviews/REMEDIATION_MILESTONE.md`  
Agent charters: `docs/agents/`  
Controller: Lead Architect (this session)

## Goal

Close remaining **P0** work for Milestone R0 exit, then address blocking P1 residuals that the milestone still lists as open. Do not expand C++ / IAM / TypeScript rewrite / exotics during R0.

## Already CLOSED (do not re-dispatch)

RF-001, RF-002, RF-003, RF-004, RF-005, RF-006, RF-008, RF-009, RF-015 (and prior R0 slices through `934379c`).

## Global Constraints

1. Pricing library prices; RiskForge manages portfolio risk; LLM never invents numbers.
2. Preserve numerical identity vs golden/pre-change suites unless an ADR documents a breaking convention.
3. Do not change numerical methodology solely for performance.
4. Do not expand native C++ VaR/QuantLib kernels in R0 (Python-side QuantLib reuse OK).
5. Every behavior change needs tests in the same change; focused suite green before handoff.
6. One owner per task; no dual-owning the same file set in parallel.
7. Update `reviews/FINDINGS.md` + `reviews/REMEDIATION_MILESTONE.md` on the owning commit; do not close a finding until independent review APPROVE (controller closes).
8. Implementer **commits** one slice per task after tests; reviewer is read-only.
9. Prefer `/usr/bin/git`; never force-push; never amend unless SDD/user rules allow.

## Task queue

### Task 1 — R0.6.3 Reuse QuantLib structures where safe
- **Owner:** Quant Pricing Engineer (`docs/agents/03_QUANT_PRICING_ENGINEER.md` or nearest charter)
- **Finding:** RF-007 (keep IN PROGRESS)
- **Goal:** Where scenario semantics allow, reuse/relink QuantLib quotes, handles, instrument terms/schedules, or curve structure across shocked scenarios instead of full rebuild per (trade, scenario). Do not cache stale market state. Prove identical P&L/VaR to existing goldens within tolerance.
- **Exit:** Documented reuse path + tests; RF-007 still open.

### Task 2 — R0.6.4 Remove anti-cache behavior
- **Owner:** Quant Pricing Engineer (with Portfolio Risk if HistoricalRiskEngine cache touched)
- **Finding:** RF-007
- **Goal:** If valuation LRU is slower for unique shocked markets, disable or bypass it for that execution class (or redesign caching level). Prove no numerical drift; preferably no wall-time regression on unique-shock path.
- **Exit:** Shocked full-reval path does not pay anti-cache tax; RF-007 still open unless Tasks 1–4 jointly meet exit.

### Task 3 — R0.6.6 Contribution reuse
- **Owner:** Portfolio Risk Engineer (`docs/agents/04_PORTFOLIO_RISK_ENGINEER.md`)
- **Finding:** RF-007
- **Goal:** Avoid whole-book full revaluation once per factor family when trade/scenario P&Ls can be reused or decomposed. Preserve contribution reconcile invariants.
- **Exit:** Contribution path reuses trade/scenario grain where possible; tests pin reconcile.

### Task 4 — R0.6.5 Process-level scenario parallelism (bounded)
- **Owner:** Backend/API Engineer (`docs/agents/07_BACKEND_API_ENGINEER.md`) coordinating with Portfolio Risk
- **Finding:** RF-007
- **Goal:** Partition independent scenario blocks across **processes** (not in-process threads) when profiling shows value — or document that Compose `worker` / RiskRun already is the process partition and add a measured opt-in for full-reval scenario chunks. Do not invent fake SLAs.
- **Exit:** Benchmark note + either opt-in partition or explicit “RiskRun worker is the partition” ADR/milestone text with evidence.

### Task 5 — RF-007 close gate — COMPLETE KEEP OPEN
- Disposition: **KEEP OPEN**. Architecture (R0.6.1–R0.6.6) APPROVE. Acceptance benches still UNMET/PARTIAL.

### Task 6 — Record RF-007 acceptance benches
- **Owner:** QA & Quant Validation (`docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`) with existing `benchmarks/run_full_reval_bench.py`
- **Finding:** RF-007 stays **IN PROGRESS** unless this slice actually records the matrix and Task 5-class close is re-justified (do not close in this slice unless the matrix is honestly filled).
- **Goal:** Record FINDINGS acceptance fields without fake SLAs: N×S (at least one size above 1×120), wall time, peak RSS, scenarios/sec, builtin vs QuantLib, warm vs cold, identity vs goldens. PR-safe: skip or bound large N/S; do not assert wall-time floors.

### Task 7+ (P1 after P0) — only after RF-007 CLOSED
- RF-011 / RF-013 / RF-014 / RF-016 residuals as separate briefs.

## Pre-flight conflict scan

- R0.6.3 reuse must not alter scenario semantics (stale curves) — tests must catch.
- R0.6.5 must use processes, not threads (QuantLib global state / RF-002 history).
- No conflict with closed RF-006 one-pass apply / scenario-once-price-many.
