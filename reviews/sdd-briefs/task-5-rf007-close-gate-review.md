# Task 5 Re-review — RF-007 close gate

**Base:** `1458a22`  
**Head:** `6e3dbdc` (fix after overreach; prior CLOSE was `970d669`)  
**Diff reviewed:** `.superpowers/sdd/review-1458a22..6e3dbdc.diff`  
**Brief:** `reviews/sdd-briefs/task-5-rf007-close-gate-brief.md`  
**Prior review (CHANGES REQUESTED):** this file, against `970d669`  
**Implementer report (unverified claims):** `reviews/sdd-briefs/task-5-rf007-close-gate-report.md`  
**Scoring report (unverified claims):** `reviews/r0.6-rf007-close-gate-report.md`  
**Lead adjudication:** KEEP OPEN; RF-007 must be **IN PROGRESS**

## Verdict

| Gate | Result |
|---|---|
| Spec compliance | ✅ |
| Task quality | **Approved** |
| Critical | 0 |
| Important | 0 |
| Minor | 0 |
| Recommendation | **KEEP OPEN** |
| Lead may keep RF-007 CLOSED | **no** |

Prior Critical (CLOSE overreach) and both Important items (RF-008 analogy; “no fake SLA” as a recording waiver) are fixed at `6e3dbdc`. Prior Minors are addressed. CLOSE is still not justified: acceptance benches remain UNMET/PARTIAL beyond 1×120 builtin identity.

This re-review did not re-run the focused 69-test suite (docs-only fix; original close-gate commit recorded 69 passed).

---

## Must-verify (Lead list)

Checked on **HEAD `6e3dbdc`**, not the intermediate CLOSE commit.

| # | Check | Result |
|---|---|---|
| 1 | FINDINGS RF-007 is **IN PROGRESS**, not CLOSED | **Pass.** Status line is **IN PROGRESS**; close-gate paragraph ends **KEEP OPEN.** / “Do not close.” No `Status: **CLOSED**` on RF-007. |
| 2 | Residual lists UNMET benches (RSS, scenarios/sec, builtin-vs-QuantLib) and PARTIAL 1×120 builtin | **Pass.** FINDINGS status + close-gate paragraph; milestone close-gate section; scoring-report table and Residuals. |
| 3 | Milestone close-gate is not COMPLETE / does not close RF-007 | **Pass.** Heading is `R0.6 close gate — KEEP OPEN / not complete`. Body: **RF-007 IN PROGRESS.** Exit: **Benchmarked no**; close-gate **not complete**. |
| 4 | R0.6.3–R0.6.6 slices may remain COMPLETE | **Pass.** All four headings are COMPLETE with APPROVE review pointers. |
| 5 | Close-gate report recommendation is KEEP OPEN | **Pass.** Header and Recommendation section are **KEEP OPEN**. Return line: `DONE \| KEEP OPEN`. |

RF-006 pointer restored: “Wall-clock N×S pricing remains RF-007” (FINDINGS) / “N×S full-reval cost remains RF-007” (milestone R0.4.6). Related-findings bullet is `RF-007 (**IN PROGRESS**; close-gate KEEP OPEN)`. R0.6.1 says identity is **1×120** builtin and “RF-007 stays open,” not “P1 after CLOSE.”

---

## Spec compliance

Checked against the task brief, FINDINGS RF-007 as written, R0.6 exit criteria, the continuation plan, and Lead’s KEEP OPEN adjudication. Implementer reports treated as unverified; evidence is the `1458a22..6e3dbdc` range (final tree at `6e3dbdc`) plus on-disk tests/docs for the seven required-direction bullets.

| Requirement | Evidence at HEAD | Status |
|---|---|---|
| Score required-direction (7 bullets) MET / PARTIAL / UNMET | Honest table in `reviews/r0.6-rf007-close-gate-report.md` (6 MET, 1 PARTIAL). Independent re-score still agrees. | Met |
| Score acceptance benches: recorded vs missing (N=100/1k, RSS, scenarios/sec, builtin vs QuantLib, warm vs cold) | Honest table: 1 MET (goldens), 3 PARTIAL, 3 UNMET. 1×120 builtin (not N=10×S=100). | Met |
| CLOSE only if remaining gaps are RF-008-class P1; else KEEP OPEN | Recommendation is **KEEP OPEN**. Acceptance matrix treated as P0 close residual, not optional P1. | Met |
| FINDINGS RF-007 status must match the recommendation | **IN PROGRESS** matches KEEP OPEN. Residual list is crisp, not “P1 (not blocking close).” | Met |
| Milestone § R0.6.3–R0.6.6 pending-review → COMPLETE with review pointers | COMPLETE + four APPROVE reviews. Close-gate section is KEEP OPEN / not complete. | Met |
| Write `reviews/r0.6-rf007-close-gate-report.md` | Present; KEEP OPEN; RF-008 analogy and SLA-as-waiver language removed. | Met |
| Docs-only; no algorithm changes; no fake SLAs | Range is eight `reviews/` files. No production/pricing/risk edits. No SLA numbers invented. Two docs commits (`970d669` then `6e3dbdc`); expected after review. | Met |
| Do not rubber-stamp CLOSE | Scoring stays honest. KEEP OPEN is the written bar, not a reclassified matrix. | Met |

---

## Prior findings — disposition at `6e3dbdc`

| Prior | Item | Disposition |
|---|---|---|
| Critical | CLOSE overreaches; FINDINGS must stay IN PROGRESS | **Fixed.** Status **IN PROGRESS**; residuals named; close-gate not COMPLETE; RF-006 pointer restored. |
| Important | RF-008 is not a valid precedent | **Fixed.** “Why CLOSE” / RF-008 paragraph removed. “Why KEEP OPEN” cites FINDINGS acceptance + plan “benchmarks recorded.” |
| Important | “No fake SLA” used as a waiver of recording | **Fixed.** Text now: SLA rule constrains **how** benches are recorded; it does not waive recording. UNMET rows are the KEEP OPEN residual. |
| Minor | R0.6.1 still prints the N/S capture list | **Addressed as intended.** Capture block kept as residual list; “P1 after CLOSE” restored to “RF-007 stays open.” |
| Minor | Report tone (“Do not KEEP OPEN”) | **Fixed.** Recommendation states KEEP OPEN without prohibiting the other fork. |

---

## Independent scores (required direction)

Repo evidence, not the implementer table. Unchanged vs prior review (docs-only fix; no production delta in this range).

| # | Required direction | Score | Evidence |
|---|---|---|---|
| 1 | stream/chunk scenarios | **MET** | `iter_shocked_snapshots` / `iter_historical_shocked_snapshots` are generators (`backend/app/risk/scenarios.py`). Production full-reval loops in `historical.py` / `var.py` consume the iterator. |
| 2 | build scenario market state once | **MET** | RF-006 CLOSED. Stress `apply_scenario` count == S. Full-reval yields one shocked snapshot per observation. |
| 3 | reuse instrument structures or relinkable handles where safe | **MET** | R0.6.3 APPROVE. Scalar equity/FX options reuse via live `SimpleQuote`; terms/schedules cached. Surfaces, snapshot curves/key-rate handles, non-scalar instruments still rebuild — documented “where safe” remainder. |
| 4 | parallelize QuantLib scenario partitions by process, not threads | **PARTIAL** | R0.6.5 APPROVE choice **B**. HEAVY full-reval is a Compose `worker` OS process; in-process QuantLib stays `_QL_PROCESS_LOCK`. Option A intra-run scenario-block multiprocessing **not** implemented. Extra replicas are job parallelism (`SKIP LOCKED`), not scenario-index partitions inside one FULL_REVALUATION. |
| 5 | move large full-revaluation jobs to `RiskRun` | **MET** | RF-015 CLOSED; R0.6.5 pins HEAVY + refuse-inline `details.use=/risk/runs` + QUEUED API process. |
| 6 | keep interactive LINEAR / DELTA_GAMMA as the fast default | **MET** | `test_default_methodology_is_delta_gamma`; `test_service_and_api_default_methodology`. FULL_REVALUATION is HEAVY. |
| 7 | remove/disable caches that make unique-shock workloads slower | **MET** | R0.6.4 APPROVE. Unique-shock FULL_REVALUATION enters `bypass_valuation_lru`. |

**Required-direction summary:** 6 MET, 1 PARTIAL. Architecture for the reconstruction extras is honestly in place. Necessary for a later CLOSE; not sufficient until the acceptance matrix is recorded.

## Independent scores (acceptance evidence)

Agrees with the implementer table at HEAD. The matrix is still the FINDINGS close bar.

| Item | Score | Recorded | Still missing |
|---|---|---|---|
| N trades × S scenarios | **PARTIAL** | R0.6.1: **1 trade × 120 obs**, builtin `full_revaluation_pnl_series`. `benchmarks/run_full_reval_bench.py` hard-codes `N_POSITIONS = 1`, `N_OBS = 120`. | N=10 / 100 / 1k and S=50 / 750 / 1k |
| wall time | **PARTIAL** | `wall_ms` on the 1×120 builtin payload; pytest asserts a number, not a floor | Host-controlled matrix; QuantLib wall times |
| peak RSS | **UNMET** | none | peak RSS at any N×S |
| scenarios/sec | **UNMET** | `throughput` omitted on purpose (identity-not-SLA) | scenarios/sec recorded (must not become an SLA) |
| built-in vs QuantLib | **UNMET** | `impl=full_reval_builtin` only | QuantLib counterpart at the same N×S |
| warm vs cold | **PARTIAL** | R0.6.3 cold-engine **numerical** identity (abs `1e-12`), not a wall-clock pair | warm vs cold wall/RSS |
| identical numerical results to pre-change goldens | **MET** | Claimed 69 passed on `970d669`; checksum `6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f`; unit-equity `[-100, 0, 50]`; contribution reconcile pinned. This review did not re-run. | n/a |

R0.6 exit: explainable **yes**; **benchmarked no** beyond 1×120 builtin identity; bounded **yes** (HEAVY RiskRun); appropriate **yes** (DELTA_GAMMA default). Continuation plan Task 5 closes only if “benchmarks recorded, numerical identity, explainable scaling” — first conjunct still fails. That is why KEEP OPEN is correct and CLOSE is not.

---

## Why CLOSE remains unjustified

RF-008 closed with P1 residuals **after core acceptance was met**. RF-007 acceptance evidence **is** the bench matrix. Architecture + goldens without RSS / scenarios/sec / QuantLib / N=100/1k is not the same class of residual.

Builtin 1×120 cannot stand in for QuantLib N=100/1k. N×S `PricingEngine.value` is now explainable and bounded out of the request thread; that does not evidence that QuantLib reconstruction is gone at the sizes the finding named.

Lead may **not** keep RF-007 CLOSED.

---

## Strengths

- Fix commit `6e3dbdc` is a narrow docs revert of the overreach: status, pointers, close-gate heading, recommendation, and residual class. R0.6.3–R0.6.6 COMPLETE bookkeeping is left intact.
- Scoring tables remain honest (no invented N=10×S=100, RSS, scenarios/sec, or QuantLib wall times).
- Required-direction PARTIAL on bullet 4 is still the right label.
- Docs-only across the full range: no pricing/risk algorithm edits, no C++, no invented SLA-K1/K2.
- Goldens/identity treated as identity; `throughput` stays omitted.
- Contribution bound stated as Task 3 asked: O(N×S) joint + O(N) Greeks; FULL_REVAL factor buckets are Δ-Γ-plus-residual.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

None.

### Minor (Nice to Have)

None.

---

## Recommendations

- Lead: apply KEEP OPEN. Leave RF-007 **IN PROGRESS**. Do not apply CLOSED.
- Leave R0.6.3–R0.6.6 COMPLETE with the cited APPROVE reviews.
- Next P0 work for this finding is the bench matrix as already specified (not option A, not C++, not an SLA job in `nightly.yml`).
- Option A stays a documented PARTIAL / later P1 unless profiling after N=100/1k shows intra-run process chunks are worth an identity-preserving ADR.

---

## Assessment

**Spec compliance:** ✅

**Task quality:** Approved

**Issue counts:** Critical 0 / Important 0 / Minor 0

**Lead may keep RF-007 CLOSED:** no

**Reasoning:** At HEAD the close gate matches the brief’s KEEP OPEN clause and Lead’s adjudication: architecture slices stay COMPLETE, RF-007 stays IN PROGRESS, and the written P0 bench matrix (RSS, scenarios/sec, builtin vs QuantLib UNMET; N×S/wall/warm-cold PARTIAL at 1×120 builtin) is the residual. CLOSE would still overreach.
