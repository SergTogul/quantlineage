# Final SDD Wave Review — R0 continuation Tasks 1–6

**Base:** `934379c`  
**Head:** `0a0739f` (`0a0739fb3414daf84659f0148b857d7da4daed5d`)  
**Diff reviewed:** `.superpowers/sdd/review-934379c..0a0739f.diff` (read once; git not mutated)  
**Plan:** `reviews/sdd-briefs/r0-continuation-plan.md`  
**Progress:** `.superpowers/sdd/progress.md`  
**Branch:** `r0-core-remediation`

This is the **final whole-wave review**, not a per-task gate. Per-task APPROVE reviews and implementer reports were treated as unverified claims. Evidence is the `934379c..0a0739f` tree, FINDINGS/milestone at HEAD, and an independent focused pytest run.

## Verdict

| Gate | Result |
|---|---|
| Ready to merge this wave | **Yes** |
| Spec compliance (Tasks 1–6 vs plan) | ✅ |
| Wave quality | **Approved** |
| Critical (must fix before merge) | **0** |
| Important (must fix before merge) | **0** |
| Minor that must be fixed before merge | **0** |
| RF-007 | **IN PROGRESS** — KEEP OPEN (plan-correct; not a defect) |
| Lead may close RF-007 | **no** |

Merge this wave. Do not CLOSE RF-007. Do not start the P1 queue (RF-011 / RF-013 / RF-014 / RF-016) until a later close re-gate actually records N=100/1k and honest RSS/QuantLib evidence.

---

## What landed

Eight commits:

| SHA | Slice |
|---|---|
| `35bf9fa` | R0.6.3 QuantLib structure reuse |
| `68c302a` | R0.6.4 unique-shock valuation LRU bypass |
| `8afd4e4` | R0.6.6 contribution reuse (joint P&L + Δ-Γ split) |
| `1458a22` | R0.6.5 option B — RiskRun / Compose worker is the process partition |
| `970d669` | Task 5 overreach: CLOSE RF-007 (superseded) |
| `6e3dbdc` | Task 5 fix: KEEP OPEN |
| `c12de23` | R0.6.7 PR-safe 10×50 acceptance benches |
| `0a0739f` | Honest PARTIAL scoring for RSS and builtin vs QuantLib |

Production surface: `quantlib.py` scalar-option / terms / swap-schedule reuse; `cache.py` `bypass_valuation_lru`; `historical.py` / `var.py` wrap unique-shock loops; `es.py` / `scenario_attribution.py` stop isolated-family revals; `risk_run_worker.py` docstring + HEAVY/RiskRun pins; bench harness records 10×50 without SLA floors.

No `backend/native/` edits. No methodology change on portfolio FULL_REVAL VaR/ES P&L. No fake SLA-K1/K2 / `check_m6_sla` / wall-time floors.

`970d669` in history is a process scar, not a HEAD defect. HEAD FINDINGS status is **IN PROGRESS**; close-gate heading is KEEP OPEN / not complete.

---

## Spec compliance vs continuation plan

| Plan item | HEAD evidence | Status |
|---|---|---|
| Task 1 R0.6.3 — reuse QuantLib structures where safe; no stale market; RF-007 stays open | `_ReusableScalarOption` live `SimpleQuote` updates; terms + swap schedules cached; surfaces/curves still rebuilt; cold-path P&L abs `1e-12`; FINDINGS still IN PROGRESS | Met |
| Task 2 R0.6.4 — unique-shock path does not pay anti-cache tax; no numerical drift | `bypass_valuation_lru` skips hash/get/put; production full-reval loops wrapped; base PV outside context; identity vs inner/cold abs `1e-12` | Met |
| Task 3 R0.6.6 — contribution reuse; preserve reconcile | Family helpers no longer `apply`+reprice per family×S; `interaction = joint − sum(families)`; cash-equity FULL vs LINEAR abs `1e-12`; reconcile abs `1e-6` / rel `1e-8` | Met |
| Task 4 R0.6.5 — processes not threads, or document RiskRun as the partition | **Choice B.** No `ProcessPoolExecutor`. HEAVY FULL_REVALUATION refused inline (`details.use=/risk/runs`); Compose `worker` is the OS-process partition. Option A PARTIAL | Met |
| Task 5 close gate — COMPLETE KEEP OPEN | FINDINGS **IN PROGRESS**; milestone `R0.6 close gate — KEEP OPEN / not complete`; `reviews/r0.6-rf007-close-gate-report.md` recommends KEEP OPEN | Met |
| Task 6 — record benches PR-safe; no fake SLA; do not close unless matrix is honest | Default 10×50 (> 1×120); finite `wall_ms` / RSS / scenarios/sec; skip-or-run QuantLib; pytest finiteness only; RSS and QL scored **PARTIAL** at `0a0739f` | Met |
| Global: no C++ kernel expansion; no methodology-only-for-speed on pricing/VaR P&L; identity vs goldens | Native untouched. Joint full-reval P&L unchanged. Factor *bucket* convention change is Task 3’s authorized decompose, documented in FINDINGS/R0.6.6 report | Met |
| RF-007 remains IN PROGRESS (KEEP OPEN): N=100/1k UNMET; RSS and builtin-vs-QuantLib PARTIAL | Matches HEAD FINDINGS residual + close-gate paragraph + milestone exit line | Met |
| Task 7+ P1 only after RF-007 CLOSED | Not started | Met |

Intentional, plan-correct remainders (not wave defects):

- N=100 / 1k and S=750 / 1k unrecorded as default PR evidence (brief forbade 1k in PR).
- Peak RSS is process-lifetime `ru_maxrss`; QuantLib figure includes prior builtin in the same process.
- Builtin vs QuantLib at 10×50 is cash equity `quantity * spot`, not curve/instrument reconstruction.
- Option A intra-run scenario-block multiprocessing not implemented (Task 4 preferred B).
- QuantLib vol surfaces, snapshot curves, and non-scalar instruments still rebuild (Task 1 “where safe”).

---

## Independent scores at HEAD

### Required direction (FINDINGS RF-007)

| # | Direction | Score | Notes |
|---|---|---|---|
| 1 | stream/chunk scenarios | **MET** | Pre-wave R0.6.2; loops consume iterators |
| 2 | build scenario market once | **MET** | RF-006 CLOSED |
| 3 | reuse instrument structures / relinkable handles where safe | **MET** | R0.6.3; remainder is documented safety, not unfinished scope |
| 4 | parallelize QuantLib scenario partitions by process, not threads | **PARTIAL** | Option B job process; not intra-run chunks |
| 5 | move large full-reval jobs to `RiskRun` | **MET** | RF-015 + R0.6.5 HEAVY pins |
| 6 | keep LINEAR / DELTA_GAMMA as fast default | **MET** | Unchanged; FULL_REVALUATION is HEAVY |
| 7 | remove/disable caches that slow unique-shock work | **MET** | R0.6.4 bypass on production full-reval loops |

**6 MET, 1 PARTIAL.** Architecture for R0.6.3–R0.6.6 is in place. Necessary for a later CLOSE; not sufficient.

### Acceptance matrix (after R0.6.7)

Agree with HEAD FINDINGS / milestone / `reviews/r0.6.7-acceptance-benches-report.md`. Peak RSS and builtin vs QuantLib are **PARTIAL**, not MET. That is the Task 6 Important fix and it holds at `0a0739f`.

| Item | Score | Still missing for CLOSE |
|---|---|---|
| N trades × S scenarios | **PARTIAL** | N=100 / 1k (and S=750 / 1k) in default PR |
| wall time | **MET** at 10×50 | Host-controlled 100/1k walls |
| peak RSS | **PARTIAL** | Fresh-process / QuantLib-only RSS; not cumulative `ru_maxrss` |
| scenarios/sec | **MET** at 10×50 | Not an SLA; 100/1k unrecorded as default evidence |
| builtin vs QuantLib | **PARTIAL** | Same N×S on a book that actually reconstructs QL instruments/curves |
| warm vs cold | **MET** at 10×50 | Two walls on one fixture; not process-cold (Minor) |
| identical numerical results to goldens | **MET** | R0.6.1 checksum `6602fa69…`; 10×50 `a28cf4ee…`; focused goldens passed here |

R0.6 exit: explainable **yes**; bounded **yes**; appropriate **yes**; **benchmarked** at PR-safe 10×50 cash-equity (+ 1×120 identity) with RSS and QuantLib still **PARTIAL**. Close-gate **not complete**.

The Task 5 report `reviews/r0.6-rf007-close-gate-report.md` still prints the **pre-R0.6.7** UNMET RSS / scenarios/sec / QuantLib table. That is a dated QA snapshot. **FINDINGS + milestone at HEAD are authoritative.**

---

## Calibration checks

### RF-007 still open

Plan-correct. Architecture APPROVE + honest 10×50 recording is not CLOSE. N=100/1k UNMET and RSS/QL PARTIAL are the written P0 residual. This review does not demand CLOSE.

### Methodology-only-for-speed

**No stealth change on joint P&L / VaR / ES portfolio numbers.** Unique-shock bypass and QuantLib quote relink preserve abs `1e-12` vs cold/inner.

Task 3 **did** change FULL_REVAL / stress *factor bucket* meaning: isolated-family full reval → Δ-Γ split of the already-priced joint P&L, remainder in `interaction`. The continuation plan authorized “reused or decomposed” with reconcile invariants. Constraint 3 is overridden by that task’s goal, not violated. Cash-equity identity and reconcile tests pin the linear path the goldens actually owned. Nonlinear remainder in `interaction` is documented in FINDINGS, the R0.6.6 report, and the close-gate residuals.

### Dishonest FINDINGS

**No at HEAD.** `0a0739f` scores peak RSS and builtin vs QuantLib **PARTIAL** and names `ru_maxrss` plus cash-equity `quantity * spot`. Status line is **IN PROGRESS**. Close-gate paragraph ends KEEP OPEN / Do not close. No `Status: **CLOSED**` on RF-007.

### Regressions

Independent focused run (not implementer-reported):

```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line \
  tests/test_quantlib_reuse.py \
  tests/test_pricing_anti_cache.py \
  tests/test_contribution_reuse.py \
  tests/test_scenario_attribution.py \
  tests/test_es_contributions.py \
  tests/test_var_es_golden.py \
  tests/test_var_methodology.py \
  tests/test_full_reval_bench.py \
  tests/test_r065_process_partition.py
```

**78 passed**, 1 pre-existing Starlette `TestClient` deprecation warning, 4.97s.

Did not re-run the full backend suite (~1200). No C++ / frontend / workflow edits in range.

---

## Strengths

- Safe QuantLib reuse model: contract keyed by evaluation date + economics; market pushed through `SimpleQuote` before every NPV/Greek read; surface/curve paths still rebuild from the current snapshot.
- Anti-cache is fail-closed on stale NPV: unique snaps always hit `_inner.value`; base snapshot still uses the LRU.
- Contribution reuse is structural (call-count / empty `apply` lists), not a wall-clock story. Reconcile is preserved.
- Option B is the right R0.6.5 call: document the shipped RiskRun partition rather than pickle QuantLib into an unused process pool.
- Task 5 overreach was reverted; Task 6 scoring was corrected without amending `c12de23`.
- Bench harness records 10×50 without floors; R0.6.1 identity pin kept; QuantLib skip-or-run with fail-closed `QUANTLINEAGE_REQUIRE_QUANTLIB`.
- Ownership stayed inside each slice’s charter paths; no dual-owned file fights in the range.

---

## Issues

### Critical (Must Fix)

None.

### Important (Must Fix before merge)

None.

### Minor that must be fixed before merge

None. Carry-forwards below are post-merge / next-slice polish. None of them are regressions, dishonest CLOSE, or methodology-for-speed.

### Minor (carry-forward; do not block merge)

Triaged from per-task reviews plus wave-level docs drift.

**Highest-priority follow-up (still not blocking):** product docs still describe the pre-R0.6.6 isolated-reval contribution model.

1. **ROADMAP + known_limitations still say isolated-reval / isolated shocks**  
   - `ROADMAP.md` ES bullet: “FULL_REVALUATION: factor-isolated reval + `interaction` residual”.  
   - `docs/known_limitations.md`: “interaction residual when isolated shocks do not add perfectly.”  
   - FINDINGS/milestone/R0.6.6 report tell the truth; the presentation catalog does not. Follow-up docs commit, not a merge gate. Optional short ADR if Lead wants the bucket convention in `docs/adr/`.

2. **`interaction` display label is still “Cross-factor interaction”**  
   - `scenario_attribution.py` `_INTERACTION_LABEL`; `es.py` `_FACTOR_LABELS`. After R0.6.6 the bucket also holds Taylor residual, option rate effects, and unmapped remainder. API key `interaction` is unchanged.

3. **Stale name `_factor_isolated_pnl`**  
   - Function no longer isolates or reprices. Rename when next touching attribution.

4. **T1 coverage / keying polish**  
   - FX reuse and swap-schedule hit-rate untested structurally; `_terms_key` uses full `model_dump_json` rather than `trade_cache_key`; duplicated option `Valuation` packing; unbounded per-engine structure/terms caches (relevant later if RSS is measured on a long-lived worker).

5. **T2 hygiene**  
   - ES/panel bypass untested with LRU spies (ES isolated loops were then deleted in T3; remaining gap is panel `full_revaluation_pnl_from_panel`). ContextVar is caller-opt-in. Unused `valuation_lru_bypassed()`. Risk modules import `app.pricing.cache`.

6. **T4 overlapping HEAVY pins**  
   - `test_r065_process_partition.py` re-pins R0.3.5 / RF-015 / bench-grep contracts. Unique coverage (FULL_REVALUATION summary under `HEAVY_INLINE=0`, QUEUED + dispatch) is enough. Docstring lock on `ProcessPoolExecutor` in `risk_run_worker.py` is wording, not behavior.

7. **T6 remaining Minors** (`reviews/sdd-briefs/task-6-rf007-benches-review.md`)  
   - Acceptance “cold” is not process-cold.  
   - `test_full_reval_bench_quantlib_same_nxs` is not on `backend-quantlib-hard-gate`.  
   - Each JSON pytest respawns the full harness.

8. **Dated Task 5 close-gate report vs HEAD matrix**  
   - `reviews/r0.6-rf007-close-gate-report.md` still lists RSS / scenarios/sec / QuantLib as UNMET. Leave it as the Task 5 snapshot; do not “fix” it into a second source of truth. FINDINGS wins.

9. **R0.6.7 milestone heading is still “COMPLETE pending review”**  
   - This review APPROVEs R0.6.7. Controller may flip the heading to COMPLETE with a pointer here. Not an implementer must-fix.

10. **`test_stress.py` comment still talks about factor-isolated extra applies**  
    - Behavior pin (`full_scenario_applies == 1`) still holds; comment is stale.

---

## Recommendations

- Merge `934379c..0a0739f` on `r0-core-remediation`. Keep RF-007 **IN PROGRESS**.
- Next P0 work for this finding is still the FINDINGS matrix at N=100/1k (operator/CLI, not a PR default), with RSS in a fresh process per engine and QuantLib on a reconstructing book — not option A, not C++, not `nightly.yml` SLA-K1/K2.
- Optional small docs follow-up: ROADMAP ES bullet + known_limitations interaction sentence + R0.6.7 “pending review” → COMPLETE.
- Do not treat recorded 10×50 `wall_ms` / `scenarios_per_sec` / `peak_rss_kib` as floors.

---

## Assessment

**Ready to merge this wave:** Yes

**Must fix before merge:** none (Critical 0 / Important 0 / blocking Minor 0)

**RF-007 status:** **IN PROGRESS**, close-gate **KEEP OPEN**. N=100/1k **UNMET** in default PR. Peak RSS **PARTIAL**. Builtin vs QuantLib **PARTIAL**. Lead may **not** close.

**Reasoning:** Tasks 1–6 match the continuation plan. Architecture slices R0.6.3–R0.6.6 are in place without C++ expansion or joint-P&L methodology drift. R0.6.7 records a PR-safe size above 1×120 and scores the close matrix honestly. Per-task Minors are polish and product-doc lag, not merge defects. RF-007 remaining open is the plan.
