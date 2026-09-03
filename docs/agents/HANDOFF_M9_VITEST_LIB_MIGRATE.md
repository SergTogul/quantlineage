# Agent Handoff: M9.1 residual — lib `*.mjs` → Vitest

## Task
Migrate leftover frontend `src/lib/*.test.mjs` (node:test) onto Vitest without breaking `npm test` / CI.

## Owner
QA & Quant Validation (+ Frontend harness)

## Summary
Converted `risk.test.mjs`, `nav.test.mjs`, and `heatmap.test.mjs` to Vitest suites (`*.test.js`) using `import { test } from 'vitest'` + existing `node:assert/strict` assertions. Dropped the vite exclude for lib tests. `npm test` is now a single Vitest run; `test:node` aliases to `vitest run src/lib` for script-name continuity. No client risk math; production helpers remain `.mjs` display/request-only. Backend / M1.12 bond pricing untouched.

## Files changed
- `frontend/src/lib/risk.test.js` (added; replaces `risk.test.mjs`)
- `frontend/src/lib/nav.test.js` (added; replaces `nav.test.mjs`)
- `frontend/src/lib/heatmap.test.js` (added; replaces `heatmap.test.mjs`)
- `frontend/src/lib/risk.test.mjs` (deleted)
- `frontend/src/lib/nav.test.mjs` (deleted)
- `frontend/src/lib/heatmap.test.mjs` (deleted)
- `frontend/vite.config.js` (remove lib `*.test.mjs` exclude)
- `frontend/package.json` (`npm test` → `vitest run`; `test:node` → lib Vitest alias)
- `ROADMAP.md` (M9.1 residual note + progress update)
- `docs/agents/HANDOFF_LEFTOVERS.md` (mark lib migrate closed)
- `docs/agents/HANDOFF_M9_VITEST_LIB_MIGRATE.md` (this file)

## Public/interface changes
- None (test harness / scripts only). CI still invokes `npm test` in `frontend/`.

## Numerical conventions
- N/A — display/request helper tests only; no pricing/risk formulas in UI.

## Tests added/updated
- Migrated all prior node:test cases in risk / nav / heatmap lib suites onto Vitest (assertions unchanged).

## Commands executed
```bash
cd frontend && npm test
cd frontend && npm run lint
cd frontend && npm run build
```

## Results
- Backend: not run (out of scope; no backend edits)
- Frontend: **70** Vitest passed; ESLint OK; Vite production build OK
- QuantLib: n/a
- C++: n/a
- Build: OK

## Known limitations / risks
- M8 ROADMAP evidence lines may still cite `risk.test.mjs` path historically; suites now live at `*.test.js`.
- Remaining M9.1 residual: broaden RTL/MSW to more panels (explicitly non-blocking).
- Older CI docs mentioning dual-run node:test + Vitest are superseded by Vitest-only `npm test`.

## Follow-up / next owner
- Owner: Frontend / QA
- Requested action: optional RTL/MSW broaden for more terminal panels
- Blocking?: no
