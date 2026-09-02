import { useEffect, useState } from 'react'
import { loadDashboard } from './api'
import MetricCard from './components/MetricCard'
import { Contributors, Limits, Stress, ThreatScenarios } from './components/RiskTable'
import { Attribution, Hierarchy, RiskFactors, VaRAnalytics } from './components/Analytics'
import { ReverseStress, RiskQuery, ScenarioBuilder } from './components/ScenarioBuilder'
import { money, stressSummary } from './lib/risk.mjs'
import './styles.css'

export default function App() {
  const [data,setData]=useState(null),[error,setError]=useState('')
  useEffect(()=>{loadDashboard().then(setData).catch(e=>setError(e.message))},[])
  if(error)return <main><h1>RiskForge</h1><div className="error">API error: {error}</div></main>
  if(!data)return <main><h1>RiskForge</h1><div className="muted">Loading portfolio risk…</div></main>
  const {portfolio,summary,stress,threats,contributors,limits,factors,varReport,hierarchy,attribution}=data; const ts=stressSummary(threats)
  return <main>
    <header><div><span className="eyebrow">RISKFORGE</span><h1>{portfolio.name}</h1></div><div className="muted">Institutional Portfolio & Derivatives Risk</div></header>
    <section className="metrics"><MetricCard label="Market Value" value={money(summary.market_value)}/><MetricCard label="99% VaR" value={money(summary.var_99)}/><MetricCard label="99% Expected Shortfall" value={money(summary.expected_shortfall_99)}/><MetricCard label="Worst Threat Loss" value={money(ts.worst?.loss||0)}/><MetricCard label="Threat Breaches" value={String(ts.breaches)}/></section>
    <section className="grid"><RiskFactors items={factors}/><VaRAnalytics report={varReport}/><Contributors items={contributors}/><Limits items={limits}/><Hierarchy node={hierarchy}/><Attribution report={attribution}/><ReverseStress portfolio={portfolio}/><Stress items={stress}/><ThreatScenarios report={threats}/><ScenarioBuilder portfolio={portfolio}/><RiskQuery portfolio={portfolio}/></section>
    <section className="card wide"><h3>Positions</h3><table><thead><tr><th>ID</th><th>Type</th><th>Book</th><th>Instrument</th></tr></thead><tbody>{portfolio.positions.map(p=><tr key={p.id}><td>{p.id}</td><td>{p.type}</td><td>{p.book}</td><td>{p.symbol||p.pair||p.issuer||`${p.currency} swap`}</td></tr>)}</tbody></table></section>
  </main>
}
