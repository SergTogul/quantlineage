import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  NAV_SECTIONS, DEFAULT_SECTION_ID, DEFAULT_OVERVIEW_LAYOUT, OVERVIEW_LAYOUTS,
  sectionFromHash, hashForSection, isNavSection, navSectionById,
  parseRoute, hashForOverviewLayout, overviewLayoutFromHash,
} from './nav.mjs'

test('NAV_SECTIONS covers terminal target areas in order', () => {
  assert.deepEqual(NAV_SECTIONS.map((s) => s.id), [
    'overview', 'portfolio', 'risk-factors', 'var-es', 'historical-analytics', 'stress',
    'scenario-builder', 'pnl-explain', 'limits', 'risk-runs', 'market-data',
  ])
  assert.equal(DEFAULT_SECTION_ID, 'overview')
  assert.equal(navSectionById('historical-analytics').label, 'Historical')
  assert.equal(navSectionById('historical-analytics').hint, 'Wealth, drawdown, SPY')
  assert.equal(navSectionById('market-data').label, 'Market Data')
  assert.equal(navSectionById('market-data').hint, 'Search & history')
  for (const s of NAV_SECTIONS) {
    assert.ok(s.label)
    assert.ok(s.hint)
  }
})

test('sectionFromHash defaults empty and unknown to overview', () => {
  assert.equal(sectionFromHash(''), 'overview')
  assert.equal(sectionFromHash('#'), 'overview')
  assert.equal(sectionFromHash('#bogus'), 'overview')
  assert.equal(sectionFromHash(undefined), 'overview')
})

test('sectionFromHash accepts known ids with or without hash prefix', () => {
  assert.equal(sectionFromHash('#stress'), 'stress')
  assert.equal(sectionFromHash('risk-runs'), 'risk-runs')
  assert.equal(sectionFromHash('#market-data'), 'market-data')
  assert.equal(sectionFromHash('  #limits  '), 'limits')
})

test('hashForSection builds hash and clamps unknown', () => {
  assert.equal(hashForSection('var-es'), '#var-es')
  assert.equal(hashForSection('nope'), '#overview')
})

test('isNavSection and navSectionById', () => {
  assert.equal(isNavSection('portfolio'), true)
  assert.equal(isNavSection('heatmap'), false)
  assert.equal(navSectionById('limits').label, 'Limits')
  assert.equal(navSectionById('missing').id, 'overview')
})

test('OVERVIEW_LAYOUTS are eight named compositions', () => {
  assert.deepEqual(OVERVIEW_LAYOUTS.map((s) => s.id), [
    'status', 'desk', 'queue', 'mosaic', 'command', 'hierarchy', 'tape', 'keys',
  ])
  assert.equal(DEFAULT_OVERVIEW_LAYOUT, 'status')
})

test('parseRoute keeps #overview as the shipped status blotter', () => {
  assert.deepEqual(parseRoute('#overview'), { section: 'overview', layout: 'status' })
  assert.deepEqual(parseRoute(''), { section: 'overview', layout: 'status' })
  assert.equal(sectionFromHash('#overview/desk'), 'overview')
})

test('parseRoute reads overview layout from the hash path', () => {
  assert.deepEqual(parseRoute('#overview/desk'), { section: 'overview', layout: 'desk' })
  assert.deepEqual(parseRoute('#overview/nope'), { section: 'overview', layout: 'status' })
  assert.deepEqual(parseRoute('#limits'), { section: 'limits', layout: 'status' })
})

test('hashForOverviewLayout and overviewLayoutFromHash round-trip', () => {
  assert.equal(hashForOverviewLayout('status'), '#overview')
  assert.equal(hashForOverviewLayout('tape'), '#overview/tape')
  assert.equal(hashForOverviewLayout('bogus'), '#overview')
  assert.equal(overviewLayoutFromHash('#overview/mosaic'), 'mosaic')
  assert.equal(overviewLayoutFromHash('#var-es'), 'status')
})
