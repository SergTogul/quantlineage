/** Display theme only — no risk math. */
export const DEFAULT_THEME = 'dark'
export const THEME_STORAGE_KEY = 'quantlineage-theme'

export function parseTheme(value) {
  return value === 'light' ? 'light' : 'dark'
}

export function toggleTheme(theme) {
  return parseTheme(theme) === 'light' ? 'dark' : 'light'
}

export function applyTheme(theme, root = globalThis.document?.documentElement) {
  const next = parseTheme(theme)
  if (!root) return next
  root.dataset.theme = next
  if (root.style) root.style.colorScheme = next
  return next
}

export function persistTheme(theme, storage = globalThis.localStorage) {
  const next = parseTheme(theme)
  try {
    storage?.setItem(THEME_STORAGE_KEY, next)
  } catch {
    /* ignore quota / private mode */
  }
  return next
}

export function readStoredTheme(storage = globalThis.localStorage) {
  try {
    return parseTheme(storage?.getItem(THEME_STORAGE_KEY))
  } catch {
    return DEFAULT_THEME
  }
}
