const { defineConfig, devices } = require('@playwright/test')
const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '..')
const backend = path.join(root, 'backend')
const frontend = path.join(root, 'frontend')
const venvUvicorn = path.join(backend, '.venv', 'bin', 'uvicorn')
const isCI = !!process.env.CI

// Local macOS often needs the installed Google Chrome channel (bundled Chromium
// can be unavailable on older hosts). GHA ubuntu-latest uses Playwright Chromium.
const useChromeChannel = !isCI && process.env.PLAYWRIGHT_USE_CHROMIUM !== '1'

function backendServerCommand() {
  if (process.env.QUANTLINEAGE_E2E_UVICORN) {
    return `${process.env.QUANTLINEAGE_E2E_UVICORN} app.main:app --host 127.0.0.1 --port 8000`
  }
  if (fs.existsSync(venvUvicorn)) {
    return `"${venvUvicorn}" app.main:app --host 127.0.0.1 --port 8000`
  }
  // CI / hosts without backend/.venv: uvicorn must be on PATH (pip install).
  return 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000'
}

module.exports = defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(useChromeChannel ? { channel: 'chrome' } : {}),
      },
    },
  ],
  webServer: [
    {
      command: backendServerCommand(),
      cwd: backend,
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        ...process.env,
        PYTHONPATH: backend,
        // PR e2e stays builtin. Nightly QuantLib E2E sets QUANTLINEAGE_PRICING_ENGINE=quantlib.
        QUANTLINEAGE_PRICING_ENGINE: process.env.QUANTLINEAGE_PRICING_ENGINE || 'builtin',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
      cwd: frontend,
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_BASE_URL: 'http://127.0.0.1:8000',
      },
    },
  ],
})
