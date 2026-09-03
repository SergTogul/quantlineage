import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.{test,spec}.{js,jsx,mjs}'],
    // Lib helper suites (risk/nav/heatmap) migrated from node:test → Vitest (M9.1 residual).
    exclude: ['node_modules/**', 'dist/**'],
    css: false,
  },
})
