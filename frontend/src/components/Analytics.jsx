import { useEffect, useState } from 'react'
import {
  changeAttribution, compareVarMethodologies, createRiskRun, esContributions, getRiskRun,
} from '../api'
import {
  money, topFactors, varMethod, hierarchySummary, attributionSummary,
  isRiskRunTerminal, riskRunStatus, riskRunStatusClass, riskRunSummary, RISK_RUN_POLL_MS,
  demoChangeAttributionRequest, riskChangeAttributionSummary,
  esContributionSummary, ES_CONTRIBUTION_DIMENSIONS, varCompareSummary,
} from '../lib/risk.mjs'

const RISK_RUN_TYPES = ['summary', 'var', 'stress', 'factors', 'limits', 'hierarchy', 'contributors']
const VAR_METHODS = ['LINEAR', 'DELTA_GAMMA', 'FULL_REVALUATION']
const CHANGE_ATTR_METRICS = ['var_99', 'var_95', 'expected_shortfall_99']

const ES_DIM_LABELS = {
  by_position: 'Position',
  by_book: 'Book',
  by_strategy: 'Strategy',
  by_desk: 'Desk',
  by_risk_factor: 'Risk factor',
}

export function RiskFactors({items}) { return <div className="card"><h3>Risk Factors</h3><table><thead><tr><th>Factor</th><th>Bucket</th><th>Exposure</th></tr></thead><tbody>{topFactors(items).map(x=><tr key={`${x.factor}-${x.bucket}`}><td>{x.factor}<div className="muted">{x.factor_type}</div></td><td>{x.bucket}</td><td>{money(x.exposure)}</td></tr>)}</tbody></table></div> }
export function VaRAnalytics({report}) { const h=varMethod(report,'historical'),p=varMethod(report,'parametric'); return <div className="card"><h3>VaR / Expected Shortfall</h3><table><thead><tr><th>Method</th><th>99% VaR</th><th>ES</th></tr></thead><tbody>{[h,p].filter(Boolean).map(x=><tr key={x.method}><td>{x.method}</td><td>{money(x.var)}</td><td>{money(x.expected_shortfall)}</td></tr>)}</tbody></table><div className="muted foot">{report.contributions.length} component-risk contributions calculated</div></div> }
export function Hierarchy({node}) {
  const s = hierarchySummary(node)
  if (!s) return <div className="card"><h3>Portfolio Hierarchy</h3><div className="muted">No hierarchy loaded</div></div>
  const title = s.firmName && s.portfolioName ? `${s.firmName} → ${s.portfolioName}` : s.rootName
  return (
    <div className="card">
      <h3>Portfolio Hierarchy</h3>
      <div className="hierarchy">
        <strong>{title}</strong>
        <span>{s.desks} desks · {s.strategies} strategies · {s.books} books · {s.trades} trades</span>
        <span>NAV {money(s.market_value ?? 0)} · 99% VaR {money(s.var_99 ?? 0)} · ES {money(s.expected_shortfall_99 ?? 0)}</span>
        <span>Δ {money(s.delta ?? 0)} · ν {money(s.vega ?? 0)} · DV01 {money(s.dv01 ?? 0)}</span>
      </div>
    </div>
  )
}

export function Attribution({report}) {
  const s = attributionSummary(report)
  if (!s) return <div className="card"><h3>P&amp;L Explain</h3><div className="muted">No attribution loaded</div></div>
  return (
    <div className="card">
      <h3>P&amp;L Explain</h3>
      <div className="muted">Illustrative previous market snapshot → current marks</div>
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

  useEffect(() => {
    if (!run?.id || isRiskRunTerminal(run)) return undefined
    let cancelled = false
    const tick = async () => {
      try {
        const next = await getRiskRun(run.id)
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
  }, [run?.id, run?.status])

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
