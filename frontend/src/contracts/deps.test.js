import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), '../..')

describe('frontend dependency reproducibility (RF-018)', () => {
  it('package.json does not declare latest for runtime or devDependencies', () => {
    const pkg = JSON.parse(readFileSync(join(frontendRoot, 'package.json'), 'utf8'))
    const leaked = []
    for (const section of ['dependencies', 'devDependencies']) {
      for (const [name, version] of Object.entries(pkg[section] || {})) {
        if (String(version).trim() === 'latest') leaked.push(`${section}:${name}`)
      }
    }
    expect(leaked).toEqual([])
  })

  it('Dockerfile installs with npm ci, not npm install', () => {
    const text = readFileSync(join(frontendRoot, 'Dockerfile'), 'utf8')
    const runs = text
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.startsWith('RUN '))
    expect(runs.some((line) => /\bnpm ci\b/.test(line))).toBe(true)
    expect(runs.some((line) => /\bnpm install\b/.test(line))).toBe(false)
  })

  it('Dockerfile accepts VITE_API_BASE_URL for shared same-origin builds', () => {
    const text = readFileSync(join(frontendRoot, 'Dockerfile'), 'utf8')
    expect(text).toMatch(/ARG VITE_API_BASE_URL=http:\/\/localhost:8000/)
  })
})
