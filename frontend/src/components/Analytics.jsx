import { useEffect, useState } from 'react'
import { createRiskRun, getRiskRun } from '../api'
import {
  money, topFactors, varMethod, hierarchySummary, attributionSummary,
  isRiskRunTerminal, riskRunStatus, riskRunStatusClass, riskRunSummary, RISK_RUN_POLL_MS,
} from '../lib/risk.mjs'

const RISK_RUN_TYPES = ['summary', 'var', 'stress', 'factors', 'limits', 'hierarchy', 'contributors']

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
