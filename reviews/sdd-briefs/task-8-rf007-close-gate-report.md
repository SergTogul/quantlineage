# Task 8 Report — RF-007 close gate (after reconstruction benches)

## Task
RF-007 close gate after Task 7 reconstruction benches (independent CLOSE vs KEEP OPEN)

## Owner
QA & Quant Validation Engineer

## Status
**DONE_WITH_CONCERNS**

## Summary
Independent close re-gate of RF-007 at BASE `78c1d0e` (Task 7 APPROVE). Implementer claims were not trusted. Required direction and acceptance matrix scored from on-disk files plus a fresh pytest run. **Disposition: CLOSE.** P0 required direction is met (6 MET; option A process-chunk **PARTIAL** as **P1 residual**, same as Task 4). Reconstruction, N×S recording, and identity are not UNMET. Peak RSS stays **PARTIAL** (isolated child `ru_maxrss` — measurement limit, not MET). N=1k remaining **UNMET** is not a KEEP OPEN: N=100 nightly is recorded and FINDINGS never set a fake 1k SLA. This is not a restamp of rejected CLOSE `970d669`. Controller does not treat CLOSED as final until this task’s review APPROVE. No production/pricing/risk algorithm change. No SLA invented.

## Files changed
- `reviews/FINDINGS.md` — RF-007 **CLOSED** with independent-review placeholder; honest matrix; P1 residuals named
- `reviews/REMEDIATION_MILESTONE.md` — R0.6 related finding CLOSED pending review; R0.6.8 COMPLETE with Task 7 APPROVE pointer; close-gate section CLOSE pending independent review
- `reviews/r0.6.9-rf007-close-gate-report.md` — scoring report
- `reviews/sdd-briefs/task-8-rf007-close-gate-report.md` — this handoff

## Public/interface changes
- None (docs only)

## Numerical conventions
- Units: unchanged (currency P&L; existing Greek/shock-unit conventions)
- Sign convention: unchanged (loss = −P&L)
- Day count/calendar if relevant: reconstruction as_of `2026-09-01`
- Tolerances/reference: R0.6.1 checksum `6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f`; cash-equity 10×50 `a28cf4ee…`; reconstruction builtin `3148a41a…` / QuantLib `0594ecd6…`; option-match `rel=2e-3`; warm==cold atol `1e-12`

## Tests added/updated
- None (docs-only close gate). Landed reconstruction/nightly/identity suites were re-run, not edited.

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
  tests/test_scenario_attribution.py \
  tests/test_nightly_ci.py \
  tests/test_pr_full_ci.py

RISKFORGE_NIGHTLY=1 PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_nightly_full_reval_n100.py
```

## Results
- Backend close-gate suite: **96 passed**, 1 pre-existing Starlette `TestClient` deprecation warning, 12.18s
- Nightly N=100 reconstruction: **1 passed**, 5.45s
- Frontend: n/a
- QuantLib: included in the 96; no methodology change
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes** (docs-only; verification suite green)
- Unexplained failures or skips: none
- CI is green (all required checks): not started (docs commit; no production change)

## MET vs PARTIAL vs UNMET (this gate)

Required direction: 1 stream **MET**; 2 market-once **MET**; 3 reuse **MET**; 4 process partitions **PARTIAL** (option B); 5 RiskRun **MET**; 6 DELTA_GAMMA default **MET**; 7 anti-cache **MET**.

Acceptance: N×S **PARTIAL**; wall **MET**; peak RSS **PARTIAL**; scenarios/sec **MET**; builtin vs QuantLib **MET**; warm vs cold **MET**; identity **MET**.

## Why CLOSE (not KEEP OPEN)
Task 5 KEEP OPEN’d because cash-equity QuantLib, process-lifetime RSS, and N=100/1k were unmet. Task 7 APPROVE recorded reconstruction-honest European options, isolated RSS subprocesses, and nightly N=100×50. Reconstruction and identity are MET. N×S recording exists (N=100 nightly). Remaining option A PARTIAL and peak RSS PARTIAL are documented P1 / measurement-limit residuals the brief allows on CLOSE. Would defend to a second reviewer if those cells stay PARTIAL and are not relabeled MET.

## Known limitations / risks
- Peak RSS is still not incremental kernel RSS (`ru_maxrss` in an isolated child)
- N=1k and S=750/1k remain UNMET (not an SLA)
- Option A intra-run multiprocessing not implemented (P1)
- QuantLib reconstruction checksum is version-sensitive
- Independent review may still KEEP OPEN; CLOSED is a QA recommendation with placeholder
- Nightly job `RISKFORGE_PRICING_ENGINE: builtin` is a carry-forward Minor (engines constructed directly)

## Follow-up / next owner
- Owner: independent Task 8 reviewer, then Lead Architect
- Requested action: APPROVE or KEEP OPEN; apply CLOSED only on APPROVE
- Blocking?: no for further P0 architecture; yes for declaring the finding closed until review APPROVE

## Return line
DONE_WITH_CONCERNS | CLOSE | required 6 MET / 1 PARTIAL(option A P1); N×S PARTIAL; wall MET; peak RSS PARTIAL; scen/sec MET; QL MET; warm/cold MET; identity MET
