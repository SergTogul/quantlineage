import { useEffect, useState } from 'react'
import { loadDashboard } from './api'
import MetricCard from './components/MetricCard'
import AppNav from './components/AppNav'
import { Contributors, Limits, Stress, ThreatScenarios } from './components/RiskTable'
import {
  Attribution, ESContributions, Hierarchy, RiskChangeAttribution, RiskFactors, RiskRuns,
  VaRAnalytics, VaRCompare,
} from './components/Analytics'
import { HedgeCompare, ReverseStress, RiskQuery, ScenarioBuilder } from './components/ScenarioBuilder'
import {
  FactorExposureHeatmap, HierarchyRiskHeatmap, LimitUtilizationHeatmap, StressPnlHeatmap,
} from './components/Heatmaps'
import { money, stressSummary } from './lib/risk.mjs'
import { hashForSection, navSectionById, sectionFromHash } from './lib/nav.mjs'
import './styles.css'

function SectionFrame({ id, children }) {
  const meta = navSectionById(id)
  return (
    <section className="view-section" id={id} aria-labelledby={`${id}-heading`}>
      <div className="view-section-head">
        <h2 id={`${id}-heading`}>{meta.label}</h2>
        <p className="muted">{meta.hint}</p>
      </div>
      {children}
    </section>
  )
}

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [section, setSection] = useState(() =>
    typeof window !== 'undefined' ? sectionFromHash(window.location.hash) : 'overview',
  )

  useEffect(() => {
    loadDashboard().then(setData).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    const onHash = () => setSection(sectionFromHash(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const selectSection = (id) => {
    const next = hashForSection(id)
    if (window.location.hash !== next) window.location.hash = next
    else setSection(sectionFromHash(next))
  }

  if (error) {
    return (
      <div className="app-shell">
        <AppNav active={section} onSelect={selectSection} />
        <main>
          <h1>RiskForge</h1>
          <div className="error">API error: {error}</div>
        </main>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="app-shell">
        <AppNav active={section} onSelect={selectSection} />
        <main>
          <h1>RiskForge</h1>
          <div className="muted">Loading portfolio risk…</div>
        </main>
      </div>
    )
  }

  const {
    portfolio, summary, stress, threats, contributors, limits, factors, varReport, hierarchy, attribution,
  } = data
  const ts = stressSummary(threats)

  const metrics = (
    <section className="metrics">
      <MetricCard label="Market Value" value={money(summary.market_value)} />
      <MetricCard label="99% VaR" value={money(summary.var_99)} />
      <MetricCard label="99% Expected Shortfall" value={money(summary.expected_shortfall_99)} />
      <MetricCard label="Worst Threat Loss" value={money(ts.worst?.loss || 0)} />
      <MetricCard label="Threat Breaches" value={String(ts.breaches)} />
    </section>
  )

  let body
  switch (section) {
    case 'portfolio':
      body = (
        <SectionFrame id="portfolio">
          <div className="grid">
            <Hierarchy node={hierarchy} />
            <HierarchyRiskHeatmap node={hierarchy} />
            <div className="card wide">
              <h3>Positions</h3>
              <table>
                <thead>
                  <tr><th>ID</th><th>Type</th><th>Book</th><th>Instrument</th></tr>
                </thead>
                <tbody>
                  {portfolio.positions.map((p) => (
                    <tr key={p.id}>
                      <td>{p.id}</td>
                      <td>{p.type}</td>
                      <td>{p.book}</td>
                      <td>{p.symbol || p.pair || p.issuer || `${p.currency} swap`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </SectionFrame>
      )
      break
    case 'risk-factors':
      body = (
        <SectionFrame id="risk-factors">
          <div className="grid">
            <RiskFactors items={factors} />
            <FactorExposureHeatmap items={factors} />
          </div>
        </SectionFrame>
      )
      break
    case 'var-es':
      body = (
        <SectionFrame id="var-es">
          <div className="grid">
            <VaRAnalytics report={varReport} />
            <Contributors items={contributors} />
            <ESContributions portfolio={portfolio} />
            <VaRCompare portfolio={portfolio} />
            <RiskChangeAttribution portfolio={portfolio} />
          </div>
        </SectionFrame>
      )
      break
    case 'stress':
      body = (
        <SectionFrame id="stress">
          <div className="grid">
            <StressPnlHeatmap items={stress} />
            <Stress items={stress} />
            <ThreatScenarios report={threats} />
            <ReverseStress portfolio={portfolio} />
          </div>
        </SectionFrame>
      )
      break
    case 'scenario-builder':
      body = (
        <SectionFrame id="scenario-builder">
          <div className="grid">
            <ScenarioBuilder portfolio={portfolio} />
            <HedgeCompare portfolio={portfolio} />
            <RiskQuery portfolio={portfolio} />
          </div>
        </SectionFrame>
      )
      break
    case 'pnl-explain':
      body = (
        <SectionFrame id="pnl-explain">
          <div className="grid"><Attribution report={attribution} /></div>
        </SectionFrame>
      )
      break
    case 'limits':
      body = (
        <SectionFrame id="limits">
          <div className="grid">
            <LimitUtilizationHeatmap items={limits} />
            <Limits items={limits} portfolio={portfolio} />
          </div>
        </SectionFrame>
      )
      break
    case 'risk-runs':
      body = (
        <SectionFrame id="risk-runs">
          <div className="grid"><RiskRuns portfolio={portfolio} /></div>
        </SectionFrame>
      )
      break
    default:
      body = (
        <SectionFrame id="overview">
          {metrics}
          <div className="grid">
            <RiskFactors items={factors} />
            <FactorExposureHeatmap items={factors} />
            <HierarchyRiskHeatmap node={hierarchy} />
            <VaRAnalytics report={varReport} />
            <Contributors items={contributors} />
            <Limits items={limits} portfolio={portfolio} />
            <RiskRuns portfolio={portfolio} />
          </div>
        </SectionFrame>
      )
  }

  return (
    <div className="app-shell">
      <AppNav active={section} onSelect={selectSection} />
      <main>
        <header>
          <div>
            <span className="eyebrow">RISKFORGE</span>
            <h1>{portfolio.name}</h1>
          </div>
          <div className="muted">Institutional Portfolio & Derivatives Risk</div>
        </header>
        {body}
      </main>
    </div>
  )
}
