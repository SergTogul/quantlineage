# QuantLineage Playwright E2E

Critical-path UI tests against a live FastAPI backend (`builtin` pricing) and Vite frontend.

## Prerequisites

- Backend venv at `backend/.venv` with requirements installed (or `uvicorn` on `PATH`)
- Frontend deps: `cd frontend && npm install`

## Run (local)

```bash
cd e2e
npm install
npm run install:browsers # Google Chrome channel (needed on macOS 13+)
npm test
```

Requires Google Chrome installed locally. Playwright starts uvicorn (`:8000`) and Vite (`:5173`) automatically unless those ports are already in use.

Optional: `PLAYWRIGHT_USE_CHROMIUM=1` forces bundled Chromium instead of the Chrome channel. `QUANTLINEAGE_E2E_UVICORN` overrides the backend command (default: `backend/.venv/bin/uvicorn` if present, else `python -m uvicorn`).

## CI (GitHub Actions)

Job `e2e-playwright` in `.github/workflows/ci.yml` sets `CI=true`, installs Chromium via `npm run install:browsers:ci`, and runs the same suite against builtin pricing.

Stage 10.4 golden demo journey: `e2e/tests/golden-demo.spec.ts` (script: `docs/demo_script.md`).

