import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { BLOCK_HELP_IDS } from './blockHelp.mjs'

const EXPECTED_IDS = [
  'positions', 'portfolio-hierarchy', 'hierarchy-risk-heatmap', 'risk-factors',
  'rates-showcase', 'run-provenance',
  'factor-exposure-heatmap', 'var-es', 'component-var', 'es-contributions',
  'var-compare', 'risk-change-attribution', 'stress-pnl-heatmap', 'stress-tests',
  'threat-scenarios', 'reverse-stress', 'reverse-stress-multi', 'scenario-builder',
  'hedge-compare', 'risk-query', 'pnl-explain', 'limit-utilization-heatmap',
  'limits', 'risk-runs',
]

const WIRED_FILES = [
  '../App.jsx',
  '../components/Heatmaps.jsx',
  '../components/RiskTable.jsx',
  '../components/ScenarioBuilder.jsx',
  '../components/Analytics.jsx',
]

const HELP_TAG = /<BlockHelp\s+id="([^"]+)"\s*\/>/g

test('every catalog id is wired as <BlockHelp id="…" /> on analysis cards', () => {
  const dir = dirname(fileURLToPath(import.meta.url))
  const found = []
  for (const rel of WIRED_FILES) {
    const text = readFileSync(join(dir, rel), 'utf8')
    const matches = [...text.matchAll(HELP_TAG)]
    assert.equal((text.match(/<BlockHelp\b/g) || []).length, matches.length, `${rel}: cards must pass only id`)
    for (const match of matches) {
      found.push({ id: match[1], file: rel })
    }
  }
  const wired = [...new Set(found.map((x) => x.id))].sort()
  assert.deepEqual(wired, [...EXPECTED_IDS].sort())
  assert.deepEqual([...BLOCK_HELP_IDS].sort(), [...EXPECTED_IDS].sort())
  for (const id of EXPECTED_IDS) {
    assert.ok(found.some((x) => x.id === id), `missing <BlockHelp id="${id}" />`)
  }
})
