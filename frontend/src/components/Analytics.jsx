import { useEffect, useState } from 'react'
import {
  changeAttribution, compareVarMethodologies, createRiskRun, esContributions, explainPnL,
  explainPnLDemo, getRiskRun,
} from '../api'
import {
  money, topFactors, varMethod, hierarchySummary, hierarchyNodeAtPath, hierarchyChildRows,
  hierarchyNodeMetrics, attributionSummary,
  isRiskRunTerminal, riskRunStatus, riskRunStatusClass, riskRunSummary, RISK_RUN_POLL_MS,
  demoChangeAttributionRequest, riskChangeAttributionSummary, demoPnLAttributionRequest,
  esContributionSummary, ES_CONTRIBUTION_DIMENSIONS, varCompareSummary,
} from '../lib/risk.mjs'

const RISK_RUN_TYPES = ['summary', 'var', 'stress', 'factors', 'limits', 'hierarchy', 'contributors']
const VAR_METHODS = ['LINEAR', 'DELTA_GAMMA', 'FULL_REVALUATION']
const CHANGE_ATTR_METRICS = ['var_99', 'var_95', 'expected_shortfall_99']
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

export function RiskFactors({items}) { return <div className="card"><h3>Risk Factors</h3><table><thead><tr><th>Factor</th><th>Bucket</th><th>Exposure</th></tr></thead><tbody>{topFactors(items).map(x=><tr key={`${x.factor}-${x.bucket}`}><td>{x.factor}<div className="muted">{x.factor_type}</div></td><td>{x.bucket}</td><td>{money(x.exposure)}</td></tr>)}</tbody></table></div> }
export function VaRAnalytics({report}) { const h=varMethod(report,'historical'),p=varMethod(report,'parametric'); return <div className="card"><h3>VaR / Expected Shortfall</h3><table><thead><tr><th>Method</th><th>99% VaR</th><th>ES</th></tr></thead><tbody>{[h,p].filter(Boolean).map(x=><tr key={x.method}><td>{x.method}</td><td>{money(x.var)}</td><td>{money(x.expected_shortfall)}</td></tr>)}</tbody></table><div className="muted foot">{report.contributions.length} component-risk contributions calculated</div></div> }

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
    return <div className="card wide"><h3>Portfolio Hierarchy</h3><div className="muted">No hierarchy loaded</div></div>
  }

  return (
    <div className="card wide">
      <h3>Portfolio Hierarchy</h3>
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
      <h3>P&amp;L Explain</h3>
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
    <div className="card">
      <h3>Risk Runs</h3>
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
        </div>
      )}
    </div>
  )
}

/**
 * M8.10: risk-metric change waterfall. Displays RiskChangeAttributionReport from API only.
 * Demo: previous book → current with SPY equity ×1.5.
 */
export function RiskChangeAttribution({ portfolio }) {
  const [metric, setMetric] = useState('var_99')
  const [methodology, setMethodology] = useState('DELTA_GAMMA')
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const request = demoChangeAttributionRequest(portfolio, { metric, methodology })
      const report = await changeAttribution(request)
      setSummary(riskChangeAttributionSummary(report))
    } catch (e) {
      setError(e.message || 'Change attribution failed')
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h3>Risk Change Attribution</h3>
      <div className="muted">
        VaR/ES waterfall after SPY×1.5 — POST /api/v1/risk/change-attribution (not P&amp;L Explain)
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
        <button type="button" onClick={run} disabled={!portfolio || loading}>
          {loading ? 'Attributing…' : 'Run attribution'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!summary && !error && <div className="muted foot">No attribution run yet</div>}
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
      <h3>ES Contributions</h3>
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
      <h3>VaR Methodology Compare</h3>
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
