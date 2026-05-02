import { useState } from 'react'
import { limitDrilldown } from '../api'
import BlockHelp from './BlockHelp'
import {
  breachedLimits, limitDrilldownSummary, limitStatus, limitStatusClass, limitStatusCounts,
  money, percent, threatClass, topContributors,
} from '../lib/risk.mjs'

export function Contributors({ items }) {
  return (
    <div className="card">
      <div className="block-title">
        <h3>Component VaR Contributors</h3>
        <BlockHelp id="component-var" />
      </div>
      <div className="muted">Parametric component VaR by trade</div>
      <table>
        <tbody>
          {topContributors(items).map((x) => (
            <tr key={x.position_id}>
              <td>{x.label}</td>
              <td>{x.contribution_pct.toFixed(1)}%</td>
              <td>{money(x.risk_amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * M8.8: Limits UX — status strip, value/limit/util table, per-metric + breach drill-down.
 * All numbers from LimitResult / LimitDrilldownReport APIs.
 */
export function Limits({ items, portfolio }) {
  const breaches = breachedLimits(items)
  const counts = limitStatusCounts(items)
  const [drilldown, setDrilldown] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [focusMetric, setFocusMetric] = useState(null)

  async function loadDrilldown(options) {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const report = await limitDrilldown(portfolio, { top_n: 5, ...options })
      setDrilldown(limitDrilldownSummary(report))
    } catch (e) {
      setError(e.message || 'Drill-down failed')
      setDrilldown(null)
    } finally {
      setLoading(false)
    }
  }

  async function loadBreachDrilldown() {
    setFocusMetric(null)
    await loadDrilldown({ breaches_only: true })
  }

  async function loadMetricDrilldown(metric) {
    setFocusMetric(metric)
    await loadDrilldown({ metric, breaches_only: false })
  }

  return (
    <div className="card wide">
      <div className="block-title">
        <h3>Limits</h3>
        <BlockHelp id="limits" />
      </div>
      <div className="muted">OK / WARNING / BREACH from LimitResult.status — drill via POST /risk/limits/drilldown</div>
      <div className="limit-status-strip" aria-label="Limit status summary">
        <span className="status ok">{counts.OK} OK</span>
        <span className="status warn">{counts.WARNING} WARNING</span>
        <span className="status breach">{counts.BREACH} BREACH</span>
      </div>
      <table className="limits-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Scope</th>
            <th>Value</th>
            <th>Limit</th>
            <th>Util %</th>
            <th>Warn @</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((x) => (
            <tr key={x.metric} className={focusMetric === x.metric ? 'limits-row-focus' : undefined}>
              <td>
                {x.label || x.metric}
                {x.label && x.label !== x.metric ? <div className="muted">{x.metric}</div> : null}
              </td>
              <td className="muted">{x.scope || '—'}</td>
              <td>{money(x.value ?? 0)}</td>
              <td>{money(x.limit ?? 0)}</td>
              <td>{(x.utilization_pct ?? 0).toFixed(0)}%</td>
              <td className="muted">{(x.warning_threshold_pct ?? 80).toFixed(0)}%</td>
              <td className={`status ${limitStatusClass(x)}`}>{limitStatus(x)}</td>
              <td>
                {portfolio && (
                  <button
                    type="button"
                    className="hierarchy-drill-btn"
                    onClick={() => loadMetricDrilldown(x.metric)}
                    disabled={loading}
                  >
                    Drill
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="limit-drilldown">
        <div className="card-title-row">
          <div className="muted">
            {breaches.length > 0
              ? `${breaches.length} breach${breaches.length === 1 ? '' : 'es'} — or drill any metric above`
              : 'No breaches — drill any metric for contributors'}
          </div>
          {portfolio && (
            <button type="button" onClick={loadBreachDrilldown} disabled={loading || breaches.length === 0}>
              {loading && !focusMetric ? 'Loading…' : 'Drill down breaches'}
            </button>
          )}
        </div>
        {error && <div className="error">{error}</div>}
        {drilldown && (
          drilldown.items.length === 0
            ? <div className="muted foot">No drill-down rows returned</div>
            : (
              <div className="limit-drilldown-body">
                <div className="muted foot">
                  Scope {drilldown.hierarchy_level}: {drilldown.hierarchy_node}
                  {focusMetric ? ` · metric ${focusMetric}` : ' · breaches'}
                </div>
                {drilldown.items.map((row) => (
                  <div key={`${row.hierarchy_node}-${row.metric}`} className="limit-drilldown-item">
                    <strong>{row.metric}</strong>
                    <span className={`status ${limitStatusClass(row)}`}>
                      {limitStatus(row)} · {(row.utilization_pct ?? 0).toFixed(0)}%
                    </span>
                    <div className="muted foot">
                      Value {money(row.value ?? 0)} / limit {money(row.limit ?? 0)}
                    </div>
                    {(row.contributors || []).length === 0
                      ? <div className="muted">No contributors</div>
                      : (
                        <table>
                          <tbody>
                            {row.contributors.map((c) => (
                              <tr key={c.position_id}>
                                <td>{c.label}</td>
                                <td>{c.contribution_pct.toFixed(1)}%</td>
                                <td>{money(c.risk_amount)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                  </div>
                ))}
              </div>
            )
        )}
      </div>
    </div>
  )
}

export function Stress({ items }) {
  return (
    <div className="card wide">
      <div className="block-title">
        <h3>Stress Tests</h3>
        <BlockHelp id="stress-tests" />
      </div>
      <table>
        <thead><tr><th>Scenario</th><th>P&amp;L</th></tr></thead>
        <tbody>
          {items.map((x) => (
            <tr key={x.scenario}>
              <td>{x.scenario}</td>
              <td className={x.pnl < 0 ? 'negative' : 'positive'}>{money(x.pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ThreatScenarios({ report }) {
  return (
    <div className="card wide">
      <div className="card-title-row">
        <div>
          <div className="block-title">
            <h3>Threat Scenario Evaluation</h3>
            <BlockHelp id="threat-scenarios" />
          </div>
          <div className="muted">Ranked by portfolio loss after full revaluation</div>
        </div>
        <div className="scenario-badges">
          <span>{report.breach_count} breaches</span>
          <span>{report.severe_count} severe</span>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Threat scenario</th>
            <th>Type</th>
            <th>Loss % NAV</th>
            <th>Loss</th>
            <th>Threshold</th>
            <th>Level</th>
          </tr>
        </thead>
        <tbody>
          {report.evaluations.map((x) => (
            <tr key={x.scenario_id}>
              <td>
                <strong>{x.scenario}</strong>
                <div className="muted scenario-description">{x.description}</div>
              </td>
              <td>{x.kind.replaceAll('_', ' ')}</td>
              <td>{percent(x.loss_pct_nav)}</td>
              <td className={x.loss > 0 ? 'negative' : 'positive'}>{money(x.loss)}</td>
              <td>{x.max_loss_pct == null ? '—' : percent(x.max_loss_pct)}</td>
              <td>
                <span className={`threat ${threatClass(x.threat_level)}`}>
                  {x.threat_level}{x.breached ? ' / BREACH' : ''}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
