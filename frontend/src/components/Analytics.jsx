import { useEffect, useState } from 'react'
import {
  changeAttribution, compareRiskRuns, compareVarMethodologies, createRiskRun, esContributions, explainPnL,
  explainPnLDemo, getRatesShowcase, getRiskRun, getRiskRunProvenance, API_V1,
} from '../api'
import BlockHelp from './BlockHelp'
import { ContributionBars, KeyRateDv01Curve } from './RiskVisuals.jsx'
import { riskChangeWaterfallSteps } from '../lib/riskVisuals.mjs'
import {
  money, topFactors, varMethod, hierarchySummary, hierarchyNodeAtPath, hierarchyChildRows,
  hierarchyNodeMetrics, attributionSummary,
  isRiskRunTerminal, riskRunStatus, riskRunStatusClass, riskRunSummary, RISK_RUN_POLL_MS,
  demoChangeAttributionRequest, riskChangeAttributionSummary, riskChangeReportSummary, demoPnLAttributionRequest,
  t1SpyScaledPortfolio,
  esContributionSummary, ES_CONTRIBUTION_DIMENSIONS, varCompareSummary,
  ratesShowcaseSummary, runProvenanceSummary,
} from '../lib/risk.mjs'

const RISK_RUN_TYPES = ['summary', 'var', 'stress', 'factors', 'limits', 'hierarchy', 'contributors']
const VAR_METHODS = ['LINEAR', 'DELTA_GAMMA', 'FULL_REVALUATION']
const WATERFALL_METRICS = ['var_99', 'var_95', 'expected_shortfall_99']
const CHANGE_ATTR_METRICS = ['var_99', 'var_95', 'expected_shortfall_99', 'dv01', 'vega', 'stress']
const PNL_MODES = [
  { id: 'position', label: 'SPY×1.5 position change (/attribution)' },
  { id: 'market_demo', label: 'Illustrative market move (/attribution/demo)' },
]

const ES_DIM_LABELS = {
  by_position: 'Position',
  by_book: 'Book',
  by_strategy: 'Strategy',
  by_desk: 'Desk',
  by_risk_factor: 'Risk factor',
}

export function RiskFactors({ items }) {
  return (
    <div className="card">
      <div className="block-title">
        <h3>Risk Factors</h3>
        <BlockHelp id="risk-factors" />
      </div>
      <table>
        <thead><tr><th>Factor</th><th>Bucket</th><th>Exposure</th></tr></thead>
        <tbody>
          {topFactors(items).map((x) => (
            <tr key={`${x.factor}-${x.bucket}`}>
              <td>{x.factor}<div className="muted">{x.factor_type}</div></td>
              <td>{x.bucket}</td>
              <td>{money(x.exposure)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Stage 10.5: USD OIS/SOFR-style curve nodes + 2Y/5Y/10Y KR-DV01 from the API.
 * Display only — no client-side DV01 math.
 */
export function RatesShowcase() {
  const [payload, setPayload] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    getRatesShowcase()
      .then((body) => {
        if (!cancelled) {
          setPayload(body)
          setError('')
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || 'Failed to load rates showcase')
      })
    return () => { cancelled = true }
  }, [])

  const s = ratesShowcaseSummary(payload)

  return (
    <div className="card">
      <div className="block-title">
        <h3>Rates curve / KR-DV01</h3>
        <BlockHelp id="rates-showcase" />
      </div>
      <div className="muted">USD OIS/SOFR-style demo zeros and SensitivityEngine KR-DV01 — API fields only</div>
      {error && <div className="error">{error}</div>}
      {!s && !error && <div className="muted foot">Loading rates showcase…</div>}
      {s && (
        <>
          <div className="muted foot">
            <strong>{s.discount_curve?.name}</strong>
            {s.market_snapshot_id ? ` · ${s.market_snapshot_id}` : ''}
            {s.conventions.shock_unit ? ` · ${s.conventions.shock_unit}` : ''}
          </div>
          <KeyRateDv01Curve rows={s.key_rate_dv01} />
          <table>
            <thead><tr><th>Tenor</th><th>Zero</th><th>KR-DV01</th></tr></thead>
            <tbody>
              {s.nodes.map((node) => {
                const kr = (s.key_rate_dv01 || []).find((row) => row.tenor === node.tenor)
                return (
                  <tr key={node.tenor}>
                    <td>{node.tenor}</td>
                    <td>{node.zero_rate}</td>
                    <td>{kr ? money(kr.value) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="parallel-dv01" data-testid="parallel-dv01">
            <span className="muted">Parallel DV01</span>
            <strong>{money(s.parallel_dv01 ?? 0)}</strong>
            {s.conventions.sensitivity_unit ? (
              <span className="muted">{s.conventions.sensitivity_unit}</span>
            ) : null}
          </div>
          {s.conventions.limitations && (
            <div className="muted foot">{s.conventions.limitations}</div>
          )}
        </>
      )}
    </div>
  )
}

/**
 * Stage 10.5: calculation lineage from GET /risk/runs/{id}/provenance.
 * Copies backend fields only — never invents a release SHA.
 * When embedded, display `run.provenance` from the polled RiskRunView so
 * status/duration stay equal to executed lineage after poll.
 */
export function RunProvenance({ runId, embedded, provenance }) {
  const [fetched, setFetched] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (embedded || !runId) {
      return undefined
    }
    let cancelled = false
    getRiskRunProvenance(runId)
      .then((body) => {
        if (!cancelled) {
          setFetched(body)
          setError('')
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || 'Failed to load provenance')
      })
    return () => { cancelled = true }
  }, [runId, embedded])

  const payload = embedded ? provenance : (runId ? fetched : null)

  const s = runProvenanceSummary(payload)
  const rows = s
    ? [
        ['RiskRun', s.risk_run_id],
        ['Portfolio', s.portfolio_id],
        ['Portfolio version', s.portfolio_version],
        ['Market snapshot', s.market_snapshot_id],
        ['As of', s.as_of],
        ['Dataset', s.historical_dataset_id],
        ['Dataset version', s.historical_dataset_version],
        ['Pricing engine', s.pricing_engine_version],
        ['Methodology', s.methodology],
        ['Scenario set', (s.scenario_set || []).join(', ')],
        ['Duration (s)', s.duration_seconds],
        ['Status', s.status],
        ['Release SHA', s.release_sha],
      ].filter(([, value]) => value != null && value !== '')
    : []

  return (
    <div className={embedded ? 'risk-run-status' : 'card'} data-testid="golden-demo-provenance">
      <div className="block-title">
        <h3>Calculation provenance</h3>
        <BlockHelp id="run-provenance" />
      </div>
      <div className="muted">Persisted RiskRun lineage — displayed fields equal the backend payload</div>
      {!runId && <div className="muted foot">Start a risk run to load lineage</div>}
      {error && <div className="error">{error}</div>}
      {s && (
        <table>
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label}>
                <td>{label}</td>
                <td>{String(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export function VaRAnalytics({ report }) {
  const h = varMethod(report, 'historical')
  const p = varMethod(report, 'parametric')
  return (
    <div className="card" data-testid="golden-demo-var-es">
      <div className="block-title">
        <h3>VaR / Expected Shortfall</h3>
        <BlockHelp id="var-es" />
      </div>
      <table>
        <thead><tr><th>Method</th><th>99% VaR</th><th>ES</th></tr></thead>
        <tbody>
          {[h, p].filter(Boolean).map((x) => (
            <tr key={x.method}>
              <td>{x.method}</td>
              <td>{money(x.var)}</td>
              <td>{money(x.expected_shortfall)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="muted foot">{report.contributions.length} component-risk contributions calculated</div>
    </div>
  )
}

/**
 * M8.6: Firm→trade hierarchy drill-down. Metrics from selected API node only.
 */
export function Hierarchy({ node }) {
  const [path, setPath] = useState([])
  const resolved = hierarchyNodeAtPath(node, path)
  const selected = resolved?.node
  const metrics = hierarchyNodeMetrics(selected)
  const children = hierarchyChildRows(selected)
  const summary = hierarchySummary(node)

  if (!node || !resolved) {
    return (
      <div className="card wide" data-testid="golden-demo-hierarchy">
        <div className="block-title">
          <h3>Portfolio Hierarchy</h3>
          <BlockHelp id="portfolio-hierarchy" />
        </div>
        <div className="muted">No hierarchy loaded</div>
      </div>
    )
  }

  return (
    <div className="card wide" data-testid="golden-demo-hierarchy">
      <div className="block-title">
        <h3>Portfolio Hierarchy</h3>
        <BlockHelp id="portfolio-hierarchy" />
      </div>
      <div className="muted">
        Drill Firm → Portfolio → Desk → Strategy → Book → Trade — node metrics from API
        {summary ? ` · book has ${summary.desks} desks / ${summary.trades} trades` : ''}
      </div>
      <nav className="hierarchy-crumb" aria-label="Hierarchy path">
        {resolved.trail.map((n, i) => {
          const atEnd = i === resolved.trail.length - 1
          const crumbPath = path.slice(0, i)
          return (
            <span key={`${n.level}-${n.name}-${i}`}>
              {i > 0 && <span className="hierarchy-crumb-sep">→</span>}
              {atEnd
                ? <strong>{n.name}</strong>
                : (
                  <button type="button" className="hierarchy-crumb-btn" onClick={() => setPath(crumbPath)}>
                    {n.name}
                  </button>
                )}
              <span className="muted hierarchy-crumb-level">{n.level}</span>
            </span>
          )
        })}
      </nav>
      {metrics && (
        <div className="hierarchy-metrics">
          <span>NAV <strong>{money(metrics.market_value ?? 0)}</strong></span>
          <span>99% VaR <strong>{money(metrics.var_99 ?? 0)}</strong></span>
          <span>ES <strong>{money(metrics.expected_shortfall_99 ?? 0)}</strong></span>
          <span>Δ {money(metrics.delta ?? 0)}</span>
          <span>ν {money(metrics.vega ?? 0)}</span>
          <span>DV01 {money(metrics.dv01 ?? 0)}</span>
          {metrics.path ? <span className="muted">{metrics.path}</span> : null}
        </div>
      )}
      {children.length === 0
        ? <div className="muted foot">Leaf node — no children</div>
        : (
          <table className="hierarchy-children">
            <thead>
              <tr>
                <th>Child</th>
                <th>Level</th>
                <th>NAV</th>
                <th>99% VaR</th>
                <th>ES</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {children.map((c) => (
                <tr key={`${c.level}-${c.name}-${c.index}`}>
                  <td>{c.name}</td>
                  <td className="muted">{c.level}</td>
                  <td>{money(c.market_value ?? 0)}</td>
                  <td>{money(c.var_99 ?? 0)}</td>
                  <td>{money(c.expected_shortfall_99 ?? 0)}</td>
                  <td>
                    <button
                      type="button"
                      className="hierarchy-drill-btn"
                      onClick={() => setPath([...path, c.index])}
                    >
                      {c.child_count === 0 ? 'Select' : 'Drill'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  )
}

/**
 * M8.7: P&L Explain wired to POST /risk/attribution (and optional /attribution/demo).
 * Displays AttributionReport from API only — no client risk math.
 */
export function Attribution({ portfolio, initialReport = null }) {
  const [mode, setMode] = useState('position')
  const [scale, setScale] = useState(1.5)
  const [dtYears, setDtYears] = useState(0)
  const [report, setReport] = useState(initialReport)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [source, setSource] = useState(initialReport ? 'dashboard' : null)

  const s = attributionSummary(report)

  async function run() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      if (mode === 'market_demo') {
        const next = await explainPnLDemo(portfolio)
        setReport(next)
        setSource('demo')
      } else {
        const request = demoPnLAttributionRequest(portfolio, {
          scale: Number(scale) || 1.5,
          dt_years: Number(dtYears) || 0,
        })
        const next = await explainPnL(request)
        setReport(next)
        setSource('attribution')
      }
    } catch (e) {
      setError(e.message || 'Attribution failed')
      setReport(null)
      setSource(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card wide">
      <div className="block-title">
        <h3>P&amp;L Explain</h3>
        <BlockHelp id="pnl-explain" />
      </div>
      <div className="muted">
        Market / trade-flow bridge from AttributionEngine — POST /api/v1/risk/attribution
        (demo endpoint optional for illustrative marks)
      </div>
      <div className="inline-form risk-run-form pnl-explain-form">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          aria-label="pnl explain mode"
          disabled={loading}
        >
          {PNL_MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
        {mode === 'position' && (
          <>
            <label className="muted">
              SPY scale
              <input
                type="number"
                step="0.1"
                min="0"
                value={scale}
                onChange={(e) => setScale(e.target.value)}
                aria-label="pnl spy scale"
                disabled={loading}
              />
            </label>
            <label className="muted">
              dt years
              <input
                type="number"
                step="0.001"
                min="0"
                value={dtYears}
                onChange={(e) => setDtYears(e.target.value)}
                aria-label="pnl dt years"
                disabled={loading}
              />
            </label>
          </>
        )}
        <button type="button" onClick={run} disabled={!portfolio || loading}>
          {loading ? 'Explaining…' : 'Run P&L explain'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!s && !error && <div className="muted foot">No attribution loaded — run explain to call the API</div>}
      {s && (
        <div className="risk-panel-result">
          <div className="attribution-mv">
            <span>Base MV <strong>{money(s.base_market_value ?? 0)}</strong></span>
            <span>Current MV <strong>{money(s.current_market_value ?? 0)}</strong></span>
            {source && (
              <span className="muted">
                via {source === 'demo' ? '/attribution/demo' : source === 'dashboard' ? 'dashboard load' : '/attribution'}
              </span>
            )}
          </div>
          {s.items.length === 0
            ? <div className="muted foot">No drivers returned</div>
            : (
              <table>
                <thead><tr><th>Driver</th><th>P&amp;L</th></tr></thead>
                <tbody>{s.items.map((x) => (
                  <tr key={x.driver}>
                    <td>{x.driver}</td>
                    <td className={x.pnl < 0 ? 'negative' : 'positive'}>{money(x.pnl)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          <div className="attribution-total">
            <span>Total change <strong>{money(s.total_change)}</strong></span>
            <span>Explained {money(s.explained_change ?? 0)}</span>
            <span className={`attribution-residual ${(s.residual ?? 0) < 0 ? 'negative' : 'positive'}`}>
              Residual <strong>{money(s.residual ?? 0)}</strong>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * M8.9: start + poll async risk runs. Status/results come from the API only.
 */
export function RiskRuns({ portfolio }) {
  const [runType, setRunType] = useState('summary')
  const [run, setRun] = useState(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')

  const runId = run?.id
  const runStatus = run?.status

  useEffect(() => {
    if (!runId || isRiskRunTerminal({ status: runStatus })) return undefined
    let cancelled = false
    const tick = async () => {
      try {
        const next = await getRiskRun(runId)
        if (!cancelled) {
          setRun(next)
          setError('')
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'Poll failed')
      }
    }
    const timer = setInterval(tick, RISK_RUN_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [runId, runStatus])

  async function start() {
    if (!portfolio) return
    setStarting(true)
    setError('')
    try {
      const created = await createRiskRun(portfolio, { run_type: runType })
      setRun(created)
    } catch (e) {
      setError(e.message || 'Failed to start risk run')
      setRun(null)
    } finally {
      setStarting(false)
    }
  }

  const s = riskRunSummary(run)
  const polling = s && !isRiskRunTerminal(s)

  return (
    <div className="card" data-testid="golden-demo-risk-runs">
      <div className="block-title">
        <h3>Risk Runs</h3>
        <BlockHelp id="risk-runs" />
      </div>
      <div className="muted">Async POST/GET /api/v1/risk/runs — poll until COMPLETED or FAILED</div>
      <div className="inline-form risk-run-form">
        <select
          value={runType}
          onChange={(e) => setRunType(e.target.value)}
          aria-label="run type"
          disabled={starting || polling}
        >
          {RISK_RUN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button type="button" onClick={start} disabled={!portfolio || starting || polling}>
          {starting ? 'Starting…' : polling ? 'Running…' : 'Start run'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!s && !error && <div className="muted foot">No run started yet</div>}
      {s && (
        <div className="risk-run-status">
          <div className="card-title-row">
            <strong>{s.run_type}</strong>
            <span className={`status ${riskRunStatusClass(s)}`}>{riskRunStatus(s)}</span>
          </div>
          <div className="muted foot">
            id {s.id}
            {s.duration_seconds != null ? ` · ${s.duration_seconds.toFixed(2)}s` : ''}
            {polling ? ' · polling…' : ''}
          </div>
          {s.status === 'FAILED' && s.error_message && (
            <div className="error risk-run-error">{s.error_message}</div>
          )}
          {s.status === 'COMPLETED' && (
            s.result_count === 0
              ? <div className="muted foot">Completed with no result payloads</div>
              : (
                <div className="muted foot">
                  Results: {s.result_types.join(', ')}
                </div>
              )
          )}
          <RunProvenance runId={s.id} embedded provenance={run?.provenance} />
        </div>
      )}
    </div>
  )
}

/**
 * Stage 10.2: Why Did My Risk Change. Displays backend payloads only — no client-side risk math.
 * Demo: SPY×1.5 waterfall (legacy) or one-click T0/T1 RiskRun pair.
 */
export function RiskChangeAttribution({ portfolio }) {
  const [metric, setMetric] = useState('var_99')
  const [methodology, setMethodology] = useState('DELTA_GAMMA')
  const [summary, setSummary] = useState(null)
  const [flagship, setFlagship] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function runWaterfall() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const request = demoChangeAttributionRequest(portfolio, { metric, methodology })
      const report = await changeAttribution(request)
      setFlagship(null)
      setSummary(riskChangeAttributionSummary(report))
    } catch (e) {
      setError(e.message || 'Change attribution failed')
      setSummary(null)
      setFlagship(null)
    } finally {
      setLoading(false)
    }
  }

  async function runT0T1() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const t0 = await createRiskRun(portfolio, { run_type: 'summary', request: { methodology } })
      let left = t0
      while (!isRiskRunTerminal(left)) {
        await new Promise((resolve) => setTimeout(resolve, RISK_RUN_POLL_MS))
        left = await getRiskRun(left.id)
      }
      if (left.status !== 'COMPLETED') {
        throw new Error(left.error_message || 'Risk run failed')
      }
      const t1Book = t1SpyScaledPortfolio(portfolio, 1.5)
      const t1 = await createRiskRun(t1Book, {
        run_type: 'summary',
        request: { methodology },
        market_snapshot_id: left.market_snapshot_id ?? null,
      })
      let right = t1
      while (!isRiskRunTerminal(right)) {
        await new Promise((resolve) => setTimeout(resolve, RISK_RUN_POLL_MS))
        right = await getRiskRun(right.id)
      }
      if (right.status !== 'COMPLETED') {
        throw new Error(right.error_message || 'Risk run failed')
      }
      const report = await compareRiskRuns({
        t0_run_id: left.id,
        t1_run_id: right.id,
        metric,
      })
      setSummary(null)
      setFlagship(riskChangeReportSummary(report))
    } catch (e) {
      setError(e.message || 'Risk-run compare failed')
      setSummary(null)
      setFlagship(null)
    } finally {
      setLoading(false)
    }
  }

  const waterfallDisabled = loading || !WATERFALL_METRICS.includes(metric)

  return (
    <div className="card wide" data-testid="golden-demo-risk-change">
      <div className="block-title">
        <h3>Risk Change Attribution</h3>
        <BlockHelp id="risk-change-attribution" />
      </div>
      <div className="muted">
        Why did my risk change — two COMPLETED RiskRuns (POST /api/v1/risk/runs/compare) or SPY×1.5 waterfall.
        UI displays the backend payload only.
      </div>
      <div className="inline-form risk-run-form">
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
          aria-label="change attribution metric"
          disabled={loading}
        >
          {CHANGE_ATTR_METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <select
          value={methodology}
          onChange={(e) => setMethodology(e.target.value)}
          aria-label="change attribution methodology"
          disabled={loading}
        >
          {VAR_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <button type="button" onClick={runT0T1} disabled={!portfolio || loading}>
          {loading ? 'Comparing…' : 'Compare T0/T1'}
        </button>
        <button type="button" onClick={runWaterfall} disabled={!portfolio || waterfallDisabled}>
          {loading ? 'Attributing…' : 'Run attribution'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!summary && !flagship && !error && <div className="muted foot">No attribution run yet</div>}
      {flagship && <RiskChangeFlagshipPanel report={flagship} />}
      {summary && (
        <div className="risk-panel-result">
          <div className="muted foot">{summary.metric}</div>
          {summary.items.length === 0
            ? <div className="muted foot">No drivers returned</div>
            : (
              <table>
                <thead><tr><th>Driver</th><th>Δ Risk</th></tr></thead>
                <tbody>{summary.items.map((x) => (
                  <tr key={x.driver}>
                    <td>{x.driver}</td>
                    <td className={(x.delta_risk ?? 0) < 0 ? 'negative' : 'positive'}>
                      {money(x.delta_risk ?? 0)}
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          <div className="attribution-total">
            <span>
              {money(summary.previous_risk ?? 0)} → {money(summary.current_risk ?? 0)}
              {' '}(<strong className={(summary.total_change ?? 0) < 0 ? 'negative' : 'positive'}>
                {money(summary.total_change ?? 0)}
              </strong>)
            </span>
            <span>Explained {money(summary.explained_change ?? 0)}</span>
            <span className={`attribution-residual ${(summary.residual ?? 0) < 0 ? 'negative' : 'positive'}`}>
              Residual <strong>{money(summary.residual ?? 0)}</strong>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

const IDENTITY_FIELDS = [
  ['portfolio_version', 'Portfolio version'],
  ['market_snapshot_id', 'Market snapshot'],
  ['historical_dataset_id', 'Historical dataset'],
  ['historical_dataset_version', 'Dataset version'],
  ['methodology', 'Methodology'],
  ['calculation_config', 'Calculation config'],
]

function formatIdentityValue(value) {
  if (value == null || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function RiskChangeIdentity({ identity, disclosedChanges }) {
  if (!identity) return null
  const changed = new Set(identity.changed_fields || [])
  return (
    <div className="risk-change-identity" data-testid="risk-change-identity">
      <table>
        <thead>
          <tr>
            <th>Identity</th>
            <th>T0</th>
            <th>T1</th>
          </tr>
        </thead>
        <tbody>
          {IDENTITY_FIELDS.map(([key, label]) => (
            <tr key={key} data-changed={changed.has(key) ? 'true' : 'false'}>
              <th scope="row">{label}</th>
              <td>{formatIdentityValue(identity.t0?.[key])}</td>
              <td>{formatIdentityValue(identity.t1?.[key])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(disclosedChanges || []).length > 0 && (
        <div className="muted foot">Changed inputs: {disclosedChanges.join(', ')}</div>
      )}
    </div>
  )
}

function RiskChangeWaterfall({ report }) {
  const steps = riskChangeWaterfallSteps(report)
  if (!steps.length) return null
  return (
    <div
      className="risk-change-waterfall"
      data-testid="risk-change-waterfall"
      role="list"
      aria-label="T0 to T1 risk-change waterfall"
    >
      {steps.map((step) => (
        <div
          key={step.key}
          className="waterfall-step"
          role="listitem"
          data-testid={step.key === 'residual' ? 'waterfall-step-residual' : 'waterfall-step'}
          data-step={step.key}
        >
          <span className="waterfall-step-label">{step.label}</span>
          <div className="waterfall-step-track">
            <div
              className={`waterfall-step-fill ${step.kind === 'level' ? 'level' : step.value < 0 ? 'negative' : 'positive'}`}
              style={{ height: `${step.barPct}%` }}
            />
          </div>
          <span className={`waterfall-step-value ${step.value < 0 ? 'negative' : 'positive'}`}>
            {money(step.value)}
          </span>
        </div>
      ))}
    </div>
  )
}

function RiskChangeFlagshipPanel({ report }) {
  const [path, setPath] = useState(null)
  const tree = report.hierarchy_contributors || []
  const node = hierarchyNodeAtPathFromContributors(tree, path) || tree[0]
  const children = node?.children || []
  const factors = report.factor_contributors || []

  return (
    <div className="risk-panel-result" data-testid="golden-demo-risk-change-result">
      <div className="muted foot">
        {report.metric} · {report.unit}
      </div>
      <div className="muted foot">{report.sign_convention}</div>
      <div className="muted foot">
        <a href={`${API_V1}/risk/runs/${encodeURIComponent(report.t0_run_id)}`}>{report.t0_run_id}</a>
        {' → '}
        <a href={`${API_V1}/risk/runs/${encodeURIComponent(report.t1_run_id)}`}>{report.t1_run_id}</a>
      </div>
      <RiskChangeIdentity identity={report.identity} disclosedChanges={report.disclosed_changes} />
      <RiskChangeWaterfall report={report} />
      <div className="attribution-total">
        <span>
          {money(report.previous_risk ?? 0)} → {money(report.current_risk ?? 0)}
          {' '}(<strong className={(report.total_change ?? 0) < 0 ? 'negative' : 'positive'}>
            {money(report.total_change ?? 0)}
          </strong>)
        </span>
        <span>Trade {money(report.portfolio_trade_change ?? 0)}</span>
        <span>Market {money(report.market_change ?? 0)}</span>
        <span className={`attribution-residual ${(report.residual ?? 0) < 0 ? 'negative' : 'positive'}`}>
          {report.residual_name || 'residual / interactions'}{' '}
          <strong>{money(report.residual ?? 0)}</strong>
        </span>
      </div>
      <div data-testid="risk-change-factors">
        {factors.length === 0
          ? <div className="muted foot">No factor contributors in this report</div>
          : (
            <table>
              <thead><tr><th>Factor</th><th>Δ Risk</th></tr></thead>
              <tbody>{factors.map((x) => (
                <tr key={x.factor_id}>
                  <td>{x.factor_id}</td>
                  <td className={(x.delta_risk ?? 0) < 0 ? 'negative' : 'positive'}>
                    {money(x.delta_risk ?? 0)}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          )}
      </div>
      {node && (
        <div data-testid="risk-change-drill">
          <div className="muted foot">
            Drilldown {node.level}: {node.path || node.name}
            {path && (
              <button type="button" className="linkish risk-change-drill-up" onClick={() => setPath(parentContributorPath(path))}>
                Up
              </button>
            )}
          </div>
          {children.length > 0 && (
            <table>
              <thead><tr><th>Node</th><th>Δ Risk</th></tr></thead>
              <tbody>{children.map((child) => (
                <tr key={child.path}>
                  <td>
                    <button type="button" className="linkish" onClick={() => setPath(child.path)}>
                      {child.level} {child.name}
                    </button>
                  </td>
                  <td className={(child.delta_risk ?? 0) < 0 ? 'negative' : 'positive'}>
                    {money(child.delta_risk ?? 0)}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

function hierarchyNodeAtPathFromContributors(nodes, path) {
  if (!path) return nodes?.[0] || null
  const stack = [...(nodes || [])]
  while (stack.length) {
    const node = stack.shift()
    if (node.path === path) return node
    for (const child of node.children || []) stack.push(child)
  }
  return nodes?.[0] || null
}

function parentContributorPath(path) {
  if (!path || !path.includes('/')) return null
  return path.split('/').slice(0, -1).join('/') || null
}

/**
 * M8.11: ES contributions by hierarchy / factor. Displays ESContributionReport from API only.
 */
export function ESContributions({ portfolio }) {
  const [methodology, setMethodology] = useState('DELTA_GAMMA')
  const [dimension, setDimension] = useState('by_position')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const next = await esContributions(portfolio, methodology)
      setReport(next)
    } catch (e) {
      setError(e.message || 'ES contributions failed')
      setReport(null)
    } finally {
      setLoading(false)
    }
  }

  const s = esContributionSummary(report, dimension)

  return (
    <div className="card">
      <div className="block-title">
        <h3>ES Contributions</h3>
        <BlockHelp id="es-contributions" />
      </div>
      <div className="muted">
        Tail-conditional ES by position / book / desk / strategy / factor — POST /api/v1/risk/es
      </div>
      <div className="inline-form risk-run-form">
        <select
          value={methodology}
          onChange={(e) => setMethodology(e.target.value)}
          aria-label="es methodology"
          disabled={loading}
        >
          {VAR_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <select
          value={dimension}
          onChange={(e) => setDimension(e.target.value)}
          aria-label="es dimension"
          disabled={loading}
        >
          {ES_CONTRIBUTION_DIMENSIONS.map((d) => (
            <option key={d} value={d}>{ES_DIM_LABELS[d] || d}</option>
          ))}
        </select>
        <button type="button" onClick={run} disabled={!portfolio || loading}>
          {loading ? 'Loading…' : 'Load ES'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!s && !error && <div className="muted foot">No ES report loaded yet</div>}
      {s && (
        <div className="risk-panel-result">
          <div className="attribution-total">
            <span>99% VaR <strong>{money(s.portfolio_var ?? 0)}</strong></span>
            <span>99% ES <strong>{money(s.portfolio_es ?? 0)}</strong></span>
            {s.methodology && <span className="muted">{s.methodology}</span>}
            {s.confidence != null && (
              <span className="muted">{(s.confidence * 100).toFixed(0)}% conf</span>
            )}
          </div>
          {s.items.length === 0
            ? <div className="muted foot">No contributions in {ES_DIM_LABELS[s.dimension]}</div>
            : (
              <>
                {s.dimension === 'by_risk_factor' && (
                  <ContributionBars
                    items={s.items}
                    amountKey="component_es"
                    ariaLabel="ES risk-factor contribution bars"
                  />
                )}
                <table>
                  <thead>
                    <tr>
                      <th>{ES_DIM_LABELS[s.dimension] || 'Key'}</th>
                      <th>Component ES</th>
                      <th>Contrib %</th>
                    </tr>
                  </thead>
                  <tbody>{s.items.map((x) => (
                    <tr key={x.key}>
                      <td>{x.label || x.key}</td>
                      <td className={(x.component_es ?? 0) < 0 ? 'negative' : 'positive'}>
                        {money(x.component_es ?? 0)}
                      </td>
                      <td>{(x.contribution_pct ?? 0).toFixed(1)}%</td>
                    </tr>
                  ))}</tbody>
                </table>
              </>
            )}
          <div className="muted foot">
            Showing {s.items.length} of {s.item_count}
            {' · '}recon err {money(s.reconciliation_error ?? 0)}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * M8.12: Linear / Δ-Γ / Full-reval VaR side-by-side. Displays VaRMethodologyComparison from API only.
 */
export function VaRCompare({ portfolio }) {
  const [observations, setObservations] = useState('')
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const obs = observations === '' ? undefined : Number(observations)
      const report = await compareVarMethodologies(
        portfolio,
        obs != null && Number.isFinite(obs) ? obs : undefined,
      )
      setSummary(varCompareSummary(report))
    } catch (e) {
      setError(e.message || 'VaR compare failed')
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card wide">
      <div className="block-title">
        <h3>VaR Methodology Compare</h3>
        <BlockHelp id="var-compare" />
      </div>
      <div className="muted">
        LINEAR vs DELTA_GAMMA vs FULL_REVALUATION — POST /api/v1/risk/var/compare
      </div>
      <div className="inline-form risk-run-form">
        <label className="muted">
          Observations
          <input
            type="number"
            min={1}
            max={5000}
            value={observations}
            onChange={(e) => setObservations(e.target.value)}
            placeholder="default"
            aria-label="var compare observations"
            disabled={loading}
          />
        </label>
        <button type="button" onClick={run} disabled={!portfolio || loading}>
          {loading ? 'Comparing…' : 'Compare methods'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!summary && !error && <div className="muted foot">No comparison run yet</div>}
      {summary && (
        <div className="risk-panel-result">
          <div className="muted foot">
            {summary.observations} observations
            {summary.portfolio_id ? ` · ${summary.portfolio_id}` : ''}
          </div>
          {summary.results.length === 0
            ? <div className="muted foot">No methodology rows returned</div>
            : (
              <table>
                <thead>
                  <tr>
                    <th>Methodology</th>
                    <th>95% VaR</th>
                    <th>99% VaR</th>
                    <th>99% ES</th>
                    <th>Runtime</th>
                  </tr>
                </thead>
                <tbody>{summary.results.map((row) => (
                  <tr key={row.methodology}>
                    <td>{row.methodology}</td>
                    <td>{money(row.var_95 ?? 0)}</td>
                    <td>{money(row.var_99 ?? 0)}</td>
                    <td>{money(row.expected_shortfall_99 ?? 0)}</td>
                    <td className="muted">
                      {row.runtime_ms != null ? `${Number(row.runtime_ms).toFixed(1)} ms` : '—'}
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
        </div>
      )}
    </div>
  )
}
