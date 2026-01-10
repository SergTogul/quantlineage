/** Terminal main-nav section ids — display routing only; no risk math. */
export const NAV_SECTIONS = Object.freeze([
  Object.freeze({ id: 'overview', label: 'Overview', hint: 'Key metrics' }),
  Object.freeze({ id: 'portfolio', label: 'Portfolio', hint: 'Hierarchy & positions' }),
  Object.freeze({ id: 'risk-factors', label: 'Risk Factors', hint: 'Factor exposures' }),
  Object.freeze({ id: 'var-es', label: 'VaR & ES', hint: 'Analytics & attribution' }),
  Object.freeze({ id: 'stress', label: 'Stress', hint: 'Scenarios & reverse stress' }),
  Object.freeze({ id: 'scenario-builder', label: 'Scenario Builder', hint: 'Shocks & hedge compare' }),
  Object.freeze({ id: 'pnl-explain', label: 'P&L Explain', hint: 'Attribution' }),
  Object.freeze({ id: 'limits', label: 'Limits', hint: 'Utilization & status' }),
  Object.freeze({ id: 'risk-runs', label: 'Risk Runs', hint: 'Async run status' }),
])

export const DEFAULT_SECTION_ID = NAV_SECTIONS[0].id

const SECTION_IDS = new Set(NAV_SECTIONS.map((s) => s.id))

/** Resolve active section from location hash; unknown → overview. */
export function sectionFromHash(hash) {
  const raw = String(hash || '').trim().replace(/^#/, '').trim()
  if (!raw) return DEFAULT_SECTION_ID
  return SECTION_IDS.has(raw) ? raw : DEFAULT_SECTION_ID
}

export function hashForSection(id) {
  const safe = SECTION_IDS.has(id) ? id : DEFAULT_SECTION_ID
  return `#${safe}`
}

export function isNavSection(id) {
  return SECTION_IDS.has(id)
}

export function navSectionById(id) {
  return NAV_SECTIONS.find((s) => s.id === id) || NAV_SECTIONS[0]
}
