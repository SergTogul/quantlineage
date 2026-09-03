# Handoff — M9.1 + M9.3/M9.5 (QA)

## Task
M9.1 Vitest/RTL/MSW; then M9.3 Hypothesis broaden + M9.5 stress invariants

## Owner
QA & Quant Validation Engineer (Frontend harness only for M9.1)

## Summary
- **M9.1 DONE (staged):** Vitest + RTL + MSW dual-run with existing node:test lib helpers; representative component slice (MetricCard, AppNav, ScenarioBuilder + MSW).
- **M9.3 DONE (staged):** Hypothesis portfolio/VaR properties beyond pricing Greeks.
- **M9.5 DONE (staged):** Hypothesis stress aggregation / empty / monotonicity invariants.
- Milestone 9 remains **PARTIAL** — do **not** mark COMPLETE.

## Files changed
### M9.1 (`bd46a1a`)
- `frontend/package.json`, `package-lock.json`, `vite.config.js`, `eslint.config.js`
- `frontend/src/test/{setup,mswServer}.js`
- `frontend/src/components/{MetricCard,AppNav,ScenarioBuilder}.test.jsx`
- `ROADMAP.md`, `BUILD_NOTES.md`

### M9.3 / M9.5 (this commit)
- `backend/tests/test_m9_risk_properties.py`
- `ROADMAP.md`
- `docs/agents/HANDOFF_M9_QA.md` (this file)

## Public/interface changes
- None (tests + docs + frontend test harness only)

## Numerical conventions
- VaR/ES: currency loss, floored ≥ 0; ES99 ≥ VaR99 ≥ VaR95
- Component VaR: Euler allocation; Σ components = parametric VaR (abs 1e-6 / rel 1e-8)
- Stress: portfolio pnl = Σ by_position (abs 1e-9); long equity equity-shock monotone

## Tests added/updated
- Vitest/RTL/MSW: 6 component tests
- Hypothesis: 6 properties in `test_m9_risk_properties.py`

## Commands executed
```bash
cd frontend && npm test && npm run lint && npm run build
# → 56 node:test + 6 Vitest; lint OK; build OK

cd backend && pytest tests/test_m9_risk_properties.py tests/test_quant_properties.py tests/test_component_var.py -q
# → 20 passed
```

## Results
- Frontend: green (dual-run)
- Backend focused: 20 passed
- Milestone 9: still PARTIAL

## Known limitations / risks
- Lib helpers still on node:test (migration residual for M9.1)
- M9.4 golden instrument expand not done
- M9.8 Redis/RQ optional containers not done
- Multi-factor reverse stress has API but **no UI panel** → blocks M9.10 reverse-multi E2E

## Follow-up / next owner
1. **Owner: Quant Pricing / QA — M9.4** — Expand `test_quantlib_golden.py` (IRS/FX/futures golden bands; close or document bond day-count gap). Blocking?: no for M9 complete until done.
2. **Owner: Frontend — reverse-multi UI** — Stress section multi-factor reverse panel wired to `POST /risk/stress/reverse/multi`; then QA closes M9.10 residual E2E. Blocking?: yes for that E2E gap.
3. **Owner: DevOps — M9.8** — Optional Redis/RQ worker path in compose (Postgres SKIP LOCKED path already exists). Blocking?: no (optional).
4. Do **not** mark Milestone 9 COMPLETE until M9.4 + M9.8 honesty + reverse-multi E2E (or explicit deferral) are settled.
