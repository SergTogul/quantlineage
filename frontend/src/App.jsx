import { useEffect, useState } from 'react'
import { loadDashboard } from './api'
import AppNav from './components/AppNav'
import MarketData from './components/MarketData'
import Overview from './components/Overview'
import { Contributors, Limits, Stress, ThreatScenarios } from './components/RiskTable'
import {
  Attribution, ESContributions, Hierarchy, RatesShowcase, RiskChangeAttribution, RiskFactors, RiskRuns,
  VaRAnalytics, VaRCompare,
} from './components/Analytics'
import {
  HedgeCompare, ReverseStress, ReverseStressMulti, RiskQuery, ScenarioBuilder,
} from './components/ScenarioBuilder'
import {
  FactorExposureHeatmap, HierarchyRiskHeatmap, LimitUtilizationHeatmap, StressPnlHeatmap,
} from './components/Heatmaps'
import { applyTheme, persistTheme, readStoredTheme } from './lib/theme.mjs'
import { hashForOverviewLayout, hashForSection, navSectionById, parseRoute } from './lib/nav.mjs'
import BlockHelp from './components/BlockHelp'
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
  const [route, setRoute] = useState(() =>
    typeof window !== 'undefined'
      ? parseRoute(window.location.hash)
      : { section: 'overview', layout: 'status' },
  )
  const [theme, setTheme] = useState(() =>
    typeof window !== 'undefined' ? applyTheme(readStoredTheme()) : 'dark',
  )
  const section = route.section

  useEffect(() => {
    loadDashboard().then(setData).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const selectSection = (id) => {
    const next = hashForSection(id)
    if (window.location.hash !== next) window.location.hash = next
    else setRoute(parseRoute(next))
  }

  const selectLayout = (layout) => {
    const next = hashForOverviewLayout(layout)
    if (window.location.hash !== next) window.location.hash = next
    else setRoute(parseRoute(next))
  }

  const selectTheme = (next) => {
    const applied = applyTheme(next)
    persistTheme(applied)
    setTheme(applied)
  }

  if (error) {
    return (
      <div className="app-shell">
        <AppNav active={section} onSelect={selectSection} theme={theme} onThemeChange={selectTheme} />
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
        <AppNav active={section} onSelect={selectSection} theme={theme} onThemeChange={selectTheme} />
        <main>
          <h1>RiskForge</h1>
          <div className="muted">Loading portfolio risk…</div>
          <div className="skel-strip" aria-hidden="true" />
        </main>
      </div>
    )
  }

  const {
    portfolio, summary, stress, threats, contributors, limits, factors, varReport, hierarchy, attribution,
  } = data

  let body
  switch (section) {
    case 'portfolio':
      body = (
        <SectionFrame id="portfolio">
          <div className="grid">
            <Hierarchy node={hierarchy} />
            <HierarchyRiskHeatmap node={hierarchy} />
            <div className="card wide">
              <div className="block-title">
                <h3>Positions</h3>
                <BlockHelp id="positions" />
              </div>
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
            <RatesShowcase />
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
            <ReverseStressMulti portfolio={portfolio} />
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
          <div className="grid">
            <Attribution portfolio={portfolio} initialReport={attribution} />
          </div>
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
    case 'market-data':
      body = (
        <SectionFrame id="market-data">
          <div className="grid">
            <MarketData />
          </div>
        </SectionFrame>
      )
      break
    default:
      body = (
        <SectionFrame id="overview">
          <Overview
            summary={summary}
            threats={threats}
            limits={limits}
            hierarchy={hierarchy}
            stress={stress}
            factors={factors}
            portfolio={portfolio}
            layout={route.layout}
            onLayoutChange={selectLayout}
            onNavigate={selectSection}
          />
        </SectionFrame>
      )
  }

  return (
    <div className="app-shell">
      <AppNav active={section} onSelect={selectSection} theme={theme} onThemeChange={selectTheme} />
      <main>
        <header>
          <div>
            <h1>{portfolio.name}</h1>
            <div className="muted">Institutional Portfolio & Derivatives Risk</div>
          </div>
        </header>
        {body}
      </main>
    </div>
  )
}
