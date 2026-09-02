import { limitStatus, money, percent, threatClass, topContributors } from '../lib/risk.mjs'

export function Contributors({items}) {
  return <div className="card"><h3>Top Risk Contributors</h3><table><tbody>{topContributors(items).map(x => <tr key={x.position_id}><td>{x.label}</td><td>{x.contribution_pct.toFixed(1)}%</td><td>{money(x.risk_amount)}</td></tr>)}</tbody></table></div>
}

export function Limits({items}) {
  return <div className="card"><h3>Limits</h3><table><tbody>{items.map(x => <tr key={x.metric}><td>{x.metric}</td><td>{x.utilization_pct.toFixed(0)}%</td><td className={`status ${limitStatus(x).toLowerCase()}`}>{limitStatus(x)}</td></tr>)}</tbody></table></div>
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
