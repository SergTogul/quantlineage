# Task 5 Report — RF-007 close gate

## Task
RF-007 close gate (score R0.6.1–R0.6.6; recommend CLOSE or KEEP OPEN)

## Owner
QA & Quant Validation Engineer

## Summary
Independent QA score of landed R0.6.1–R0.6.6 work. **Recommendation: KEEP OPEN.** Required-direction architecture is in place (6 MET, 1 PARTIAL: option B RiskRun/Compose worker job process, not intra-run scenario chunks). Joint N×S `value` is explainable and bounded as a HEAVY RiskRun job; goldens/identity checksum still match (69 passed on the original close-gate suite). Acceptance benches required for P0 close remain UNMET/PARTIAL: peak RSS, scenarios/sec, builtin vs QuantLib **UNMET**; N trades × S scenarios, wall time, and warm vs cold only **PARTIAL** at 1×120 builtin. Record N=100/1k (and S=50/750/1k where practical) wall, peak RSS, scenarios/sec, builtin vs QuantLib, warm vs cold; identity checksum stays; no SLA. Option A remains PARTIAL (may stay P1 after benches). No algorithm changes. No SLA invented.

## Files changed
- `reviews/FINDINGS.md` — RF-007 **IN PROGRESS**; RF-006 wall-clock pointer restored to remaining RF-007
- `reviews/REMEDIATION_MILESTONE.md` — § R0.6.3–R0.6.6 stay COMPLETE with APPROVE pointers; R0.6 close gate KEEP OPEN / not complete; R0.6.1 bench size remains 1×120
- `reviews/r0.6-rf007-close-gate-report.md` — scoring report; recommendation KEEP OPEN; honest tables retained
- `reviews/sdd-briefs/task-5-rf007-close-gate-report.md` — this handoff
- `reviews/sdd-briefs/task-1-r0.6.3-review.md` — cited APPROVE review (previously untracked in `970d669`)
- `reviews/sdd-briefs/task-2-r0.6.4-review.md` — cited APPROVE review (previously untracked)
- `reviews/sdd-briefs/task-3-r0.6.6-review.md` — cited APPROVE review (previously untracked)
- `reviews/sdd-briefs/task-4-r0.6.5-review.md` — cited APPROVE review (previously untracked)

## Public/interface changes
- None (docs only)

## Numerical conventions
- Units: unchanged (currency P&L; existing Greek/shock-unit conventions)
- Sign convention: unchanged (loss = −P&L)
- Day count/calendar if relevant: n/a
- Tolerances/reference: unit-equity `[-100, 0, 50]`; R0.6.1 checksum `6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f`; cash-equity FULL vs LINEAR family abs `1e-12`; contribution reconcile abs `1e-6` / rel `1e-8`; QuantLib reuse cold-path abs `1e-12`

## Tests added/updated
- None (docs-only close gate; original close-gate commit re-ran landed suites)

## Commands executed
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_full_reval_bench.py \
  tests/test_full_reval_golden.py \
  tests/test_quantlib_reuse.py \
  tests/test_pricing_anti_cache.py \
  tests/test_contribution_reuse.py \
  tests/test_r065_process_partition.py \
  tests/test_var_methodology.py \
  tests/test_es_contributions.py \
  tests/test_scenario_attribution.py
```

## Results
- Backend: **69 passed** in 3.10s (1 pre-existing Starlette `TestClient` deprecation warning) — recorded on the original docs close-gate commit; not re-run for this KEEP OPEN docs fix
- Frontend: n/a
- QuantLib: reuse tests included; no methodology change
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **n/a** (docs-only; no suite)
- Unexplained failures or skips: none
- CI is green (all required checks): not started (docs commit; no production change)

## Known limitations / risks
- Acceptance benches UNMET/PARTIAL: RSS / scenarios/sec / builtin vs QuantLib UNMET; N×S / wall / warm-cold PARTIAL at 1×120 builtin
- Option A intra-run scenario-block multiprocessing not implemented (PARTIAL; may stay P1 after benches)
- R0.6.3 safety remainder: surfaces/curves/non-scalar instruments still rebuild
- Factor buckets under FULL_REVAL are Δ-Γ-plus-residual, not isolated reval
- Lead Architect applies KEEP OPEN; RF-007 stays IN PROGRESS

## Follow-up / next owner
- Owner: Lead Architect
- Requested action: keep RF-007 IN PROGRESS; next P0 work is the recorded bench matrix (not option A, not a nightly SLA from `wall_ms`)
- Blocking?: yes — RF-007 stays open until acceptance benches are recorded

## Return line
DONE | KEEP OPEN | architecture in place (R0.6.1–R0.6.6 APPROVE); acceptance benches UNMET/PARTIAL at 1×120 builtin; RF-007 IN PROGRESS

## Fix note (KEEP OPEN after spec review)

Independent review of `970d669` (**KEEP OPEN**; Lead adjudication: reviewer's KEEP OPEN governs). This follow-up is **docs-only**; no production/pricing/risk algorithm edits; **no pytest suite** re-run.

Fixes applied:

- FINDINGS RF-007 Status reverted to **IN PROGRESS**. Status line lists R0.6.1–R0.6.6 APPROVE (architecture in place) and the residual: RSS / scenarios/sec / builtin-vs-QuantLib **UNMET**; N×S / wall / warm-cold only **PARTIAL** at 1×120 builtin. Remaining benches are not labeled P1 blocking-close leftovers.
- RF-006 pointer restored: wall-clock N×S pricing remains RF-007.
- Milestone R0.6.3–R0.6.6 stay COMPLETE with APPROVE reviews. Close-gate section is **KEEP OPEN / not complete**. Does not say RF-007 CLOSED or R0.6 close-gate COMPLETE.
- Scoring reports recommend **KEEP OPEN**; honest MET/PARTIAL/UNMET tables retained. RF-008 analogy and “no fake SLA” as a recording waiver removed.

**Test results:** docs-only; no suite.
