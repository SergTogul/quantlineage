import test from 'node:test'
import assert from 'node:assert/strict'
import {
  NAV_SECTIONS, DEFAULT_SECTION_ID, sectionFromHash, hashForSection, isNavSection, navSectionById,
} from './nav.mjs'

test('NAV_SECTIONS covers terminal target areas in order', () => {
  assert.deepEqual(NAV_SECTIONS.map((s) => s.id), [
    'overview', 'portfolio', 'risk-factors', 'var-es', 'stress',
    'scenario-builder', 'pnl-explain', 'limits', 'risk-runs',
  ])
  assert.equal(DEFAULT_SECTION_ID, 'overview')
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
