# RiskForge Playwright E2E

Critical-path UI tests against a live FastAPI backend (`builtin` pricing) and Vite frontend.

## Prerequisites

- Backend venv at `backend/.venv` with requirements installed
- Frontend deps: `cd frontend && npm install`

## Run

```bash
cd e2e
npm install
npm run install:browsers   # registers Google Chrome channel (needed on macOS 13+)
npm test
```

Requires Google Chrome installed. Playwright starts uvicorn (`:8000`) and Vite (`:5173`) automatically unless those ports are already in use.
