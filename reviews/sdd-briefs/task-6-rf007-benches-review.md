# Task 6 Re-review — RF-007 acceptance benches

**Base:** `6e3dbdc`  
**Head:** `0a0739f` (`0a0739fb3414daf84659f0148b857d7da4daed5d`)  
**Diff reviewed:** `.superpowers/sdd/review-6e3dbdc..0a0739f.diff`  
**Brief:** `reviews/sdd-briefs/task-6-rf007-benches-brief.md`  
**Prior review:** `reviews/sdd-briefs/task-6-rf007-benches-review.md` (was `c12de23`; Important scoring)  
**Implementer report (unverified claims):** `reviews/sdd-briefs/task-6-rf007-benches-report.md`  
**Scoring report (unverified claims):** `reviews/r0.6.7-acceptance-benches-report.md`

This is a task-scoped re-review after a docs-only Important fix (`0a0739f` on `c12de23`). Implementer reports treated as unverified. Evidence is the `6e3dbdc..0a0739f` tree. Focused HEAD check (named risk: dirty working tree): `git show 0a0739f:reviews/FINDINGS.md` and `git show 0a0739f:reviews/REMEDIATION_MILESTONE.md`. Did not re-run pytest: second commit is docs-only; `c12de23` code is unchanged.

## Verdict

| Gate | Result |
|---|---|
| Spec compliance | ✅ |
| Task quality | **Approved** |
| Critical | 0 |
| Important | 0 |
| Minor | 3 (carried; not blocking) |
| RF-007 still IN PROGRESS | **yes** |
| Lead may close RF-007 | **no** |

The prior Important is fixed at HEAD: peak RSS and builtin vs QuantLib are scored **PARTIAL**, not MET. RF-007 remains **IN PROGRESS**. Close-gate **KEEP OPEN**.

---

## Spec compliance

Checked against the task brief, global constraints, FINDINGS RF-007 acceptance list, and R0.6.1 identity rules. Two commits: `test(r0.6): record RF-007 acceptance benches at 10×50` (`c12de23`); `docs(r0.6): score RF-007 benches as partial where honest` (`0a0739f`). Docs-only delta is FINDINGS, milestone, R0.6.7 report, and the task-6 report — no harness/test change.

| Requirement | Evidence at HEAD | Status |
|---|---|---|
| Record N×S above 1×120; PR-safe (not 1k default) | Default `ACCEPTANCE_N_POSITIONS=10`, `ACCEPTANCE_N_OBS=50` (500 > 120). Pytest pins those sizes. CLI `--acceptance-n` / `--acceptance-s`; checksum pin dropped off 10×50. | Met |
| Record `wall_ms`; pytest finite, not a floor | Acceptance rows emit `wall_ms` / `wall_ms_cold` / `wall_ms_warm`. `_assert_recorded_finite` + identity `math.isfinite`. No `wall_ms >=` / `check_m6_sla`. | Met |
| Record peak RSS | `peak_rss_kib` from `resource.getrusage(RUSAGE_SELF).ru_maxrss` (Darwin bytes→KiB). Pytest finite, not a floor. FINDINGS/milestone score this **PARTIAL** (process-lifetime `ru_maxrss`). | Met (recording + honest close score) |
| Record scenarios/sec; do not gate CI | `scenarios_per_sec` from cold `wall_ms`. No `throughput` key. Source grep rejects `scenarios_per_sec` comparison floors. | Met |
| Builtin vs QuantLib at same N×S; skip-or-run | `acceptance.builtin` and `acceptance.quantlib` share N×S. Missing QL → `available: false` + `skip_reason`; `RISKFORGE_REQUIRE_QUANTLIB=1` fail-closed. Dedicated test uses `import_quantlib()`. FINDINGS/milestone score this **PARTIAL** (cash equity `quantity * spot`). | Met (recording + honest close score) |
| Warm vs cold: two `wall_ms`, same fixture, no SLA | `_engine_row` runs `_time_pnl_series` twice; emits both walls; warm P&L must allclose cold at `1e-12`. | Met |
| Identical numerical results / keep R0.6.1 checksum | Top-level pin still `6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f`. New 10×50 engine pin `a28cf4ee…`. Goldens file unchanged. | Met |
| No fake SLAs / no wall-time/RSS floors in CI | Pytest asserts presence + finiteness only. No new nightly/PR-FULL job; `check_m6_sla.py` not invoked. | Met |
| RF-007 stays IN PROGRESS (prefer not CLOSED) | FINDINGS status **IN PROGRESS**; close-gate **KEEP OPEN** / **not complete**; “Do not close.” R0.6.7 is COMPLETE pending review, not a close. | Met |
| Do not expand C++ kernels | Range is bench script, bench tests, `benchmarks/README.md`, FINDINGS, milestone, reports. No `backend/native/`. `0a0739f` docs-only. | Met |
| Extend harness + tests; write `reviews/r0.6.7-acceptance-benches-report.md`; focused commit | All present. Two focused commits (implement + docs scoring). | Met |
| Skip rules must not hide missing fields when the bench runs | Builtin recorded fields always asserted. QL fields required when `available`; else `skip_reason`. Identity checksum still asserted even if QL skipped. | Met |

---

## Independent scores (FINDINGS RF-007 acceptance matrix)

Agree with HEAD scoring. Peak RSS and builtin vs QuantLib are **PARTIAL**, not MET.

| Item | Score | Recorded | Still missing for CLOSE |
|---|---|---|---|
| N trades × S scenarios | **PARTIAL** | 1×120 identity kept; PR-safe **10×50** (above 1×120) on `full_revaluation_pnl_series`. | Milestone still lists N=100 / 1k and S=750 / 1k. Those sizes are CLI-only, not default-PR evidence. |
| wall time | **MET** at 10×50 | Finite `wall_ms` / `wall_ms_cold` / `wall_ms_warm` on builtin and QuantLib rows; no floor. | Host-controlled 100/1k walls still unrecorded as default evidence. |
| peak RSS | **PARTIAL** | `peak_rss_kib` is present and finite. FINDINGS residual + close-gate + R0.6.7 + close-gate Acceptance benches all say **PARTIAL**. | Measurement is process-lifetime `ru_maxrss` after identity **then** builtin **then** QuantLib in one process. QuantLib RSS is cumulative, not QuantLib-only. |
| scenarios/sec | **MET** at 10×50 | `scenarios_per_sec` from cold wall (S/sec, not N×S/sec). No `throughput` SLA. | Not an SLA; 100/1k still unrecorded as default evidence. |
| built-in vs QuantLib | **PARTIAL** | Same N×S skip-or-run; checksum match when QL is installed; hard-gate helper on the dedicated test. FINDINGS residual + close-gate name cash equity `quantity * spot`. | Book is cash equity. Same checksum as builtin is expected; it does not show N×S curve/instrument reconstruction (FINDINGS root cause). |
| warm vs cold | **MET** at 10×50 | Two wall times on the same engine/fixture; warm P&L matches cold. | “Cold” acceptance builtin runs after the 1×120 identity in the same process (not a process-cold start). Recorded, not SLA. |
| identical numerical results to pre-change goldens | **MET** | R0.6.1 checksum unchanged. 10×50 engine digest `a28cf4ee6199bf40da3f2598f4241fc85fa4adc4f86bccbbd97e4938047d7537`. | n/a |

**HEAD scoring check (`0a0739f`):** `Status: **IN PROGRESS**`; no `Status: **CLOSED**` on RF-007; `peak RSS **MET**` absent; `builtin vs QuantLib **MET**` absent; both cells **PARTIAL** in FINDINGS residual (L436), FINDINGS close-gate (L483), milestone R0.6.1 (L561), R0.6.7 (L623), close-gate Acceptance benches (L631), and exit “Benchmarked” line (L637).

**Still UNMET for P0 close sizes:** N=100 / 1k and S=750 / 1k in default PR (intentional; brief forbade 1k in PR).

Option A intra-run scenario-block multiprocessing remains **PARTIAL** (out of this slice).

R0.6 exit: explainable **yes**; bounded **yes**; appropriate **yes**; **benchmarked** at PR-safe 10×50 cash-equity (+ 1×120 identity) with peak RSS and QuantLib still **PARTIAL**. Close-gate **not complete**.

---

## Strengths

- Docs fix matches the prior Important exactly: FINDINGS residual, FINDINGS close-gate, milestone R0.6.1 / R0.6.7 / close-gate / exit line, and both reports now score RSS and QuantLib **PARTIAL** and name `ru_maxrss` plus cash-equity `quantity * spot`.
- Did not amend `c12de23`; second commit is `docs(r0.6):` only.
- Harness still records 10×50 without SLA floors; R0.6.1 identity pin kept; QuantLib skip-or-run unchanged.
- RF-007 status, KEEP OPEN, and “Do not close” survived the scoring rewrite.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

None. Prior Important (FINDINGS/milestone scoring QuantLib and peak RSS as MET) is resolved at `0a0739f`.

### Minor (Nice to Have)

Carried from the `c12de23` review; docs-only fix did not address them. Not blocking.

1. **Acceptance “cold” is not process-cold**
   - File: `benchmarks/run_full_reval_bench.py` `run_full_reval_identity` then `run_acceptance_matrix`.
   - Issue: Builtin acceptance cold/warm both run after the 1×120 identity in the same interpreter. QuantLib “cold” is first QL use but after builtin acceptance.
   - Impact: Warm vs cold walls are still two measurements on the same fixture (brief met). They are not a cold-start pair. Residual now notes cumulative RSS; a one-line “not process-cold” note remains optional.

2. **QuantLib bench test is not on the hard-gate job list**
   - File: `.github/workflows/ci.yml` `backend-quantlib-hard-gate` pytest list.
   - Issue: `test_full_reval_bench_quantlib_same_nxs` uses `import_quantlib()`, but that job does not collect `tests/test_full_reval_bench.py`. `backend-pytest` will run it when the wheel installs and will skip-green the QL test if the wheel is absent (`REQUIRE` unset).
   - Impact: Fail-closed QL coverage for this path depends on `backend-pytest` getting QuantLib, not on the dedicated hard-gate job.

3. **Harness runs the full matrix once per pytest that calls `_run_bench_json`**
   - File: `backend/tests/test_full_reval_bench.py`.
   - Issue: Identity, acceptance, and QuantLib tests each spawn `--json` (identity 1×120 + builtin 10×50 cold/warm + QuantLib 10×50 cold/warm). PR-safe, wasteful.
   - Fix (optional): one subprocess fixture shared by the JSON tests.

---

## Recommendations

- Lead / Task 7: treat 10×50 as the first recorded size above 1×120, not as a complete FINDINGS matrix. Do not CLOSE on cash-equity QuantLib walls or cumulative RSS.
- Do not add `nightly.yml` SLA-K1/K2 or assert floors on the recorded numbers.
- Option A stays PARTIAL / later P1 unless N=100/1k profiling says otherwise.
- If a later slice records QuantLib reconstruction, use a book that actually builds QL instruments (scalar option / curve), in a fresh process per engine if RSS is meant to be comparable.

---

## Assessment

**Spec compliance:** ✅

**Task quality:** Approved

**Issue counts:** Critical 0 / Important 0 / Minor 3 (carried)

**RF-007 still IN PROGRESS:** yes

**Lead may close RF-007:** no

**Reasoning:** Recording at 10×50 still matches the brief. The docs-only follow-up makes the close matrix honest: peak RSS and builtin vs QuantLib are **PARTIAL** at HEAD, RF-007 stays **IN PROGRESS**, and Task 7 still owns CLOSED vs KEEP OPEN.
