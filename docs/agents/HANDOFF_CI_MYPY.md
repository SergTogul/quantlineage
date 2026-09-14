# Agent Handoff — CI mypy / lint regression

## Task
Fix CI lint failure (mypy on PortfolioService), run full affected suites, push, attempt `gh run watch`.

## Owner
DevOps / Platform + QA & Quant Validation

## Summary
Local reproduction matched CI `lint-static-analysis`: `mypy app` failed because `PortfolioService.__init__` used a ternary `isinstance` that did not narrow `risk: RiskEngine` before reading `.seed` / `.observations`.

Fix: statement-level `isinstance(risk, HistoricalRiskEngine)` then build `hist_kwargs`. Pushed to `master` as `11339c6`.

**Standing rule for future agents:** run the full affected CI command set **before** every push. Never claim green without fresh local evidence. Do **not** spam `gh auth login` / device codes.

## Files changed
- `backend/app/services/portfolio_service.py` — mypy narrowing fix
- `ROADMAP.md` — honest record
- `docs/agents/HANDOFF_CI_MYPY.md` — this handoff

## Public/interface changes
- None (internal type-narrowing only; PricingEngine / risk math untouched)

## Numerical conventions
- N/A

## Tests added/updated
- None required (existing suites cover PortfolioService)

## Commands executed
```bash
# Local CI parity
cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib python -m pytest -q
cd backend && ruff check app tests && mypy app
# native g++ kernel_test + libriskkernel.so
cd frontend && npm test && npm run lint && npm run build

/usr/bin/git push origin HEAD # 8d3d67a..11339c6

# gh (failed — do not re-auth loop)
gh auth status # token in keyring is invalid
gh run list -L 8 # Forbidden
```

## Results
- Backend: **619 passed** (QuantLib 1.43), 1 Starlette/httpx warning
- Frontend: **70** Vitest passed; ESLint OK; Vite build OK
- Ruff/mypy: OK after fix
- C++: `risk_kernel_ok` + shared lib OK
- Push: **succeeded** to `origin/master` (`11339c6`)
- GHA watch: **blocked** — `gh` API Forbidden (invalid keyring token). Git push/fetch still works.

## Known limitations / risks
- Cannot confirm GHA all-jobs green via CLI until `gh` keyring token is repaired **once** by a human (no agent device-code loops).
- Expected Actions URL pattern: https://github.com/SergTogul/quantlineage/actions for SHA `11339c6`.

## Follow-up / next owner
- Owner: whoever has a working `gh` session
- Requested action: `gh run list -L 5`; `gh run watch` on the `11339c6` run; paste success URL into ROADMAP and check the box
- Blocking?: **partial** — code fix on master; GHA URL confirmation only
