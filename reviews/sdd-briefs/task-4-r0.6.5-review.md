# Task 4 Review — R0.6.5 Process-level scenario parallelism

**Base:** `8afd4e4`  
**Head:** `1458a22`  
**Diff reviewed:** `.superpowers/sdd/review-8afd4e4..1458a22.diff`  
**Brief:** `reviews/sdd-briefs/task-4-r0.6.5-brief.md`  
**Implementer report (unverified claims):** `reviews/sdd-briefs/task-4-r0.6.5-report.md`

## Verdict

| Gate | Result |
|---|---|
| Spec compliance | ✅ |
| Task quality | **Approved** |
| Critical | 0 |
| Important | 0 |
| Minor | 5 |
| RF-007 | Stays **IN PROGRESS** (correct; do not close) |
| Choice | **B** (RiskRun / Compose worker is the process partition). **A is not implemented** — no opt-in chunked `ProcessPoolExecutor`, no P&L-identity multiprocess concat. |

Ready to proceed to the RF-007 close gate (Task 5). No blocking fixes required for this task gate.

---

## Spec compliance

Checked against the task brief and binding global constraints. Implementer report treated as unverified; evidence is the `8afd4e4..1458a22` diff.

| Requirement | Evidence in diff | Status |
|---|---|---|
| Processes, not threads, for QuantLib scenario partitions | No thread pool for pricing. Production change is a docstring on `risk_run_worker.py` stating HEAVY full-reval stays on the Compose `worker` OS process. In-process `ThreadPoolExecutor` remains job scheduling only. | Met |
| Pick A (opt-in chunked multiprocess with exact P&L identity) **or** B (document RiskRun as the partition + HEAVY proof tests; do not add unused multiprocessing) | **B.** No `ProcessPoolExecutor` / multiprocessing added. ADR 007 + milestone + `reviews/r0.6.5-process-parallelism-report.md` document Compose `worker` / `QUANTLINEAGE_EXTERNAL_WORKER` as the partition. | Met |
| Prefer B unless A can land with identity tests without C++ / methodology change | B chosen; ADR records why A is not cheap (pickle/reconstruct QuantLib per chunk; R0.6.1 is identity-not-SLA). | Met |
| Proof: FULL_REVALUATION summary/var is HEAVY | `test_full_revaluation_summary_and_var_are_heavy` calls `classify(..., methodology=FULL_REVALUATION)` on both mounts. | Met |
| Proof: refused inline when the gate is on (`details.use=/risk/runs`) | Parametrized TestClient posts to summary/var (v1 + legacy) under `QUANTLINEAGE_EXTERNAL_WORKER=1` and `QUANTLINEAGE_HEAVY_INLINE=0`; asserts 400 / `use=/risk/runs`. | Met |
| Record R0.6.1 checksum/identity as scaling evidence, not an SLA | Report + ADR + FINDINGS pin `6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f`; test asserts checksum constant, `wall_ms` not SLA-gated, `check_m6_sla.py` not imported. | Met |
| FINDINGS RF-007 stays IN PROGRESS; milestone § R0.6.5 COMPLETE pending review | Status line still **IN PROGRESS** / “Do not close”; § R0.6.5 titled COMPLETE pending review. | Met |
| Write `reviews/r0.6.5-process-parallelism-report.md` (short ADR only if A) | Report added. Existing ADR 007 updated rather than a new ADR — matches plan exit (“RiskRun worker is the partition” ADR/milestone text), not a new option-A ADR. | Met (justified extra) |
| One focused commit (`feat(r0.6): ...`); no C++ / no RF-007 close / no fake SLA | Single commit `1458a22 feat(r0.6): pin HEAVY full-reval to RiskRun worker processes`; native kernels untouched; no SLA numbers. | Met |
| Every behavior change has tests in the same change | New `backend/tests/test_r065_process_partition.py` in the owning commit. Production behavior is documentation/pin, not a numerical or API change. | Met |
| Preserve interfaces; LLM does not invent numbers; no native kernel expansion | No env flag, DTO, or multiprocessing API. | Met |

Brief-authorized deviation from the plan’s goal line (“add a measured opt-in for full-reval scenario chunks”): the brief prefers B and forbids unused multiprocessing when A is not justified. That is what landed.

This review did not re-run the suite.

---

## Strengths

- Right call for this slice: option B documents an existing, already-shipped partition (RF-015 CLOSED) instead of adding a pickle-heavy scenario `ProcessPoolExecutor` that would not be cheap or justified by R0.6.1.
- The required HTTP proof is real behavior, not grepping: TestClient posts FULL_REVALUATION summary/var on both mounts, both gates, and asserts `details.use=/risk/runs`.
- The partition’s two sides are both pinned: API process stays `QUEUED` under `QUANTLINEAGE_EXTERNAL_WORKER=1`; `execute_run_type` still accepts `methodology=FULL_REVALUATION` (would fail if dispatch dropped it to `DELTA_GAMMA`).
- RF-007 hygiene is correct: FINDINGS stays IN PROGRESS with “Do not close”; milestone is COMPLETE *pending review*; N×S joint pricing and N=100/1k remain explicit residuals.
- No SLA invention; checksum is recorded as identity, `wall_ms` as telemetry.
- Ownership stayed on Backend/API (`risk_run_worker` docstring + tests + ADR/findings). Portfolio Risk loops and native kernels were not dual-owned.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

None.

### Minor (Nice to Have)

1. **Several “proof” tests re-pin contracts already owned by R0.3.5 / RF-015 suites**  
   - File: `backend/tests/test_r065_process_partition.py`  
   - Overlap: `test_endpoint_execution_class.py::test_full_revaluation_is_never_interactive_only`; `test_backpressure.py` already refuses FULL_REVALUATION summary and leftover HEAVY `/risk/var`; `test_full_reval_bench.py::test_full_reval_bench_script_is_identity_not_sla`; `test_quantlib_process_parallelism.py` already pins Compose worker vs API and `full_revaluation_pnl_series` has no executor.  
   - Unique coverage that does belong here: FULL_REVALUATION summary under `QUANTLINEAGE_HEAVY_INLINE=0` (summary is INTERACTIVE unless methodology upgrades it); RiskRun `QUEUED` with FULL_REVALUATION; `execute_run_type` FULL_REVALUATION dispatch.  
   - Why it matters: a dedicated R0.6.5 file is fine as a named pin, but the AST/compose/checksum copies will drift in two places.  
   - Fix (optional): keep the HTTP + QUEUED + dispatch tests; drop or import the R0.3.5 compose/AST helpers instead of cloning them.

2. **Docstring lock requires `ProcessPoolExecutor` to remain in `risk_run_worker.py`**  
   - File: `backend/tests/test_r065_process_partition.py` (`test_worker_does_not_defer_unused_process_pool_to_r065`)  
   - Asserts `"ProcessPoolExecutor" in source` and `"does not start a" in source`. Removing the mention entirely (also correct: the module still would not start a pool) fails the test.  
   - Why it matters: this pins wording, not behavior.  
   - Fix (optional): assert absence of `R0.6.5 may add` plus the existing AST “worker may name `ThreadPoolExecutor` only” check.

3. **`execute_run_type` proof is shallow**  
   - File: `backend/tests/test_r065_process_partition.py` (`test_full_revaluation_execute_run_type_still_computes`)  
   - Only asserts `isinstance(payload, dict)` and `methodology == "FULL_REVALUATION"`. `PortfolioService.summary` stamps `methodology.value` onto the result, so a path that ignored FULL_REVALUATION internally but still labeled the payload could pass. It also runs in-process, so it does not prove OS-process isolation (the QUEUED test is the isolation pin).  
   - Why it matters: the worker-side half of option B is “dispatch still computes,” not “numbers exist.”  
   - Fix (optional): assert a numeric field (`var` / `pnl` length) on the payload.

4. **R0.6.1 identity test greps the bench script; it does not run it**  
   - File: `backend/tests/test_r065_process_partition.py` (`test_r061_checksum_is_identity_scaling_evidence_not_sla`)  
   - Near-duplicate of `test_full_reval_bench_script_is_identity_not_sla`. The live checksum run already lives in `test_full_reval_bench_emits_identity_json` (included in the brief focused suite).  
   - Why it matters: “scaling evidence” is documentation of an existing identity bench, which is what B asked for; this test does not add a new measurement.  
   - Fix (optional): cite `test_full_reval_bench.py` from the R0.6.5 report and drop the grep clone.

5. **Stale R0.6.4 milestone sentence**  
   - File: `reviews/REMEDIATION_MILESTONE.md` (R0.6.4 section)  
   - Still says “RF-007 remains open for R0.6.5–R0.6.6 / close gate” after this commit marked both slices COMPLETE pending review. R0.6.6’s trailer was updated; R0.6.4’s was not.  
   - Why it matters: the close-gate reader can think R0.6.5 is still unstarted.  
   - Fix (optional): point R0.6.4 at the close gate / N=100/1k, matching R0.6.5–R0.6.6.

---

## Recommendations

- Treat replica scale-out (`SKIP LOCKED` extra Compose workers) as **job** parallelism, not scenario-index partitioning inside one FULL_REVALUATION. The report already says this; Task 5 should not close RF-007 on replica-count alone if N=100/1k wall-clock evidence is still required.
- Do not add option A later without exact P&L identity vs serial on a small deterministic fixture, and without a new ADR (brief already required that for A).

---

## Assessment

**Ready to proceed?** Yes.

**Reasoning:** Option B is what the brief preferred and what the diff actually contains: documentation plus HEAVY/RiskRun proof tests, no unused multiprocessing, no methodology or C++ change, RF-007 left open. Remaining issues are duplication and brittle docstring locks, not missing requirements.
