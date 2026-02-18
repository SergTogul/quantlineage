# Agent Handoff — CI failure triage

## Task
Triage GitHub Actions failures on `origin/master`, document in ROADMAP, harden reverse-stress E2E locator, confirm green.

## Owner
DevOps / Platform + QA & Quant Validation

## Summary
User reported failing pipelines. Audited recent GHA runs on `master`.

**Failing jobs found (historical, already superseded on HEAD):**

| Run | SHA | Failed job(s) | Root cause |
|-----|-----|---------------|------------|
| [33700340552](https://github.com/SergTogul/riskforge-mvp/actions/runs/33700340552) | `8409b7e` | **e2e-playwright** | Heading locator `Reverse Stress` matched both single-factor and multi-factor cards (strict mode) |
| [33680821074](https://github.com/SergTogul/riskforge-mvp/actions/runs/33680821074) | `68322c7` | backend-pytest + lint-static-analysis | Early land (fixed in later commits) |

**HEAD at triage:** `f74b528` — [33701266538](https://github.com/SergTogul/riskforge-mvp/actions/runs/33701266538) **success** — all jobs: `backend-pytest`, `frontend-test-build`, `lint-static-analysis`, `postgres-persistence-smoke`, `e2e-playwright`.

This change: ROADMAP (honest failure record), `data-testid="reverse-stress"` on single-factor card, E2E uses testid (durable vs heading substring).

## Files changed
- `ROADMAP.md` — + highest-risk gap note
- `frontend/src/components/ScenarioBuilder.jsx` — `data-testid="reverse-stress"`
- `e2e/tests/reverse-stress.spec.ts` — locate via testid
- `docs/agents/HANDOFF_CI_TRIAGE.md` — this handoff

## Public/interface changes
- None (UI testid only; no API / PricingEngine / risk math)

## Numerical conventions
- N/A (no risk/pricing changes)

## Tests added/updated
- E2E reverse-stress single-factor path uses `getByTestId('reverse-stress')`

## Commands executed
```bash
gh run list --repo SergTogul/riskforge-mvp --branch master --limit 12
gh run view 33701266538 --json conclusion,jobs,...
gh run view 33700340552 --log-failed
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q
cd backend && ruff check app tests && mypy app
cd frontend && npm test && npm run lint
# native g++ kernel_test + shared lib (CI parity)
```

## Results
- Backend: **571 passed** (QuantLib), ruff/mypy OK
- Frontend: **61** node:test + **9** Vitest passed; ESLint OK
- QuantLib: 1.43
- C++: `risk_kernel_ok` + shared lib OK
- GHA HEAD: success run 33701266538 (pre-hardening); post-hardening **success** https://github.com/SergTogul/riskforge-mvp/actions/runs/33703670779 (SHA `16c91cc`; all five jobs green)

## Known limitations / risks
- Local Playwright under Cursor sandbox aborts Chrome (`kill EPERM`); trust GHA `e2e-playwright` + prior green evidence for E2E.
- `gh` keyring token was stale earlier; `full_network` `gh run list` worked with existing session.

## Follow-up / next owner
- Owner: Lead Architect
- Requested action: Continue SLA residuals; keep as historical CI honesty (not a new open workstream)
- Blocking?: no (master CI green at triage; hardening is preventive)
