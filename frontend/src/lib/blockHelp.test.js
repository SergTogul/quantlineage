import { test } from 'vitest'
import assert from 'node:assert/strict'
import { BLOCK_HELP, BLOCK_HELP_IDS, getBlockHelp } from './blockHelp.mjs'

const EXPECTED_IDS = [
  'positions', 'portfolio-hierarchy', 'hierarchy-risk-heatmap', 'risk-factors',
  'rates-showcase', 'run-provenance',
  'factor-exposure-heatmap', 'var-es', 'component-var', 'es-contributions',
  'var-compare', 'risk-change-attribution', 'stress-pnl-heatmap', 'stress-tests',
  'threat-scenarios', 'reverse-stress', 'reverse-stress-multi', 'scenario-builder',
  'hedge-compare', 'risk-query', 'pnl-explain', 'limit-utilization-heatmap',
  'limits', 'risk-runs',
]

test('catalog covers every expected block id with non-empty body', () => {
  assert.deepEqual([...BLOCK_HELP_IDS].sort(), [...EXPECTED_IDS].sort())
  for (const id of EXPECTED_IDS) {
    const entry = getBlockHelp(id)
    assert.ok(entry, `missing ${id}`)
    assert.equal(typeof entry.body, 'string')
    assert.ok(entry.body.trim().length >= 40, `${id} body too short`)
    assert.ok(entry.body.trim().length <= 320, `${id} body too long`)
  }
})

test('getBlockHelp returns null for unknown id', () => {
  assert.equal(getBlockHelp('no-such-block'), null)
})

test('BLOCK_HELP is frozen', () => {
  assert.ok(Object.isFrozen(BLOCK_HELP))
})
