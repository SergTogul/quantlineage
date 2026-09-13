import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'vitest'
import assert from 'node:assert/strict'
import { contributionBarPct, contributionBarRows, keyRateDv01Chart } from './riskVisuals.mjs'

const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'riskVisuals.mjs'), 'utf8')

test('presentation helpers do not contain risk math or KR sums', () => {
  assert.doesNotMatch(src, /bps_to_decimal|0\.0001/)
  assert.doesNotMatch(src, /1\.645|1\.96|Math\.sqrt/)
  assert.doesNotMatch(src, /key_rate_dv01[\s\S]{0,120}\.reduce|key_rate_dv01\s*\+/)
})

test('contributionBarPct scales |API amount| against maxAbs', () => {
  assert.equal(contributionBarPct(80, 100), 80)
  assert.equal(contributionBarPct(-50, 100), 50)
  assert.equal(contributionBarPct(10, 0), 0)
  assert.equal(contributionBarPct(Number.NaN, 10), 0)
})

test('contributionBarRows pass through API amounts and percents without recomputing them', () => {
  const rows = contributionBarRows([
    { position_id: 'a', label: 'EQ-1', risk_amount: 80, contribution_pct: 62.5 },
    { position_id: 'b', label: 'EQ-2', risk_amount: -40, contribution_pct: 31.25 },
  ])
  assert.equal(rows.length, 2)
  assert.equal(rows[0].risk_amount, 80)
  assert.equal(rows[0].contribution_pct, 62.5)
  assert.equal(rows[0].barPct, 100)
  assert.equal(rows[1].barPct, 50)
  assert.equal(rows[1].contribution_pct, 31.25)
})

test('keyRateDv01Chart maps each tenor independently and does not sum KR values', () => {
  const chart = keyRateDv01Chart([
    { tenor: '2Y', value: -200, unit: 'per_bp' },
    { tenor: '5Y', value: -400, unit: 'per_bp' },
    { tenor: '10Y', value: -100, unit: 'per_bp' },
  ])
  assert.equal(chart.rows.length, 3)
  assert.equal(chart.rows[0].value, -200)
  assert.equal(chart.rows[1].barPct, 100)
  assert.equal(chart.rows[2].barPct, 25)
  assert.equal(chart.maxAbs, 400)
  const summed = chart.rows.reduce((n, r) => n + r.value, 0)
  assert.notEqual(summed, chart.maxAbs)
  assert.equal(keyRateDv01Chart(null).rows.length, 0)
})
