import { useState } from 'react'
import { askRisk, evaluateCustomScenario, reverseStress } from '../api'
import { money, percent, scenarioPayload } from '../lib/risk.mjs'

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
