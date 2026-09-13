import { displayBpsToDecimal, displayPercentToFraction } from '../contracts/wireUnits.js'

export function money(value) {
  const sign = value < 0 ? '-' : ''; const n = Math.abs(value)
  if (n >= 1_000_000) return `${sign}$${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${sign}$${(n / 1_000).toFixed(1)}K`
  return `${sign}$${n.toFixed(0)}`
}
export function topContributors(items, count = 5) {
  return [...items].sort((a, b) => Math.abs(b.risk_amount) - Math.abs(a.risk_amount)).slice(0, count)
}
export function worstStress(items) { return items.length ? items.reduce((w,c)=>c.pnl<w.pnl?c:w) : null }
/**
 * Prefer API ``LimitResult.status`` (OK / WARNING / BREACH). Fallback maps
 * utilization / breached when status is absent (legacy payloads).
 */
export function limitStatus(item) {
  const s = item?.status
  if (s === 'OK' || s === 'WARNING' || s === 'BREACH') return s
  if (item?.breached) return 'BREACH'
  if ((item?.utilization_pct ?? 0) >= 80) return 'WARNING'
  return 'OK'
}

/** CSS modifier for limit status (WARNING → warn to match existing styles). */
export function limitStatusClass(item) {
  const s = limitStatus(item)
  return s === 'WARNING' ? 'warn' : s.toLowerCase()
}
export function threatClass(level) { return String(level||'LOW').toLowerCase() }
export function percent(value,digits=1){ return `${(value*100).toFixed(digits)}%` }
export function stressSummary(report){ if(!report||!report.evaluations?.length)return{worst:null,severe:0,breaches:0}; return{worst:report.evaluations[0],severe:report.severe_count,breaches:report.breach_count} }
export function topFactors(items,count=8){ return [...items].sort((a,b)=>Math.abs(b.exposure)-Math.abs(a.exposure)).slice(0,count) }
export function varMethod(report,method){ return report?.methods?.find(x=>x.method===method)||null }
/** Count nodes at a given hierarchy level (display only — no risk math). */
export function hierarchyCountByLevel(node, level) {
  if (!node) return 0
  if (node.level === level) return 1
  return (node.children || []).reduce((n, x) => n + hierarchyCountByLevel(x, level), 0)
}
export function hierarchyTradeCount(node) { return hierarchyCountByLevel(node, 'trade') }

/** Firm root → first portfolio child; portfolio root returns itself. */
export function hierarchyPortfolio(node) {
  if (!node) return null
  if (node.level === 'portfolio') return node
  if (node.level === 'firm') {
    return (node.children || []).find((c) => c.level === 'portfolio') || node.children?.[0] || null
  }
  return null
}

/**
 * Display summary for Hierarchy card. Walks Firm→Portfolio→… and reads API metrics
 * from the root node only (no client-side aggregation).
 */
export function hierarchySummary(node) {
  if (!node) return null
  const portfolio = hierarchyPortfolio(node)
  const scope = portfolio || node
  return {
    firmName: node.level === 'firm' ? node.name : null,
    portfolioName: portfolio?.name ?? null,
    rootName: node.name,
    rootLevel: node.level,
    desks: hierarchyCountByLevel(scope, 'desk'),
    strategies: hierarchyCountByLevel(scope, 'strategy'),
    books: hierarchyCountByLevel(scope, 'book'),
    trades: hierarchyTradeCount(node),
    market_value: node.market_value,
    var_95: node.var_95,
    var_99: node.var_99,
    expected_shortfall_99: node.expected_shortfall_99,
    delta: node.delta,
    gamma: node.gamma,
    vega: node.vega,
    dv01: node.dv01,
    fx_delta: node.fx_delta,
  }
}

/**
 * Resolve a node by child-index path from the root (display navigation only).
 * pathIndices = [0, 1] → root.children[0].children[1].
 */
export function hierarchyNodeAtPath(root, pathIndices = []) {
  if (!root) return null
  let node = root
  const trail = [root]
  const resolved = []
  for (const i of pathIndices) {
    const kids = node.children || []
    const idx = Number(i)
    if (!Number.isInteger(idx) || idx < 0 || idx >= kids.length) break
    node = kids[idx]
    trail.push(node)
    resolved.push(idx)
  }
  return { node, trail, pathIndices: resolved }
}

/** Child rows for hierarchy drill table — API fields only. */
export function hierarchyChildRows(node) {
  return (node?.children || []).map((c, index) => ({
    index,
    name: c.name,
    level: c.level,
    path: c.path || '',
    market_value: c.market_value,
    var_99: c.var_99,
    expected_shortfall_99: c.expected_shortfall_99,
    child_count: (c.children || []).length,
  }))
}

/** Selected-node metrics strip for drill-down (no aggregation). */
export function hierarchyNodeMetrics(node) {
  if (!node) return null
  return {
    name: node.name,
    level: node.level,
    path: node.path || '',
    market_value: node.market_value,
    var_95: node.var_95,
    var_99: node.var_99,
    expected_shortfall_99: node.expected_shortfall_99,
    delta: node.delta,
    gamma: node.gamma,
    vega: node.vega,
    dv01: node.dv01,
    fx_delta: node.fx_delta,
    stress: node.stress || [],
    limits: node.limits || [],
    child_count: (node.children || []).length,
  }
}

/** Normalize HedgeComparisonReport (object). Legacy list → scenarios-only shim. */
export function hedgeComparisonSummary(report) {
  if (!report) return null
  if (Array.isArray(report)) {
    return {
      hedge_cost: null,
      var_improvement: null,
      es_improvement: null,
      base_var_99: null,
      hedged_var_99: null,
      base_expected_shortfall_99: null,
      hedged_expected_shortfall_99: null,
      methodology: null,
      scenarios: report,
      factor_exposure_changes: [],
    }
  }
  return {
    hedge_cost: report.hedge_cost,
    var_improvement: report.var_improvement,
    es_improvement: report.es_improvement,
    base_var_99: report.base_var_99,
    hedged_var_99: report.hedged_var_99,
    base_expected_shortfall_99: report.base_expected_shortfall_99,
    hedged_expected_shortfall_99: report.hedged_expected_shortfall_99,
    methodology: report.methodology ?? null,
    scenarios: report.scenarios || [],
    factor_exposure_changes: report.factor_exposure_changes || [],
  }
}

/**
 * Request helper: clone portfolio with SPY equity quantity set to 0 (flat hedge demo).
 * Does not compute risk — only builds the hedged_portfolio body for compare API.
 */
export function spyFlatHedgePortfolio(portfolio) {
  if (!portfolio) return null
  const positions = (portfolio.positions || []).map((p) => {
    if (p?.symbol === 'SPY' && p?.type === 'equity') {
      return { ...p, quantity: 0 }
    }
    return { ...p }
  })
  return { ...portfolio, positions }
}

/** Default stress scenarios for hedge-compare UI (formal ScenarioWire only). */
export function defaultHedgeScenarios(portfolio) {
  const { equities } = stressFactorKeysFromPortfolio(portfolio)
  const shocks = []
  for (const sym of equities) {
    shocks.push({
      factor_type: 'equity',
      key: sym,
      amount: -0.2,
      bucket: sym,
    })
  }
  return [
    {
      id: 'Crash',
      name: 'Crash',
      category: 'factor',
      shocks,
    },
  ]
}

/** Thin display parse for MultiFactorReverseStressResult (API fields only). */
export function reverseStressMultiSummary(result) {
  if (!result) return null
  return {
    converged: !!result.converged,
    target_loss_pct: result.target_loss_pct,
    target_loss: result.target_loss,
    achieved_loss_pct: result.achieved_loss_pct,
    pnl: result.pnl,
    base_market_value: result.base_market_value,
    objective_l2: result.objective_l2 ?? null,
    shocks: result.shocks || [],
    factors: result.factors || [],
    method: result.method ?? null,
    iterations: result.iterations ?? 0,
    message: result.message ?? null,
    assumptions: result.assumptions || [],
  }
}

/** Factor families accepted by POST /risk/stress/reverse/multi. */
export const REVERSE_MULTI_FACTORS = Object.freeze(['equity', 'rates', 'vol', 'fx'])

/** Default multi-factor reverse form (display units: loss %, max shock %). */
export function defaultReverseMultiForm() {
  return {
    target_loss_pct: 5,
    max_shock: 80,
    factors: { equity: true, rates: false, vol: true, fx: false },
    weights: { equity: '', rates: '', vol: '', fx: '' },
  }
}

/** Selected factor ids from the multi-factor reverse form. */
export function selectedReverseMultiFactors(form) {
  return REVERSE_MULTI_FACTORS.filter((f) => !!form?.factors?.[f])
}

/**
 * Validate multi-factor reverse form before API call (display checks only).
 * Requires ≥2 factors so the panel matches the multi-factor endpoint intent.
 */
export function validateReverseMultiForm(form) {
  const factors = selectedReverseMultiFactors(form)
  if (factors.length < 2) {
    return { ok: false, error: 'Select at least two factors' }
  }
  const target = Number(form?.target_loss_pct)
  if (!Number.isFinite(target) || target <= 0) {
    return { ok: false, error: 'Target loss % must be > 0' }
  }
  const maxShock = Number(form?.max_shock)
  if (!Number.isFinite(maxShock) || maxShock <= 0) {
    return { ok: false, error: 'Max shock % must be > 0' }
  }
  const anyWeight = factors.some((f) => String(form?.weights?.[f] ?? '').trim() !== '')
  if (anyWeight) {
    for (const f of factors) {
      const w = Number(form?.weights?.[f])
      if (!Number.isFinite(w) || w <= 0) {
        return { ok: false, error: `Weight for ${f} must be > 0` }
      }
    }
  }
  return { ok: true, error: null }
}

/**
 * Build reverseStressMulti options from the form (request body helpers only).
 * target_loss_pct is returned as a fraction for the API.
 */
export function reverseMultiRequestBody(form) {
  const factors = selectedReverseMultiFactors(form)
  const body = {
    target_loss_pct: displayPercentToFraction(form.target_loss_pct),
    factors,
    max_shock: displayPercentToFraction(form.max_shock),
  }
  const anyWeight = factors.some((f) => String(form?.weights?.[f] ?? '').trim() !== '')
  if (anyWeight) {
    body.weights = Object.fromEntries(
      factors.map((f) => [f, Number(form.weights[f])]),
    )
  }
  return body
}

/** Format a FactorShockSolution for display (wire unit from API). */
export function formatFactorShock(shock) {
  if (!shock || shock.required_shock == null) return '—'
  if (shock.shock_unit === 'bp') {
    return `${Number(shock.required_shock).toFixed(0)} bp`
  }
  return percent(shock.required_shock)
}

/**
 * Display parse for P&L Explain (AttributionReport). Passes API driver labels
 * through unchanged — no client-side risk math or label remapping.
 * M4.3 drivers: Delta, Gamma, Vega, Rates, FX, Theta, New trades, Closed trades.
 */
export function attributionSummary(report) {
  if (!report) return null
  return {
    base_market_value: report.base_market_value,
    current_market_value: report.current_market_value,
    total_change: report.total_change,
    explained_change: report.explained_change,
    residual: report.residual,
    items: report.items || [],
    drivers: (report.items || []).map((x) => x.driver),
  }
}

/** Limits rows flagged breached (display filter — no risk math). */
export function breachedLimits(items) {
  return (items || []).filter((x) => x.breached)
}

/**
 * Display parse for LimitDrilldownReport. Passes API fields through;
 * counts breaches from the `breached` flag only (no client risk math).
 */
export function limitDrilldownSummary(report) {
  if (!report) return null
  const items = report.items || []
  return {
    portfolio_id: report.portfolio_id,
    hierarchy_node: report.hierarchy_node,
    hierarchy_level: report.hierarchy_level,
    items,
    breach_count: items.filter((x) => x.breached).length,
  }
}

/**
 * Demo / fallback factor keys matching canned global-macro market expansion
 * (NVDA/SPY equity+vol, EURUSD FX+vol, USD/EUR parallel rates).
 * Used when portfolio is absent so ScenarioWire still expands like legacy scalars.
 */
export const DEMO_STRESS_FACTOR_KEYS = Object.freeze({
  equities: Object.freeze(['NVDA', 'SPY']),
  fxPairs: Object.freeze(['EURUSD']),
  rateCcys: Object.freeze(['EUR', 'USD']),
})

const EQUITY_POS_TYPES = new Set(['equity', 'european_option', 'equity_future'])
const FX_POS_TYPES = new Set(['fx_forward', 'fx_option'])
const RATE_POS_TYPES = new Set(['bond', 'swap'])

/**
 * Derive stress expansion keys from portfolio positions (display/request only).
 * FX pairs also contribute inferred currency codes for parallel rate shocks.
 */
export function stressFactorKeysFromPortfolio(portfolio) {
  const equities = new Set()
  const fxPairs = new Set()
  const rateCcys = new Set()
  for (const pos of portfolio?.positions || []) {
    const type = pos?.type
    if (EQUITY_POS_TYPES.has(type) && pos.symbol) equities.add(pos.symbol)
    if (FX_POS_TYPES.has(type) && pos.pair) {
      fxPairs.add(pos.pair)
      if (typeof pos.pair === 'string' && pos.pair.length === 6) {
        rateCcys.add(pos.pair.slice(0, 3))
        rateCcys.add(pos.pair.slice(3, 6))
      }
    }
    if (RATE_POS_TYPES.has(type) && pos.currency) rateCcys.add(pos.currency)
  }
  if (!equities.size && !fxPairs.size && !rateCcys.size) {
    return {
      equities: [...DEMO_STRESS_FACTOR_KEYS.equities],
      fxPairs: [...DEMO_STRESS_FACTOR_KEYS.fxPairs],
      rateCcys: [...DEMO_STRESS_FACTOR_KEYS.rateCcys],
    }
  }
  return {
    equities: [...equities].sort(),
    fxPairs: [...fxPairs].sort(),
    rateCcys: [...rateCcys].sort(),
  }
}

/**
 * Display % / bp → formal ScenarioWire (MarketSnapshot.bump units).
 * Equity/FX/vol: fraction; rates: absolute decimal (100 bp → 0.01).
 * Expands family shocks onto portfolio (or demo) factor keys for legacy parity.
 */
export function scenarioPayload(form, portfolio) {
  const equityFrac = displayPercentToFraction(form.equity)
  const volFrac = displayPercentToFraction(form.vol)
  const ratesAmt = displayBpsToDecimal(form.rates)
  const fxFrac = displayPercentToFraction(form.fx)
  const { equities, fxPairs, rateCcys } = stressFactorKeysFromPortfolio(portfolio)
  const shocks = []
  for (const sym of equities) {
    if (equityFrac) {
      shocks.push({
        factor_type: 'equity',
        key: sym,
        amount: equityFrac,
        bucket: sym,
      })
    }
    if (volFrac) {
      shocks.push({
        factor_type: 'vol',
        key: `${sym}:VOL`,
        amount: volFrac,
        bucket: sym,
        expiry: 'GENERIC',
        moneyness: 'ATM',
      })
    }
  }
  for (const pair of fxPairs) {
    if (fxFrac) {
      shocks.push({
        factor_type: 'fx',
        key: pair,
        amount: fxFrac,
        bucket: pair,
      })
    }
    if (volFrac) {
      shocks.push({
        factor_type: 'vol',
        key: `${pair}:VOL`,
        amount: volFrac,
        bucket: pair,
        expiry: 'GENERIC',
        moneyness: 'ATM',
      })
    }
  }
  for (const ccy of rateCcys) {
    if (ratesAmt) {
      shocks.push({
        factor_type: 'rate',
        key: `${ccy}:RATE`,
        amount: ratesAmt,
        bucket: 'ALL',
      })
    }
  }
  return {
    id: 'ui_custom',
    name: form.name || 'Custom Scenario',
    category: 'custom',
    shocks,
    max_loss_pct: displayPercentToFraction(form.limit),
  }
}

/** Default Scenario Builder form (display units: % / bp). */
export function defaultScenarioForm() {
  return { name: 'Custom Crash', equity: -20, vol: 50, rates: 100, fx: -5, limit: 10 }
}

/**
 * Named shock presets for Scenario Builder — request payloads only (no risk math).
 * Form fields use display units matching scenarioPayload().
 */
export const SCENARIO_PRESETS = Object.freeze([
  Object.freeze({
    id: 'equity_crash',
    label: 'Equity crash',
    form: Object.freeze({ name: 'Equity Crash', equity: -20, vol: 50, rates: 0, fx: -5, limit: 10 }),
  }),
  Object.freeze({
    id: 'rates_hike',
    label: 'Rates hike',
    form: Object.freeze({ name: 'Rates Hike', equity: -5, vol: 15, rates: 100, fx: 0, limit: 8 }),
  }),
  Object.freeze({
    id: 'vol_spike',
    label: 'Vol spike',
    form: Object.freeze({ name: 'Vol Spike', equity: -8, vol: 80, rates: 25, fx: -2, limit: 10 }),
  }),
  Object.freeze({
    id: 'fx_shock',
    label: 'FX shock',
    form: Object.freeze({ name: 'FX Shock', equity: 0, vol: 10, rates: 0, fx: -10, limit: 5 }),
  }),
])

/** Validate Scenario Builder form before API call (display checks only). */
export function validateScenarioForm(form) {
  const name = String(form?.name || '').trim()
  if (!name) return { ok: false, error: 'Scenario name is required' }
  const nums = ['equity', 'vol', 'rates', 'fx', 'limit']
  for (const k of nums) {
    if (!Number.isFinite(Number(form?.[k]))) {
      return { ok: false, error: `${k} must be a number` }
    }
  }
  if (Number(form.limit) <= 0) return { ok: false, error: 'Loss limit % must be > 0' }
  return { ok: true, error: null }
}

/**
 * Overview KPI strip from risk/summary + stress/evaluate (API display only).
 */
export function overviewKpis(summary, threats) {
  const ts = stressSummary(threats)
  return {
    market_value: summary?.market_value ?? null,
    var_99: summary?.var_99 ?? null,
    expected_shortfall_99: summary?.expected_shortfall_99 ?? null,
    worst_threat_loss: ts.worst?.loss ?? 0,
    threat_breaches: ts.breaches ?? 0,
    worst_threat_name: ts.worst?.scenario ?? null,
  }
}

function pluralCount(n, one, many) {
  return `${n} ${n === 1 ? one : many}`
}

/** Display value/limit from LimitResult — percents stay percents, not dollars. */
function limitValueLimit(item) {
  if (item.metric === 'single_position_pct') {
    return `${Number(item.value).toFixed(1)} / ${Number(item.limit).toFixed(1)} pct`
  }
  return `${money(item.value)} / ${money(item.limit)}`
}

/**
 * Book condition from loaded limit + threat payloads only (no client risk math).
 * Drill target is the first specialist section that can resolve the condition.
 */
export function overviewBookStatus({ limits, threats } = {}) {
  const lim = limitStatusCounts(limits)
  const ts = stressSummary(threats)
  const limitBreaches = lim.BREACH || 0
  const warnings = lim.WARNING || 0
  const threatBreaches = ts.breaches ?? 0

  let tone = 'ok'
  let label = 'Clear'
  if (limitBreaches > 0 || threatBreaches > 0) {
    tone = 'breach'
    label = 'Breach'
  } else if (warnings > 0) {
    tone = 'warn'
    label = 'Watch'
  }

  const parts = []
  if (limitBreaches) parts.push(pluralCount(limitBreaches, 'limit breach', 'limit breaches'))
  if (threatBreaches) parts.push(pluralCount(threatBreaches, 'threat breach', 'threat breaches'))
  if (!parts.length && warnings) parts.push(pluralCount(warnings, 'limit warning', 'limit warnings'))
  if (!parts.length) parts.push('No limit or threat breaches on loaded payloads')

  let drill = { id: 'var-es', label: 'Open VaR & ES' }
  if (limitBreaches > 0) drill = { id: 'limits', label: 'Open limit breaches' }
  else if (threatBreaches > 0) drill = { id: 'stress', label: 'Open worst threat' }
  else if (warnings > 0) drill = { id: 'limits', label: 'Open limits' }

  return { tone, label, reason: parts.join(' · '), drill, limitBreaches, threatBreaches, warnings }
}

/**
 * Actionable exception rows from API limit breaches + worst threat evaluation.
 */
export function overviewExceptions({ limits, threats } = {}) {
  const limitRows = []
  for (const item of breachedLimits(limits)) {
    const util = Number(item.utilization_pct)
    const bits = []
    if (Number.isFinite(util)) bits.push(`${util.toFixed(0)}% util`)
    if (item.value != null && item.limit != null) {
      bits.push(limitValueLimit(item))
    }
    limitRows.push({
      key: `limit-${item.metric || item.label}`,
      section: 'limits',
      title: item.label || item.metric || 'Limit',
      detail: bits.join(' · '),
      utilization_pct: Number.isFinite(util) ? util : 0,
      tone: 'breach',
      lead: false,
    })
  }
  limitRows.sort((a, b) => b.utilization_pct - a.utilization_pct)

  const rows = [...limitRows]
  const ts = stressSummary(threats)
  if (ts.worst?.scenario) {
    const loss = ts.worst.loss
    rows.push({
      key: 'threat-worst',
      section: 'stress',
      title: ts.worst.scenario,
      detail: Number.isFinite(Number(loss)) ? money(loss) : '',
      utilization_pct: 0,
      tone: (ts.breaches ?? 0) > 0 ? 'breach' : 'warn',
      lead: false,
    })
  }
  if (rows[0]) rows[0] = { ...rows[0], lead: true }
  return rows
}

/**
 * Overnight-tape rows from the loaded dashboard only (no invented run history).
 * Latest print is the current batch; exception rows follow.
 */
export function overviewTapeRows({ summary, threats, limits } = {}) {
  const status = overviewBookStatus({ limits, threats })
  const kpis = overviewKpis(summary, threats)
  const nav = kpis.market_value != null ? `NAV ${money(kpis.market_value)}` : ''
  const var99 = kpis.var_99 != null ? `99% VaR ${money(kpis.var_99)}` : ''
  const head = {
    key: 'dashboard-load',
    section: 'risk-runs',
    title: 'Loaded dashboard',
    detail: [nav, var99].filter(Boolean).join(' · '),
    tone: status.tone,
  }
  return [head, ...overviewExceptions({ limits, threats })]
}

/**
 * Section collage / entry points for Overview — teaser stats from loaded API payloads.
 * No risk math; navigation ids match NAV_SECTIONS.
 */
export function overviewCollage({ summary, threats, limits, hierarchy, stress, factors } = {}) {
  const ts = stressSummary(threats)
  const hs = hierarchySummary(hierarchy)
  const limCounts = limitStatusCounts(limits)
  const worstStressRow = worstStress(stress || [])
  const topFactor = topFactors(factors || [], 1)[0]
  return [
    {
      id: 'portfolio',
      label: 'Portfolio',
      hint: 'Hierarchy & positions',
      teaser: hs
        ? `${hs.desks} desks · ${hs.trades} trades · NAV ${money(hs.market_value ?? 0)}`
        : 'Open firm → trade tree',
    },
    {
      id: 'risk-factors',
      label: 'Risk Factors',
      hint: 'Exposures & heatmaps',
      teaser: topFactor
        ? `Top: ${topFactor.factor} (${money(topFactor.exposure)})`
        : 'Factor × bucket matrix',
    },
    {
      id: 'var-es',
      label: 'VaR & ES',
      hint: 'Analytics & attribution',
      teaser: summary
        ? `99% VaR ${money(summary.var_99)} · ES ${money(summary.expected_shortfall_99)}`
        : 'VaR / ES analytics',
    },
    {
      id: 'historical-analytics',
      label: 'Historical',
      hint: 'Wealth, drawdown, SPY',
      teaser: 'POST /risk/historical-analytics',
    },
    {
      id: 'stress',
      label: 'Stress',
      hint: 'Scenarios & reverse stress',
      teaser: worstStressRow
        ? `Worst: ${worstStressRow.scenario} ${money(worstStressRow.pnl)}`
        : 'Library & reverse stress',
    },
    {
      id: 'scenario-builder',
      label: 'Scenario Builder',
      hint: 'Shocks & hedge compare',
      teaser: 'Custom equity / rates / FX / vol shocks',
    },
    {
      id: 'pnl-explain',
      label: 'P&L Explain',
      hint: 'Attribution',
      teaser: 'POST /risk/attribution drivers',
    },
    {
      id: 'limits',
      label: 'Limits',
      hint: 'Utilization & status',
      teaser: `${limCounts.BREACH} breach · ${limCounts.WARNING} warn · ${limCounts.OK} ok`,
    },
    {
      id: 'risk-runs',
      label: 'Risk Runs',
      hint: 'Async run status',
      teaser: ts.breaches != null
        ? `${ts.breaches} threat breach${ts.breaches === 1 ? '' : 'es'} on book`
        : 'Start & poll async runs',
    },
  ]
}

/** Count limits by OK / WARNING / BREACH (uses limitStatus). */
export function limitStatusCounts(items) {
  const counts = { OK: 0, WARNING: 0, BREACH: 0 }
  for (const x of items || []) {
    const s = limitStatus(x)
    counts[s] = (counts[s] || 0) + 1
  }
  return counts
}

/**
 * AttributionRequest for POST /risk/attribution — SPY quantity scale demo.
 * Markets omitted so the API builds snapshots (same pattern as change-attr).
 */
export function demoPnLAttributionRequest(portfolio, options = {}) {
  if (!portfolio) return null
  return {
    previous_portfolio: portfolio,
    current_portfolio: spyScaledPortfolio(portfolio, options.scale ?? 1.5),
    dt_years: options.dt_years ?? 0,
  }
}

/** Default poll interval for non-terminal risk runs (display only). */
export const RISK_RUN_POLL_MS = 500

const RISK_RUN_TERMINAL = new Set(['COMPLETED', 'FAILED'])
const RISK_RUN_KNOWN = new Set(['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED'])

/** Prefer API RiskRunStatus; unknown → QUEUED for display. */
export function riskRunStatus(run) {
  const s = typeof run === 'string' ? run : run?.status
  return RISK_RUN_KNOWN.has(s) ? s : 'QUEUED'
}

/** CSS modifier: QUEUED → queued, etc. */
export function riskRunStatusClass(run) {
  return riskRunStatus(run).toLowerCase()
}

/** True when status is COMPLETED or FAILED (stop polling). */
export function isRiskRunTerminal(run) {
  return RISK_RUN_TERMINAL.has(riskRunStatus(run))
}

/**
 * Display parse for RiskRunView. Passes API fields through — no risk math.
 * result_types lists named payloads when present.
 */
export function riskRunSummary(run) {
  if (!run) return null
  const results = run.results || []
  return {
    id: run.id,
    portfolio_id: run.portfolio_id,
    status: riskRunStatus(run),
    run_type: run.run_type,
    error_message: run.error_message ?? null,
    created_at: run.created_at ?? null,
    started_at: run.started_at ?? null,
    finished_at: run.finished_at ?? null,
    duration_seconds: run.duration_seconds ?? null,
    result_count: results.length,
    result_types: results.map((r) => r.result_type),
  }
}

/**
 * Display parse for GET /market/rates-showcase. Passes API fields through — no risk math.
 */
export function ratesShowcaseSummary(payload) {
  if (!payload) return null
  const discount = payload.discount_curve || {}
  return {
    portfolio_id: payload.portfolio_id,
    market_snapshot_id: payload.market_snapshot_id,
    conventions: payload.conventions || {},
    discount_curve: discount,
    projection_curve: payload.projection_curve ?? null,
    nodes: [...(discount.nodes || [])],
    parallel_dv01: payload.parallel_dv01,
    key_rate_dv01: [...(payload.key_rate_dv01 || [])],
  }
}

/**
 * Display parse for RiskRun provenance. Copies backend fields only — never invents SHA.
 */
export function runProvenanceSummary(payload) {
  if (!payload) return null
  return {
    risk_run_id: payload.risk_run_id,
    portfolio_id: payload.portfolio_id,
    portfolio_version: payload.portfolio_version ?? null,
    market_snapshot_id: payload.market_snapshot_id ?? null,
    as_of: payload.as_of ?? null,
    historical_dataset_id: payload.historical_dataset_id ?? null,
    historical_dataset_version: payload.historical_dataset_version ?? null,
    pricing_engine_version: payload.pricing_engine_version ?? null,
    methodology: payload.methodology ?? null,
    scenario_set: [...(payload.scenario_set || [])],
    scenario_set_version: payload.scenario_set_version ?? null,
    calculation_config: payload.calculation_config ?? null,
    duration_seconds: payload.duration_seconds ?? null,
    status: payload.status,
    release_sha: payload.release_sha ?? null,
  }
}

/**
 * Request helper: scale SPY equity quantity for change-attribution demo.
 * Does not compute risk — only builds current_portfolio body.
 */
export function spyScaledPortfolio(portfolio, scale = 1.5) {
  if (!portfolio) return null
  const positions = (portfolio.positions || []).map((p) => {
    if (p?.symbol === 'SPY' && p?.type === 'equity') {
      return { ...p, quantity: Number(p.quantity) * scale }
    }
    return { ...p }
  })
  return { ...portfolio, positions }
}

/**
 * Flagship Compare T0/T1 book: same SPY×scale economics as the waterfall helper,
 * but a stable distinct id so durable attach-stored cannot clobber the catalog.
 */
export function t1SpyScaledPortfolio(portfolio, scale = 1.5) {
  const scaled = spyScaledPortfolio(portfolio, scale)
  if (!scaled) return null
  return { ...scaled, id: `${portfolio.id}-t1-spy-x${scale}` }
}

/**
 * Demo RiskChangeAttributionRequest: previous = book, current = SPY×scale.
 * Markets omitted so the API builds snapshots (OpenAPI quantity_increase pattern).
 */
export function demoChangeAttributionRequest(portfolio, options = {}) {
  if (!portfolio) return null
  return {
    previous_portfolio: portfolio,
    current_portfolio: spyScaledPortfolio(portfolio, options.scale ?? 1.5),
    metric: options.metric ?? 'var_99',
    methodology: options.methodology ?? 'DELTA_GAMMA',
  }
}

/**
 * Display parse for RiskChangeAttributionReport (M8.10). Driver labels / delta_risk
 * from API only — no client-side risk math.
 */
export function riskChangeAttributionSummary(report) {
  if (!report) return null
  return {
    metric: report.metric,
    previous_risk: report.previous_risk,
    current_risk: report.current_risk,
    total_change: report.total_change,
    explained_change: report.explained_change,
    residual: report.residual,
    items: report.items || [],
    drivers: (report.items || []).map((x) => x.driver),
  }
}

/**
 * Display parse for flagship RiskChangeReport. Passes backend fields through —
 * no client-side VaR / residual math.
 */
export function riskChangeReportSummary(report) {
  if (!report) return null
  return {
    t0_run_id: report.t0_run_id,
    t1_run_id: report.t1_run_id,
    metric: report.metric,
    unit: report.unit,
    sign_convention: report.sign_convention,
    currency_convention: report.currency_convention,
    previous_risk: report.previous_risk,
    current_risk: report.current_risk,
    total_change: report.total_change,
    portfolio_trade_change: report.portfolio_trade_change,
    market_change: report.market_change,
    explained_change: report.explained_change,
    residual: report.residual,
    residual_name: report.residual_name || 'residual / interactions',
    disclosed_changes: report.disclosed_changes || [],
    identity: report.identity || null,
    factor_contributors: report.factor_contributors || [],
    hierarchy_contributors: report.hierarchy_contributors || [],
    items: report.items || [],
  }
}

/** ES contribution dimension keys on ESContributionReport. */
export const ES_CONTRIBUTION_DIMENSIONS = [
  'by_position',
  'by_book',
  'by_strategy',
  'by_desk',
  'by_risk_factor',
]

const ES_RECON_KEY = {
  by_position: 'reconciliation_error_position',
  by_book: 'reconciliation_error_book',
  by_strategy: 'reconciliation_error_strategy',
  by_desk: 'reconciliation_error_desk',
  by_risk_factor: 'reconciliation_error_risk_factor',
}

/**
 * Display parse for ESContributionReport (M8.11). Slices one dimension for the table;
 * contribution_pct is already percent units from the API.
 */
export function esContributionSummary(report, dimension = 'by_position', topN = 8) {
  if (!report) return null
  const dim = ES_CONTRIBUTION_DIMENSIONS.includes(dimension) ? dimension : 'by_position'
  const items = report[dim] || []
  const reconKey = ES_RECON_KEY[dim]
  return {
    portfolio_id: report.portfolio_id,
    methodology: report.methodology ?? null,
    confidence: report.confidence,
    portfolio_var: report.portfolio_var,
    portfolio_es: report.portfolio_es,
    dimension: dim,
    items: items.slice(0, topN),
    item_count: items.length,
    reconciliation_error: report[reconKey] ?? 0,
  }
}

/**
 * Display parse for VaRMethodologyComparison (M8.12). Passes API rows through.
 */
export function varCompareSummary(report) {
  if (!report) return null
  return {
    portfolio_id: report.portfolio_id,
    observations: report.observations,
    results: report.results || [],
  }
}
