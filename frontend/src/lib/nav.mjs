/** Terminal main-nav section ids — display routing only; no risk math. */
export const NAV_SECTIONS = Object.freeze([
  Object.freeze({ id: 'overview', label: 'Overview', hint: 'Book status' }),
  Object.freeze({ id: 'portfolio', label: 'Portfolio', hint: 'Hierarchy & positions' }),
  Object.freeze({ id: 'risk-factors', label: 'Risk Factors', hint: 'Exposures & heatmaps' }),
  Object.freeze({ id: 'var-es', label: 'VaR & ES', hint: 'Analytics & attribution' }),
  Object.freeze({ id: 'stress', label: 'Stress', hint: 'Scenarios & reverse stress' }),
  Object.freeze({ id: 'scenario-builder', label: 'Scenario Builder', hint: 'Shocks & hedge compare' }),
  Object.freeze({ id: 'pnl-explain', label: 'P&L Explain', hint: 'Attribution' }),
  Object.freeze({ id: 'limits', label: 'Limits', hint: 'Utilization & status' }),
  Object.freeze({ id: 'risk-runs', label: 'Risk Runs', hint: 'Async run status' }),
  Object.freeze({ id: 'market-data', label: 'Market Data', hint: 'Search & history' }),
])

export const DEFAULT_SECTION_ID = NAV_SECTIONS[0].id

/** Overview first-screen compositions. Default `status` is the shipped blotter. */
export const OVERVIEW_LAYOUTS = Object.freeze([
  Object.freeze({ id: 'status', label: 'Status blotter', hint: 'Banner, KPIs, Where, map' }),
  Object.freeze({ id: 'desk', label: 'Two-pane desk', hint: 'Exceptions stay; drill docks' }),
  Object.freeze({ id: 'queue', label: 'Exception queue', hint: 'The blotter is the page' }),
  Object.freeze({ id: 'mosaic', label: 'Launchpad mosaic', hint: 'Four live monitors' }),
  Object.freeze({ id: 'command', label: 'Command GO', hint: 'Query is the control' }),
  Object.freeze({ id: 'hierarchy', label: 'Hierarchy book', hint: 'The tree is the overview' }),
  Object.freeze({ id: 'tape', label: 'Overnight tape', hint: 'Latest load, then exceptions' }),
  Object.freeze({ id: 'keys', label: 'Function keys', hint: 'F-strip into specialist teasers' }),
])

export const DEFAULT_OVERVIEW_LAYOUT = OVERVIEW_LAYOUTS[0].id

const SECTION_IDS = new Set(NAV_SECTIONS.map((s) => s.id))
const OVERVIEW_LAYOUT_IDS = new Set(OVERVIEW_LAYOUTS.map((s) => s.id))

function hashBody(hash) {
  return String(hash || '').trim().replace(/^#/, '').trim()
}

/** Section + overview layout from location hash. Unknown layout → status blotter. */
export function parseRoute(hash) {
  const raw = hashBody(hash)
  if (!raw) return { section: DEFAULT_SECTION_ID, layout: DEFAULT_OVERVIEW_LAYOUT }
  const slash = raw.indexOf('/')
  const head = slash === -1 ? raw : raw.slice(0, slash)
  const tail = slash === -1 ? '' : raw.slice(slash + 1)
  if (!SECTION_IDS.has(head)) {
    return { section: DEFAULT_SECTION_ID, layout: DEFAULT_OVERVIEW_LAYOUT }
  }
  if (head !== DEFAULT_SECTION_ID) {
    return { section: head, layout: DEFAULT_OVERVIEW_LAYOUT }
  }
  const layout = OVERVIEW_LAYOUT_IDS.has(tail) ? tail : DEFAULT_OVERVIEW_LAYOUT
  return { section: DEFAULT_SECTION_ID, layout }
}

/** Resolve active section from location hash; unknown → overview. */
export function sectionFromHash(hash) {
  return parseRoute(hash).section
}

export function overviewLayoutFromHash(hash) {
  return parseRoute(hash).layout
}

export function hashForSection(id) {
  const safe = SECTION_IDS.has(id) ? id : DEFAULT_SECTION_ID
  return `#${safe}`
}

export function hashForOverviewLayout(layout) {
  const id = OVERVIEW_LAYOUT_IDS.has(layout) ? layout : DEFAULT_OVERVIEW_LAYOUT
  return id === DEFAULT_OVERVIEW_LAYOUT ? '#overview' : `#overview/${id}`
}

export function isNavSection(id) {
  return SECTION_IDS.has(id)
}

export function navSectionById(id) {
  return NAV_SECTIONS.find((s) => s.id === id) || NAV_SECTIONS[0]
}
