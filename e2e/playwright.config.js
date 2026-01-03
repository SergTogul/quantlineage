const { defineConfig, devices } = require('@playwright/test')
const path = require('node:path')

const root = path.resolve(__dirname, '..')
const backend = path.join(root, 'backend')
const frontend = path.join(root, 'frontend')
const uvicorn = path.join(backend, '.venv', 'bin', 'uvicorn')

module.exports = defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  // Bundled Chromium is unavailable on macOS 13; use the installed Google Chrome channel.
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chrome' } }],
  webServer: [
    {
      command: `"${uvicorn}" app.main:app --host 127.0.0.1 --port 8000`,
      cwd: backend,
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        PYTHONPATH: backend,
        RISKFORGE_PRICING_ENGINE: 'builtin',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
      cwd: frontend,
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_BASE_URL: 'http://127.0.0.1:8000',
      },
    },
  ],
})
