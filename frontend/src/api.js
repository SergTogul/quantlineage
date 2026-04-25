import { RISK_RUN_POLL_MS, isRiskRunTerminal, riskRunStatus } from './lib/risk.mjs'

/** Canonical API prefix (M7.6 / M8). Bodies unchanged vs legacy dual-mount. */
export const API_V1 = '/api/v1'

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function parseJsonBody(res) {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function httpError(res, body) {
  const err = new Error(`${res.status} ${res.statusText}`)
  err.status = res.status
  err.body = body
  return err
}

/** HEAVY inline refuse: HTTP 400 with details.use pointing at /risk/runs. */
function isHeavyInlineRefuse(err) {
  return (
    err?.status === 400 &&
    err?.body &&
    typeof err.body === 'object' &&
    err.body.details?.use === '/risk/runs'
  )
}

async function json(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {headers: {'Content-Type':'application/json'}, ...options})
  const body = await parseJsonBody(res)
  if (!res.ok) throw httpError(res, body)
  return body
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollRiskRunUntilTerminal(runId) {
  let run = await getRiskRun(runId)
  while (!isRiskRunTerminal(run)) {
    await sleep(RISK_RUN_POLL_MS)
    run = await getRiskRun(runId)
  }
  return run
}

function dashboardPayloadFromRun(run) {
  const results = Array.isArray(run?.results) ? run.results : []
  const typed = results.find((r) => r?.result_type === 'dashboard')
  const entry = typed ?? (results.length === 1 ? results[0] : null)
  const payload = entry?.payload
  if (!payload || typeof payload !== 'object') {
    throw new Error('Dashboard risk run completed without a usable payload')
  }
  return payload
}

async function loadDashboardViaRiskRun() {
  const portfolio = await getPortfolio()
  const created = await createRiskRun(portfolio, { run_type: 'dashboard' })
  const runId = created?.id
  if (!runId) throw new Error('Risk run create response missing id')
  const run = isRiskRunTerminal(created)
    ? created
    : await pollRiskRunUntilTerminal(runId)
  if (riskRunStatus(run) === 'FAILED') {
    throw new Error(run.error_message || `Risk run ${runId} FAILED`)
  }
  return dashboardPayloadFromRun(run)
}

/**
 * Coherent dashboard batch (10 keys). Prefer sync POST /risk/dashboard;
 * when HEAVY inline is refused, fall back to GET /portfolio + dashboard RiskRun.
 */
export async function loadDashboard() {
  try {
    return await json(`${API_V1}/risk/dashboard`, { method: 'POST' })
  } catch (err) {
    if (!isHeavyInlineRefuse(err)) throw err
    return loadDashboardViaRiskRun()
  }
}

/** Demo / default book → Portfolio (GET /portfolio). */
export function getPortfolio() {
  return json(`${API_V1}/portfolio`)
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
