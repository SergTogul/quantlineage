# Handoff — M9.10 reverse-multi E2E close → Lead Architect

## Task
Close M9.10 multi-factor reverse Playwright E2E; keep Milestone 9 honest (PARTIAL)

## Owner
QA & Quant Validation → next: Lead Architect / Orchestrator

## Summary
- Confirmed and hardened live Playwright coverage for Stress-section **Multi-Factor Reverse Stress** (`data-testid=reverse-stress-multi`): navigate `#stress`, fill target loss / max shock / weights, toggle factors, assert Status Converged/Not converged + shock table factor rows; separate client-validation path for fewer than two factors.
- Fixed selector flake: single-factor **Reverse Stress** card now uses `exact: true` so it does not match **Multi-Factor Reverse Stress**; scoped Target/Achieved asserts to `.attribution-total` to avoid message-text collisions.
- Spec/selectors only — no product UI or API changes. No invented PnL or shock magnitudes.
- **M9.10 DONE**. Milestone 9 remains **PARTIAL** (M9.8 Redis/RQ optional still open). Do **not** invent Milestone 9 COMPLETE.

## Files changed
- `e2e/tests/reverse-stress.spec.ts` — multi-factor fill/status + validation E2E; exact heading for single-factor card
- `e2e/tests/m8-panels.spec.ts` — comment: reverse-multi E2E closed under reverse-stress.spec
- `ROADMAP.md` — M9.10 DONE; Milestone 9 still PARTIAL on M9.8
- `docs/agents/HANDOFF_M9_QA_REVERSE_MULTI_E2E.md` (this file)

## Public/interface changes
- None

## Numerical conventions
- Units: N/A (structural UI assertions only; display % filled in form, values not asserted numerically)
- Sign convention: N/A
- Day count/calendar: N/A
- Tolerances/reference: N/A — no PnL/shock golden asserts in E2E

## Tests added/updated
- Playwright: multi-factor validation (fewer than two factors → error, no result panel)
- Playwright: multi-factor solve with equity+vol+rates + filled controls → Status + table rows for equity/vol/rates
- Playwright: single-factor Reverse Stress selector hardened (`exact: true`)

## Commands executed
```bash
cd e2e && npm test
# → 12 passed (35.9s)
```

## Results
- Backend: unchanged (live uvicorn via Playwright webServer, builtin pricing)
- Frontend: unchanged product code; E2E against Vite dev server
- QuantLib: N/A for this E2E run (`RISKFORGE_PRICING_ENGINE=builtin`)
- C++: N/A
- Build: N/A
- Milestone 9: **PARTIAL** — M9.10 closed; M9.8 Redis/RQ optional remains

## Known limitations / risks
- Multi-factor solve may return **Not converged** (e.g. target unreachable within max shock); E2E accepts Converged|Not converged structurally.
- Local macOS uses Chrome channel; GHA `e2e-playwright` uses Chromium when `CI=true` — config unchanged.
- Post-push: SHA `a61c29a` on `origin/master`. GHA **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33700677387 ; `e2e-playwright` https://github.com/SergTogul/riskforge-mvp/actions/runs/33700677387/job/100479144624 (clears `8409b7e` heading collision).

## Follow-up / next owner
- Owner: Lead Architect / Orchestrator
- Requested action (pick path; do not rubber-stamp M9 COMPLETE):
  1. **M9.8** — explicitly defer Redis/RQ as out-of-scope optional and document acceptance criteria for marking M9.8 DONE on current compose (postgres+backend+worker+frontend), **or** implement Redis/RQ if still required.
  2. **M3.8** — formal `Scenario` as stress HTTP wire type (still open residual).
  3. **M6** — risk-path wall-time SLA (keeps M6 PARTIAL until claimed with evidence).
  4. **M10** — demo portfolios / reproducibility once M9 honesty settled.
- Blocking?: no for M9.10; **yes** for Milestone 9 COMPLETE until M9.8 disposition
