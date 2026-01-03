import { useState } from 'react'
import { limitDrilldown } from '../api'
import {
  breachedLimits, limitDrilldownSummary, limitStatus, limitStatusClass, money, percent, threatClass, topContributors,
} from '../lib/risk.mjs'

export function Contributors({items}) {
  return <div className="card"><h3>Component VaR Contributors</h3><div className="muted">Parametric component VaR by trade</div><table><tbody>{topContributors(items).map(x => <tr key={x.position_id}><td>{x.label}</td><td>{x.contribution_pct.toFixed(1)}%</td><td>{money(x.risk_amount)}</td></tr>)}</tbody></table></div>
}

export function Limits({items, portfolio}) {
  const breaches = breachedLimits(items)
  const [drilldown, setDrilldown] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function loadBreachDrilldown() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const report = await limitDrilldown(portfolio, { breaches_only: true, top_n: 5 })
      setDrilldown(limitDrilldownSummary(report))
    } catch (e) {
      setError(e.message || 'Drill-down failed')
      setDrilldown(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h3>Limits</h3>
      <table>
        <tbody>
          {items.map((x) => (
            <tr key={x.metric}>
              <td>{x.metric}</td>
              <td>{x.utilization_pct.toFixed(0)}%</td>
              <td className={`status ${limitStatusClass(x)}`}>{limitStatus(x)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {breaches.length > 0 && portfolio && (
        <div className="limit-drilldown">
          <div className="card-title-row">
            <div className="muted">{breaches.length} breach{breaches.length === 1 ? '' : 'es'} — drill into contributors</div>
            <button type="button" onClick={loadBreachDrilldown} disabled={loading}>
              {loading ? 'Loading…' : 'Drill down breaches'}
            </button>
          </div>
          {error && <div className="error">{error}</div>}
          {drilldown && (
            drilldown.items.length === 0
              ? <div className="muted foot">No breach drill-down rows returned</div>
              : (
                <div className="limit-drilldown-body">
                  <div className="muted foot">
                    Scope {drilldown.hierarchy_level}: {drilldown.hierarchy_node}
                  </div>
                  {drilldown.items.map((row) => (
                    <div key={`${row.hierarchy_node}-${row.metric}`} className="limit-drilldown-item">
                      <strong>{row.metric}</strong>
                      <span className={`status ${limitStatusClass(row)}`}>
                        {limitStatus(row)} · {row.utilization_pct.toFixed(0)}%
                      </span>
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
      )}
    </div>
  )
}

export function Stress({items}) {
  return <div className="card wide"><h3>Stress Tests</h3><table><thead><tr><th>Scenario</th><th>P&amp;L</th></tr></thead><tbody>{items.map(x => <tr key={x.scenario}><td>{x.scenario}</td><td className={x.pnl < 0 ? 'negative' : 'positive'}>{money(x.pnl)}</td></tr>)}</tbody></table></div>
}

export function ThreatScenarios({report}) {
  return <div className="card wide">
    <div className="card-title-row"><div><h3>Threat Scenario Evaluation</h3><div className="muted">Ranked by portfolio loss after full revaluation</div></div><div className="scenario-badges"><span>{report.breach_count} breaches</span><span>{report.severe_count} severe</span></div></div>
    <table>
      <thead><tr><th>Threat scenario</th><th>Type</th><th>Loss % NAV</th><th>Loss</th><th>Threshold</th><th>Level</th></tr></thead>
      <tbody>{report.evaluations.map(x => <tr key={x.scenario_id}>
        <td><strong>{x.scenario}</strong><div className="muted scenario-description">{x.description}</div></td>
        <td>{x.kind.replaceAll('_', ' ')}</td>
        <td>{percent(x.loss_pct_nav)}</td>
        <td className={x.loss > 0 ? 'negative' : 'positive'}>{money(x.loss)}</td>
        <td>{x.max_loss_pct == null ? '—' : percent(x.max_loss_pct)}</td>
        <td><span className={`threat ${threatClass(x.threat_level)}`}>{x.threat_level}{x.breached ? ' / BREACH' : ''}</span></td>
      </tr>)}</tbody>
    </table>
  </div>
}
