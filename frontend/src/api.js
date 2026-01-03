const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function json(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {headers: {'Content-Type':'application/json'}, ...options})
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export async function loadDashboard() {
  const portfolio = await json('/portfolio')
  const body = JSON.stringify(portfolio)
  const [summary, stress, threats, contributors, limits, factors, varReport, hierarchy, attribution] = await Promise.all([
    json('/risk/summary', {method:'POST', body}), json('/risk/stress', {method:'POST', body}),
    json('/risk/stress/evaluate', {method:'POST', body}), json('/risk/contributors', {method:'POST', body}),
    json('/risk/limits', {method:'POST', body}), json('/risk/factors', {method:'POST', body}),
    json('/risk/var', {method:'POST', body}), json('/risk/hierarchy', {method:'POST', body}),
    json('/risk/attribution/demo', {method:'POST', body}),
  ])
  return {portfolio, summary, stress, threats, contributors, limits, factors, varReport, hierarchy, attribution}
}

export function evaluateCustomScenario(portfolio, scenario) {
  return json('/risk/stress/evaluate/custom',{method:'POST',body:JSON.stringify({portfolio,scenarios:[scenario]})})
}
export function reverseStress(portfolio, factor, target_loss_pct) {
  return json('/risk/stress/reverse',{method:'POST',body:JSON.stringify({portfolio,factor,target_loss_pct})})
}
/** Multi-factor reverse stress → MultiFactorReverseStressResult. */
export function reverseStressMulti(portfolio, target_loss_pct, options = {}) {
  return json('/risk/stress/reverse/multi', {
    method: 'POST',
    body: JSON.stringify({
      portfolio,
      target_loss_pct,
      factors: options.factors,
      weights: options.weights,
      max_shock: options.max_shock,
      max_shocks: options.max_shocks,
    }),
  })
}
/**
 * Before/after hedge comparison → HedgeComparisonReport (object, not list).
 * Use hedgeComparisonSummary() from risk.mjs to normalize for display.
 */
export function compareHedge(portfolio, hedged_portfolio, scenarios, methodology = 'DELTA_GAMMA') {
  return json('/risk/stress/compare', {
    method: 'POST',
    body: JSON.stringify({ portfolio, hedged_portfolio, scenarios, methodology }),
  })
}
export function askRisk(portfolio, question) {
  return json('/risk/query',{method:'POST',body:JSON.stringify({portfolio,question})})
}
/**
 * Limit breach drill-down → LimitDrilldownReport.
 * Use limitDrilldownSummary() from risk.mjs to normalize for display.
 */
export function limitDrilldown(portfolio, options = {}) {
  return json('/risk/limits/drilldown', {
    method: 'POST',
    body: JSON.stringify({
      portfolio,
      metric: options.metric,
      hierarchy: options.hierarchy,
      limits: options.limits,
      top_n: options.top_n,
      breaches_only: options.breaches_only,
    }),
  })
}

/**
 * Enqueue async risk run → RiskRunView (202). Prefer `/api/v1` after M7.2.
 * Poll with getRiskRun(id) until COMPLETED / FAILED.
 */
export function createRiskRun(portfolio, options = {}) {
  return json('/risk/runs', {
    method: 'POST',
    body: JSON.stringify({
      portfolio,
      run_type: options.run_type ?? 'summary',
      request: options.request ?? {},
      market_snapshot_id: options.market_snapshot_id ?? null,
    }),
  })
}

/** GET risk-run status / results by id → RiskRunView. */
export function getRiskRun(runId) {
  return json(`/risk/runs/${encodeURIComponent(runId)}`)
}
