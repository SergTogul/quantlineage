import { useState } from 'react'
import { askRisk, compareHedge, evaluateCustomScenario, reverseStress } from '../api'
import {
  defaultHedgeScenarios, hedgeComparisonSummary, money, percent, scenarioPayload,
  spyFlatHedgePortfolio,
} from '../lib/risk.mjs'

const HEDGE_METHODS = ['LINEAR', 'DELTA_GAMMA', 'FULL_REVALUATION']

export function ScenarioBuilder({portfolio}) {
  const [form,setForm]=useState({name:'Custom Crash',equity:-20,vol:50,rates:100,fx:-5,limit:10})
  const [result,setResult]=useState(null); const set=(k)=>(e)=>setForm({...form,[k]:e.target.value})
  async function run(){ const r=await evaluateCustomScenario(portfolio,scenarioPayload(form)); setResult(r.evaluations[0]) }
  return <div className="card wide"><h3>Scenario Builder</h3><div className="scenario-form">
    <input value={form.name} onChange={set('name')} aria-label="scenario name"/><label>Equity %<input type="number" value={form.equity} onChange={set('equity')}/></label><label>Vol %<input type="number" value={form.vol} onChange={set('vol')}/></label><label>Rates bp<input type="number" value={form.rates} onChange={set('rates')}/></label><label>FX %<input type="number" value={form.fx} onChange={set('fx')}/></label><label>Loss limit %<input type="number" value={form.limit} onChange={set('limit')}/></label><button onClick={run}>Run scenario</button>
  </div>{result&&<div className="scenario-result"><strong>{result.scenario}</strong><span>Loss {money(result.loss)}</span><span>{percent(result.loss_pct_nav)} NAV</span><span className={`threat ${String(result.threat_level).toLowerCase()}`}>{result.threat_level}{result.breached?' / BREACH':''}</span></div>}</div>
}

export function ReverseStress({portfolio}) {
  const [factor,setFactor]=useState('equity'),[target,setTarget]=useState(5),[result,setResult]=useState(null)
  return <div className="card"><h3>Reverse Stress</h3><div className="inline-form"><select value={factor} onChange={e=>setFactor(e.target.value)}><option>equity</option><option>rates</option><option>vol</option><option>fx</option></select><input type="number" value={target} onChange={e=>setTarget(e.target.value)}/><span className="muted">% target loss</span><button onClick={async()=>setResult(await reverseStress(portfolio,factor,Number(target)/100))}>Solve</button></div>{result&&<p>{result.converged?`Required ${factor} shock: ${factor==='rates'?result.required_shock.toFixed(0)+' bp':percent(result.required_shock)}`:'Target not reached within search bound.'}</p>}</div>
}

export function RiskQuery({portfolio}) {
  const [q,setQ]=useState('What is the worst stress scenario?'),[r,setR]=useState(null)
  return <div className="card"><h3>Risk Query</h3><div className="query"><input value={q} onChange={e=>setQ(e.target.value)}/><button onClick={async()=>setR(await askRisk(portfolio,q))}>Ask</button></div>{r&&<p className="query-answer">{r.answer}</p>}<div className="muted">Deterministic routing to risk APIs; ready for an LLM tool layer later.</div></div>
}

/**
 * M8.5: before/after hedge workflow. Displays HedgeComparisonReport from API only.
 * Demo hedge = SPY equity flat (qty 0); default scenario = equity Crash −20%.
 */
export function HedgeCompare({ portfolio }) {
  const [methodology, setMethodology] = useState('DELTA_GAMMA')
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const hedged = spyFlatHedgePortfolio(portfolio)
      const report = await compareHedge(portfolio, hedged, defaultHedgeScenarios(), methodology)
      setSummary(hedgeComparisonSummary(report))
    } catch (e) {
      setError(e.message || 'Hedge compare failed')
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card wide">
      <h3>Hedge Compare</h3>
      <div className="muted">
        Before/after SPY flat hedge — VaR, ES, scenario P&amp;L, and factor deltas from API (no client risk math)
      </div>
      <div className="inline-form risk-run-form">
        <select
          value={methodology}
          onChange={(e) => setMethodology(e.target.value)}
          aria-label="hedge methodology"
          disabled={loading}
        >
          {HEDGE_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <button type="button" onClick={run} disabled={!portfolio || loading}>
          {loading ? 'Comparing…' : 'Compare hedge'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!summary && !error && <div className="muted foot">No comparison run yet</div>}
      {summary && (
        <div className="hedge-compare-result">
          <div className="attribution-total">
            <span>Hedge cost <strong>{money(summary.hedge_cost ?? 0)}</strong></span>
            <span>99% VaR {money(summary.base_var_99 ?? 0)} → {money(summary.hedged_var_99 ?? 0)}
              {' '}(<span className={(summary.var_improvement ?? 0) >= 0 ? 'positive' : 'negative'}>
                Δ {money(summary.var_improvement ?? 0)}
              </span>)
            </span>
            <span>99% ES {money(summary.base_expected_shortfall_99 ?? 0)} → {money(summary.hedged_expected_shortfall_99 ?? 0)}
              {' '}(<span className={(summary.es_improvement ?? 0) >= 0 ? 'positive' : 'negative'}>
                Δ {money(summary.es_improvement ?? 0)}
              </span>)
            </span>
            {summary.methodology && <span className="muted">{summary.methodology}</span>}
          </div>
          {summary.scenarios.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Base P&amp;L</th>
                  <th>Hedged P&amp;L</th>
                  <th>Improvement</th>
                  <th>Loss Δ</th>
                </tr>
              </thead>
              <tbody>
                {summary.scenarios.map((row) => (
                  <tr key={row.scenario}>
                    <td>{row.scenario}</td>
                    <td className={(row.base_pnl ?? 0) < 0 ? 'negative' : 'positive'}>{money(row.base_pnl ?? 0)}</td>
                    <td className={(row.hedged_pnl ?? 0) < 0 ? 'negative' : 'positive'}>{money(row.hedged_pnl ?? 0)}</td>
                    <td className={(row.improvement ?? 0) < 0 ? 'negative' : 'positive'}>{money(row.improvement ?? 0)}</td>
                    <td className={(row.loss_improvement ?? 0) < 0 ? 'negative' : 'positive'}>
                      {money(row.loss_improvement ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {summary.factor_exposure_changes.length > 0 && (
            <>
              <div className="muted foot">Factor exposure changes</div>
              <table>
                <thead><tr><th>Factor</th><th>Before</th><th>After</th><th>Δ</th></tr></thead>
                <tbody>
                  {summary.factor_exposure_changes.map((f) => (
                    <tr key={f.factor}>
                      <td>{f.factor}</td>
                      <td>{money(f.before ?? 0)}</td>
                      <td>{money(f.after ?? 0)}</td>
                      <td className={(f.delta ?? 0) < 0 ? 'negative' : 'positive'}>{money(f.delta ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </div>
  )
}
