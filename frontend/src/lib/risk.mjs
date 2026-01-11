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

/** Default stress scenarios for hedge-compare UI (API request payload only). */
export function defaultHedgeScenarios() {
  return [{ name: 'Crash', equity_shock: -0.2 }]
}

/** Thin display parse for MultiFactorReverseStressResult. */
export function reverseStressMultiSummary(result) {
  if (!result) return null
  return {
    converged: !!result.converged,
    target_loss_pct: result.target_loss_pct,
    achieved_loss_pct: result.achieved_loss_pct,
    pnl: result.pnl,
    shocks: result.shocks || [],
    factors: result.factors || [],
    message: result.message ?? null,
  }
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

export function scenarioPayload(form){
  return {id:'ui_custom',name:form.name||'Custom Scenario',kind:'custom',equity_shock:Number(form.equity)/100,vol_shock:Number(form.vol)/100,rates_shift_bps:Number(form.rates),fx_shock:Number(form.fx)/100,max_loss_pct:Number(form.limit)/100}
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
