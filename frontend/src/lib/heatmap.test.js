import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  clamp, lerp, parseHex, mixHex, normalizeToUnit, domainMaxAbs,
  divergingColor, sequentialColor, utilizationColor, contrastText, cellStyle,
  hierarchyMetricCells, factorExposureCells, factorExposureMatrix,
  stressPnlCells, limitUtilizationCells,
} from './heatmap.mjs'

test('clamp / lerp / normalize are display-only bounds', () => {
  assert.equal(clamp(5, 0, 3), 3)
  assert.equal(clamp(-1, 0, 3), 0)
  assert.equal(lerp(0, 10, 0.5), 5)
  assert.equal(normalizeToUnit(5, 0, 10), 0.5)
  assert.equal(normalizeToUnit(0, 0, 0), 0.5)
})

test('mixHex blends endpoints', () => {
  assert.equal(mixHex('#000000', '#ffffff', 0), '#000000')
  assert.equal(mixHex('#000000', '#ffffff', 1), '#ffffff')
  assert.equal(mixHex('#000000', '#ffffff', 0.5), '#808080')
})

test('domainMaxAbs ignores non-finite', () => {
  assert.equal(domainMaxAbs([-3, 2, NaN, null]), 3)
  assert.equal(domainMaxAbs([]), 0)
})

test('divergingColor is mid at zero and arms by sign', () => {
  const mid = divergingColor(0, 100)
  const neg = divergingColor(-100, 100)
  const pos = divergingColor(100, 100)
  assert.equal(mid, '#1a2431')
  assert.notEqual(neg, mid)
  assert.notEqual(pos, mid)
  assert.notEqual(neg, pos)
  assert.equal(divergingColor(50, 0), '#1a2431')
})

test('sequentialColor scales magnitude toward high', () => {
  const low = sequentialColor(0, 100)
  const high = sequentialColor(100, 100)
  const mid = sequentialColor(50, 100)
  assert.equal(low, '#151d28')
  assert.equal(high, '#c45c5c')
  assert.notEqual(mid, low)
  assert.notEqual(mid, high)
})

test('utilizationColor bands OK / warn / breach', () => {
  const ok = utilizationColor(40)
  const warn = utilizationColor(85)
  const breach = utilizationColor(120)
  assert.notEqual(ok, warn)
  assert.notEqual(warn, breach)
  assert.equal(utilizationColor(100), '#c45c5c')
})

test('contrastText picks light on dark bg', () => {
  assert.equal(contrastText('#0b0f14'), '#e7edf5')
  assert.equal(contrastText('#f5f5f5'), '#0b0f14')
  assert.equal(cellStyle('#0b0f14').color, '#e7edf5')
})

test('hierarchyMetricCells reads API metric at levels only', () => {
  const tree = {
    name: 'Firm',
    level: 'firm',
    var_99: 200,
    children: [{
      name: 'Port',
      level: 'portfolio',
      var_99: 200,
      children: [
        { name: 'Desk A', level: 'desk', var_99: 80, children: [
          { name: 'Book A', level: 'book', var_99: 80, children: [] },
        ] },
        { name: 'Desk B', level: 'desk', var_99: 120, children: [] },
      ],
    }],
  }
  const desks = hierarchyMetricCells(tree, { levels: ['desk'], metric: 'var_99' })
  assert.equal(desks.length, 2)
  assert.deepEqual(desks.map((c) => c.value).sort((a, b) => a - b), [80, 120])
  assert.equal(desks[0].metric, 'var_99')
  const books = hierarchyMetricCells(tree, { levels: ['book'], metric: 'var_99' })
  assert.equal(books.length, 1)
  assert.equal(books[0].label, 'Book A')
})

test('factorExposureCells are 1:1 with API rows', () => {
  const cells = factorExposureCells([
    { factor: 'SPY', factor_type: 'equity', bucket: 'spot', exposure: -10 },
    { factor: 'USD', factor_type: 'fx', bucket: 'spot', exposure: 5 },
  ])
  assert.equal(cells.length, 2)
  assert.equal(cells[0].value, -10)
  assert.equal(cells[1].label, 'USD')
})

test('factorExposureMatrix does not invent exposures for empty cells', () => {
  const m = factorExposureMatrix([
    { factor: 'SPY', factor_type: 'equity', bucket: 'spot', exposure: 12 },
    { factor: 'VIX', factor_type: 'vol', bucket: '1m', exposure: -3 },
  ])
  assert.deepEqual(m.rows, ['SPY', 'VIX'])
  assert.deepEqual(m.cols, ['1m', 'spot'])
  assert.equal(m.maxAbs, 12)
  const spySpot = m.cells.find((c) => c.row === 'SPY' && c.col === 'spot')
  const spy1m = m.cells.find((c) => c.row === 'SPY' && c.col === '1m')
  assert.equal(spySpot.value, 12)
  assert.equal(spy1m.value, null)
})

test('stressPnlCells and limitUtilizationCells map API fields', () => {
  assert.deepEqual(stressPnlCells([{ scenario: 'Crash', pnl: -9 }]), [
    { id: 'Crash', label: 'Crash', value: -9 },
  ])
  assert.equal(limitUtilizationCells([{ metric: 'var_99', utilization_pct: 88 }])[0].value, 88)
})

test('parseHex tolerates bad input', () => {
  assert.deepEqual(parseHex('nope'), { r: 26, g: 36, b: 49 })
})
