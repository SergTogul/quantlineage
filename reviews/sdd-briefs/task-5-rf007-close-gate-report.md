# Task 5 Report — RF-007 close gate

## Task
RF-007 close gate (score R0.6.1–R0.6.6; recommend CLOSE or KEEP OPEN)

## Owner
QA & Quant Validation Engineer

## Summary
Independent QA score of landed R0.6.1–R0.6.6 work. **Recommendation: CLOSE** RF-007 with P1 residuals. Required-direction architecture is in place (6 MET, 1 PARTIAL: option B RiskRun/Compose worker job process, not intra-run scenario chunks). Joint N×S `value` is now the explainable cost of full reval, bounded as a HEAVY RiskRun job; goldens/identity checksum still match (69 passed). Remaining bench matrix (N=100/1k, RSS, scenarios/sec, builtin vs QuantLib, warm vs cold) and option A multiprocessing are P1, same class as RF-008 limits/drilldown. No algorithm changes. No SLA invented.

## Files changed
- `reviews/FINDINGS.md` — RF-007 **CLOSED** with P1 residuals; RF-006 wall-clock pointer updated
- `reviews/REMEDIATION_MILESTONE.md` — § R0.6.3–R0.6.6 pending-review → COMPLETE with review pointers; R0.6 close gate; R0.6.1 bench size corrected to 1×120
- `reviews/r0.6-rf007-close-gate-report.md` — scoring report
- `reviews/sdd-briefs/task-5-rf007-close-gate-report.md` — this handoff
- `reviews/sdd-briefs/task-1-r0.6.3-review.md` — cited APPROVE review (previously untracked)
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
- None (docs-only close gate; re-ran landed suites)

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
- Backend: **69 passed** in 3.10s (1 pre-existing Starlette `TestClient` deprecation warning)
- Frontend: n/a
- QuantLib: reuse tests included; no methodology change
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (docs commit; no production change)

## Known limitations / risks
- N=100/1k wall/RSS/scenarios-sec/builtin-vs-QuantLib/warm-vs-cold not recorded (P1)
- Option A intra-run scenario-block multiprocessing not implemented (P1)
- R0.6.3 safety remainder: surfaces/curves/non-scalar instruments still rebuild
- Factor buckets under FULL_REVAL are Δ-Γ-plus-residual, not isolated reval
- Lead Architect applies CLOSE after task review of this recommendation

## Follow-up / next owner
- Owner: Lead Architect
- Requested action: apply RF-007 CLOSED (or reject and keep open); do not add a nightly SLA from `wall_ms`
- Blocking?: no

## Return line
DONE | CLOSE | required-direction architecture is in place; N×S joint pricing is explainable and bounded as a RiskRun job; remaining benches are P1
