/**
 * Display-only heatmap color/scale helpers.
 * Maps API-returned numbers onto CSS colors — does not compute VaR, ES, or other risk.
 */

const DEFAULT_NEG = '#c45c5c'
const DEFAULT_MID = '#1a2431'
const DEFAULT_POS = '#3d9b6e'
const DEFAULT_LOW = '#151d28'
const DEFAULT_HIGH = '#c45c5c'
const DEFAULT_WARN = '#c9a227'

export function clamp(n, lo, hi) {
  const x = Number(n)
  if (!Number.isFinite(x)) return lo
  return Math.min(hi, Math.max(lo, x))
}

export function lerp(a, b, t) {
  return a + (b - a) * t
}

/** Parse #RRGGBB → {r,g,b}; invalid → mid gray. */
export function parseHex(hex) {
  const s = String(hex || '').replace('#', '')
  if (s.length !== 6) return { r: 26, g: 36, b: 49 }
  const n = Number.parseInt(s, 16)
  if (!Number.isFinite(n)) return { r: 26, g: 36, b: 49 }
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

export function rgbToHex({ r, g, b }) {
  const h = (v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, '0')
  return `#${h(r)}${h(g)}${h(b)}`
}

/** Linear blend between two #RRGGBB colors; t in [0,1]. */
export function mixHex(a, b, t) {
  const A = parseHex(a)
  const B = parseHex(b)
  const u = clamp(t, 0, 1)
  return rgbToHex({
    r: lerp(A.r, B.r, u),
    g: lerp(A.g, B.g, u),
    b: lerp(A.b, B.b, u),
  })
}

/**
 * Map value into [0, 1] given inclusive domain [min, max].
 * Flat domain → 0.5 (neutral). Display-only normalization.
 */
export function normalizeToUnit(value, min, max) {
  const v = Number(value)
  const lo = Number(min)
  const hi = Number(max)
  if (!Number.isFinite(v) || !Number.isFinite(lo) || !Number.isFinite(hi)) return 0.5
  if (hi === lo) return 0.5
  return clamp((v - lo) / (hi - lo), 0, 1)
}

/** Max |value| over a list; empty / non-finite → 0. */
export function domainMaxAbs(values) {
  let m = 0
  for (const v of values || []) {
    const n = Math.abs(Number(v))
    if (Number.isFinite(n) && n > m) m = n
  }
  return m
}

/**
 * Diverging color around zero (loss → neg, gain → pos).
 * Scale is |value| / maxAbs → [0,1] intensity; sign picks arm.
 * Documented display-only — not a risk measure.
 */
export function divergingColor(
  value,
  maxAbs,
  { neg = DEFAULT_NEG, mid = DEFAULT_MID, pos = DEFAULT_POS } = {},
) {
  const v = Number(value)
  const m = Number(maxAbs)
  if (!Number.isFinite(v) || !Number.isFinite(m) || m <= 0) return mid
  const t = clamp(Math.abs(v) / m, 0, 1)
  return mixHex(mid, v < 0 ? neg : pos, t)
}

/**
 * Sequential magnitude scale: 0 → low, maxAbs → high (hotter = larger |API value|).
 * Suitable for VaR / utilization display.
 */
export function sequentialColor(
  value,
  maxAbs,
  { low = DEFAULT_LOW, high = DEFAULT_HIGH } = {},
) {
  const v = Math.abs(Number(value))
  const m = Number(maxAbs)
  if (!Number.isFinite(v) || !Number.isFinite(m) || m <= 0) return low
  return mixHex(low, high, clamp(v / m, 0, 1))
}

/**
 * Utilization band: OK (low→mid green), WARNING band, BREACH (high red).
 * Uses API utilization_pct (0–100+) only — display mapping.
 */
export function utilizationColor(
  utilizationPct,
  { ok = DEFAULT_POS, warn = DEFAULT_WARN, breach = DEFAULT_NEG, mid = DEFAULT_MID } = {},
) {
  const u = Number(utilizationPct)
  if (!Number.isFinite(u)) return mid
  if (u >= 100) return breach
  if (u >= 80) return mixHex(warn, breach, clamp((u - 80) / 20, 0, 1))
  return mixHex(mid, ok, clamp(u / 80, 0, 1))
}

/** Relative luminance → light or dark text for contrast on cell bg. */
export function contrastText(bgHex) {
  const { r, g, b } = parseHex(bgHex)
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return lum > 0.55 ? '#0b0f14' : '#e7edf5'
}

export function cellStyle(bgHex) {
  const background = bgHex || DEFAULT_MID
  return { background, color: contrastText(background) }
}

/**
 * Flatten hierarchy nodes at selected levels with an API metric field.
 * Reads node[metric] only — no aggregation.
 */
export function hierarchyMetricCells(node, options = {}) {
  const levels = options.levels || ['desk', 'book']
  const metric = options.metric || 'var_99'
  const levelSet = new Set(levels)
  const out = []

  function walk(n, path) {
    if (!n) return
    const nextPath = path ? `${path} / ${n.name}` : n.name
    if (levelSet.has(n.level)) {
      const raw = n[metric]
      const value = Number(raw)
      out.push({
        id: n.path || nextPath,
        label: n.name,
        level: n.level,
        path: nextPath,
        metric,
        value: Number.isFinite(value) ? value : 0,
      })
    }
    for (const c of n.children || []) walk(c, nextPath)
  }

  walk(node, '')
  return out
}

/**
 * One display cell per RiskFactorExposure row (no client aggregation).
 */
export function factorExposureCells(items) {
  return (items || []).map((x, i) => {
    const exp = Number(x?.exposure)
    return {
      id: `${x?.factor ?? 'f'}:${x?.bucket ?? i}`,
      label: x?.factor || `Factor ${i + 1}`,
      factor_type: x?.factor_type ?? '',
      bucket: x?.bucket ?? '',
      value: Number.isFinite(exp) ? exp : 0,
    }
  })
}

/**
 * Factor × bucket matrix from API exposures.
 * Each cell is the API exposure for that exact (factor, bucket); missing → null.
 * Duplicate (factor, bucket) keys keep the last API row (display pick, not a risk formula).
 */
export function factorExposureMatrix(items) {
  const list = Array.isArray(items) ? items : []
  const rowSet = new Set()
  const colSet = new Set()
  const map = new Map()

  for (const x of list) {
    const row = x?.factor ?? '—'
    const col = x?.bucket ?? '—'
    rowSet.add(row)
    colSet.add(col)
    const exp = Number(x?.exposure)
    map.set(`${row}\0${col}`, {
      value: Number.isFinite(exp) ? exp : 0,
      factor_type: x?.factor_type ?? '',
    })
  }

  const rows = [...rowSet].sort()
  const cols = [...colSet].sort()
  const cells = []
  const values = []
  for (const row of rows) {
    for (const col of cols) {
      const hit = map.get(`${row}\0${col}`)
      const value = hit ? hit.value : null
      if (hit) values.push(value)
      cells.push({
        row,
        col,
        value,
        factor_type: hit?.factor_type ?? '',
        id: `${row}:${col}`,
      })
    }
  }
  return { rows, cols, cells, maxAbs: domainMaxAbs(values) }
}

/** StressResult[] → cells keyed by scenario with API pnl. */
export function stressPnlCells(items) {
  return (items || []).map((x, i) => {
    const pnl = Number(x?.pnl)
    return {
      id: x?.scenario || `stress-${i}`,
      label: x?.scenario || `Scenario ${i + 1}`,
      value: Number.isFinite(pnl) ? pnl : 0,
    }
  })
}

/** LimitResult[] → utilization cells (API utilization_pct). */
export function limitUtilizationCells(items) {
  return (items || []).map((x, i) => {
    const u = Number(x?.utilization_pct)
    return {
      id: x?.metric || `limit-${i}`,
      label: x?.metric || `Limit ${i + 1}`,
      value: Number.isFinite(u) ? u : 0,
      status: x?.status,
      breached: Boolean(x?.breached),
    }
  })
}
