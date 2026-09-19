import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // Same-origin /api in dev — avoids Failed to fetch from CORS / host mismatch.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.{test,spec}.{js,jsx,mjs}'],
    // Lib helper suites (risk/nav/heatmap) migrated from node:test → Vitest (M9.1 residual).
    exclude: ['node_modules/**', 'dist/**'],
    css: false,
  },
})
