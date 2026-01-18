import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.{test,spec}.{js,jsx,mjs}'],
    // Lib helpers remain on node:test (see package.json test:node) until migrated.
    exclude: ['src/lib/**/*.test.mjs', 'node_modules/**', 'dist/**'],
    css: false,
  },
})
