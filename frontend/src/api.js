/** Canonical API prefix (M7.6 / M8). Bodies unchanged vs legacy dual-mount. */
export const API_V1 = '/api/v1'

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function json(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {headers: {'Content-Type':'application/json'}, ...options})
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export async function loadDashboard() {
  return json(`${API_V1}/risk/dashboard`, {method: 'POST'})
}

export function evaluateCustomScenario(portfolio, scenario) {
  return json(`${API_V1}/risk/stress/evaluate/custom`,{method:'POST',body:JSON.stringify({portfolio,scenarios:[scenario]})})
}
export function reverseStress(portfolio, factor, target_loss_pct) {
  return json(`${API_V1}/risk/stress/reverse`,{method:'POST',body:JSON.stringify({portfolio,factor,target_loss_pct})})
}
/** Multi-factor reverse stress → MultiFactorReverseStressResult. */
export function reverseStressMulti(portfolio, target_loss_pct, options = {}) {
  return json(`${API_V1}/risk/stress/reverse/multi`, {
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
  return json(`${API_V1}/risk/stress/compare`, {
    method: 'POST',
    body: JSON.stringify({ portfolio, hedged_portfolio, scenarios, methodology }),
  })
}
export function askRisk(portfolio, question) {
  return json(`${API_V1}/risk/query`,{method:'POST',body:JSON.stringify({portfolio,question})})
}
/**
 * Limit breach drill-down → LimitDrilldownReport.
 * Use limitDrilldownSummary() from risk.mjs to normalize for display.
 */
export function limitDrilldown(portfolio, options = {}) {
  return json(`${API_V1}/risk/limits/drilldown`, {
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
 * P&L Explain → AttributionReport (M4.3 / M8.7).
 * Body: AttributionRequest (previous/current portfolio ± markets, optional dt_years).
 */
export function explainPnL(request) {
  return json(`${API_V1}/risk/attribution`, {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

/** Illustrative market-move demo → AttributionReport via POST /risk/attribution/demo. */
export function explainPnLDemo(portfolio) {
  return json(`${API_V1}/risk/attribution/demo`, {
    method: 'POST',
    body: JSON.stringify(portfolio),
  })
}

/**
 * Enqueue async risk run → RiskRunView (202).
 * Canonical: POST /api/v1/risk/runs (legacy dual-mount remains until sunset).
 * Poll with getRiskRun(id) until COMPLETED / FAILED.
 */
export function createRiskRun(portfolio, options = {}) {
  return json(`${API_V1}/risk/runs`, {
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
  return json(`${API_V1}/risk/runs/${encodeURIComponent(runId)}`)
}

/**
 * Risk-metric change waterfall → RiskChangeAttributionReport (M8.10).
 * Body: RiskChangeAttributionRequest (previous/current portfolio ± markets).
 */
export function changeAttribution(request) {
  return json(`${API_V1}/risk/change-attribution`, {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

/**
 * Expected Shortfall contributions → ESContributionReport (M8.11).
 * Methodology is a query param (LINEAR | DELTA_GAMMA | FULL_REVALUATION).
 */
export function esContributions(portfolio, methodology = 'DELTA_GAMMA') {
  const q = new URLSearchParams({ methodology })
  return json(`${API_V1}/risk/es?${q}`, {
    method: 'POST',
    body: JSON.stringify(portfolio),
  })
}

/**
 * Side-by-side VaR methodologies → VaRMethodologyComparison (M8.12).
 * Optional observations query (defaults server-side).
 */
export function compareVarMethodologies(portfolio, observations) {
  const q =
    observations != null && observations !== ''
      ? `?observations=${encodeURIComponent(observations)}`
      : ''
  return json(`${API_V1}/risk/var/compare${q}`, {
    method: 'POST',
    body: JSON.stringify(portfolio),
  })
}
