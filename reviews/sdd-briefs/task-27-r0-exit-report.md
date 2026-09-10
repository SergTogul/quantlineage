# Task 27 Report — RF-020 + R0 exit checklist + P2 accepted residuals

## Task
RF-020 close + R0 Final Exit Checklist honesty + P2 ACCEPTED / DEFERRED

## Owner
Lead Architect / Orchestrator (`docs/agents/01_LEAD_ARCHITECT.md`) — documentation honesty; no pricing/risk code

## Status
**CLOSED.** RF-020 **CLOSED**. Milestone R0 **COMPLETE**. P2 RF-017 / RF-018 / RF-019 **ACCEPTED / DEFERRED** (not CLOSED as MET).

## Summary
Filled the R0 exit checklist honestly: MET items `[x]`; RF-014 shared auth/ACLs/TLS, RF-016 labeled-runner SLA-K1/K2, and QA-024 stay `[~]` / accepted residual (not MET). ROADMAP Current gate and FINDINGS header now say Milestone R0 COMPLETE and no longer say IN PROGRESS while claiming COMPLETE. `docs/known_limitations.md` names the residuals. Dated Phase A suite counts remain **not a live** re-run (allowed). Included leftover R0.12.7 APPROVE stamp on the milestone. TDD docs pins failed first, then docs landed. No C++ / IAM / TypeScript / AI implementation. No pricing/risk code changed.

## Files changed
- `backend/tests/test_rf020_r0_exit.py` — FINDINGS / ROADMAP / milestone / known_limitations honesty pins (TDD: failed first)
- `reviews/FINDINGS.md` — header Milestone R0 COMPLETE; RF-020 CLOSED; RF-017/018/019 ACCEPTED / DEFERRED; release gate updated
- `reviews/REMEDIATION_MILESTONE.md` — Status COMPLETE; R0.12.7 APPROVE stamp; exit checklist `[x]`/`[~]`; P2 deferred
- `ROADMAP.md` — Current gate and Progress row COMPLETE; Phase A baseline still not re-run
- `docs/known_limitations.md` — RF-014 ACLs/TLS, RF-016 SLA-K1/K2, QA-024, RF-017/018/019 named not MET
- `reviews/r0-exit-checklist-report.md` — scoring report
- `reviews/sdd-briefs/task-27-r0-exit-report.md` — this handoff

## Public/interface changes
- None. Docs and pins only.

## Numerical conventions
- Units: n/a (docs honesty)
- Sign convention: n/a
- Day count/calendar if relevant: n/a
- Tolerances/reference: n/a. Suite integers in ROADMAP remain the recorded Phase A baseline (builtin **659** pre-insertion; QuantLib **688** post-R0.1); not rewritten as a live matrix.

## Tests added/updated
- `test_findings_header_declares_milestone_r0_complete`
- `test_findings_rf020_closed_with_dated_count_disclaimer`
- `test_p2_findings_are_accepted_deferred_not_closed_as_met`
- `test_all_p0_and_p1_findings_are_closed`
- `test_roadmap_current_gate_says_r0_complete_not_in_progress`
- `test_roadmap_does_not_claim_complete_while_in_progress`
- `test_milestone_status_complete_and_checklist_distinguishes_residuals`
- `test_accepted_residuals_are_not_checked_as_met`
- `test_known_limitations_name_r0_accepted_residuals`
- `test_findings_release_gate_matches_r0_complete`
- Existing: `tests/test_rf016_close_gate.py` (RF-016 CLOSED + labeled-runner residual)

TDD: 9 failed, 3 passed (P0/P1 already CLOSED; RF-016 pins already green). After docs: 12 passed.

## Commands executed
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_rf020_r0_exit.py tests/test_rf016_close_gate.py
# RED: 9 failed, 3 passed

PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_rf020_r0_exit.py tests/test_rf016_close_gate.py
# GREEN: 12 passed in 2.28s

.venv/bin/ruff check tests/test_rf020_r0_exit.py tests/test_rf016_close_gate.py
# All checks passed
```

## Results
- Backend required suite: **12 passed** in 2.28s. Ruff: all checks passed.
- Frontend: n/a
- QuantLib: not exercised numerically this slice
- C++: n/a
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## Known limitations / risks
- RF-014 object ACLs / TLS / secrets remain unimplemented (accepted residual, not MET)
- RF-016 labeled-runner SLA-K1/K2 not CI-enforced (accepted residual, not MET)
- QA-024 demo-artifact range still absent (leftover residual, not MET)
- Live full-suite recount was not re-run; Phase A 659/688 stay dated
- P2 RF-017 / RF-018 / RF-019 remain deferred
- Do not check accepted residuals as MET in later docs

## Follow-up / next owner
- Owner: independent reviewer / Lead Architect integration
- Requested action: treat R0 COMPLETE as docs-honest with named residuals; do not implement C++ / IAM / TypeScript / AI from this close; do not force-push
- Blocking?: no
