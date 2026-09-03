# Handoff — Multi-factor reverse stress UI → QA M9.10

## Task
Multi-factor reverse-stress panel (Frontend) so QA can close remaining M9.10 reverse-multi E2E

## Owner
Frontend / Risk UX Engineer → next: QA & Quant Validation

## Summary
- Added Stress-section **Multi-Factor Reverse Stress** panel (`ReverseStressMulti`) calling existing `POST /api/v1/risk/stress/reverse/multi` via `reverseStressMulti`.
- UI displays API results only (converged status, target/achieved loss %, P&L, factor shocks, method, assumptions). No client-side search, optimization, or risk math.
- Factor checkboxes (default equity+vol), target loss %, max shock %, optional weights; local validation requires ≥2 factors.
- Structural Playwright coverage for labels/status; full M9.10 close remains QA.

## Files changed
- `frontend/src/components/ScenarioBuilder.jsx` — `ReverseStressMulti` panel
- `frontend/src/App.jsx` — mount under Stress section
- `frontend/src/lib/risk.mjs` — request/display helpers
- `frontend/src/lib/risk.test.mjs` — helper unit tests
- `frontend/src/components/ReverseStressMulti.test.jsx` — RTL/MSW component tests
- `frontend/src/test/mswServer.js` — reverse/multi fixture
- `frontend/src/styles.css` — panel layout
- `e2e/tests/reverse-stress.spec.ts` — structural multi-factor E2E
- `e2e/tests/m8-panels.spec.ts` — comment update
- `ROADMAP.md` — honest PARTIAL updates
- `docs/agents/HANDOFF_M9_FRONTEND_REVERSE_MULTI.md` (this file)

## Public/interface changes
- None on backend. Frontend consumes existing `MultiFactorReverseStressRequest` / `MultiFactorReverseStressResult`.

## Numerical conventions
- Units: form uses display % for target loss and max shock; helpers convert to API fractions (`/100`). Rates shocks displayed as `bp` when `shock_unit === 'bp'` from API; relative factors via existing `percent()`.
- Sign convention: display API `required_shock` / `pnl` unchanged.
- Day count/calendar: N/A
- Tolerances/reference: N/A (no client risk math)

## Tests added/updated
- `validateReverseMultiForm` / `reverseMultiRequestBody` / `formatFactorShock` / expanded summary (`risk.test.mjs`)
- RTL: empty/validation, MSW success fixture, API error (`ReverseStressMulti.test.jsx`)
- Playwright: labels + Converged/Not converged status after Solve (`reverse-stress.spec.ts`)

## Commands executed
```bash
cd frontend && npm test
# → node:test 61 passed; Vitest 9 passed (4 files)

cd frontend && npm run build
# → Vite production build OK

cd frontend && npm run lint
# → eslint OK (max-warnings 0)
```

## Results
- Backend: unchanged
- Frontend: 61 node:test + 9 Vitest passed; lint OK; production build OK
- QuantLib: N/A
- C++: N/A
- Build: Vite `dist/` OK
- Milestone 9: still PARTIAL (M9.8 + M9.10 QA close open)
## Known limitations / risks
- Solver is ray + coordinate descent (not a certified global optimum); UI surfaces API `assumptions` / `method` honestly.
- Structural E2E asserts status labels, not shock magnitudes — QA should confirm live suite green and any residual M9.10 breadth.
- Milestone 9 must stay **PARTIAL** (M9.8 Redis optional; M9.10 not CLOSED until QA signs off).

## Follow-up / next owner
- Owner: QA & Quant Validation
- Requested action: Run / confirm Playwright reverse-multi E2E against live stack; update M9.10 checklist; do **not** invent Milestone 8/9 COMPLETE.
- Blocking?: yes for honest M9.10 reverse-multi close (UI unblocked; E2E confirmation remaining)
