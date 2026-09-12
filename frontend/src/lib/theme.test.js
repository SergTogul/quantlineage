import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  DEFAULT_THEME, THEME_STORAGE_KEY, applyTheme, parseTheme, persistTheme, readStoredTheme, toggleTheme,
} from './theme.mjs'

test('parseTheme accepts only dark and light', () => {
  assert.equal(parseTheme('light'), 'light')
  assert.equal(parseTheme('dark'), 'dark')
  assert.equal(parseTheme('nope'), 'dark')
  assert.equal(parseTheme(null), 'dark')
})

test('toggleTheme flips between the two themes', () => {
  assert.equal(toggleTheme('dark'), 'light')
  assert.equal(toggleTheme('light'), 'dark')
})

test('applyTheme writes data-theme and color-scheme on the root', () => {
  const root = { dataset: {}, style: {} }
  assert.equal(applyTheme('light', root), 'light')
  assert.equal(root.dataset.theme, 'light')
  assert.equal(root.style.colorScheme, 'light')
})

test('action buttons stay light in both themes', async () => {
  const { readFile } = await import('node:fs/promises')
  const { dirname, join } = await import('node:path')
  const { fileURLToPath } = await import('node:url')
  const css = await readFile(join(dirname(fileURLToPath(import.meta.url)), '../styles.css'), 'utf8')
  const block = (selector) => {
    const match = css.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\{([^}]+)\\}`))
    assert.ok(match, `missing ${selector}`)
    return match[1]
  }
  const token = (src, name) => {
    const match = src.match(new RegExp(`--${name}:([^;]+)`))
    assert.ok(match, `missing --${name}`)
    return match[1]
  }
  const dark = block(':root,html[data-theme="dark"]')
  const light = block('html[data-theme="light"]')
  assert.equal(token(dark, 'btn'), '#e8e8e8')
  assert.equal(token(dark, 'on-btn'), '#050505')
  assert.equal(token(light, 'btn'), '#ffffff')
  assert.equal(token(light, 'on-btn'), '#161616')
  assert.notEqual(token(light, 'btn'), token(light, 'text'))
  assert.equal(token(light, 'threat-severe-bg'), '#f8e4e4')
  assert.notEqual(token(light, 'threat-severe-bg'), token(dark, 'threat-severe-bg'))
})

test('readStoredTheme and persistTheme round-trip through storage', () => {
  const storage = new Map()
  const fake = {
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => { storage.set(k, v) },
  }
  assert.equal(readStoredTheme(fake), DEFAULT_THEME)
  persistTheme('light', fake)
  assert.equal(fake.getItem(THEME_STORAGE_KEY), 'light')
  assert.equal(readStoredTheme(fake), 'light')
})
