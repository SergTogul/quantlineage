import MetricCard from './MetricCard'
import { FactorExposureHeatmap, HierarchyRiskHeatmap } from './Heatmaps'
import { money, overviewCollage, overviewKpis } from '../lib/risk.mjs'

/**
 * M8.2 dedicated overview: KPI strip from API summary + section collage entry points.
 * Heatmap teasers are display-only; navigation uses hash sections (no client risk math).
 */
export default function Overview({
  summary,
  threats,
  limits,
  hierarchy,
  stress,
  factors,
  onNavigate,
}) {
  const kpis = overviewKpis(summary, threats)
  const cards = overviewCollage({ summary, threats, limits, hierarchy, stress, factors })

  return (
    <>
      <section className="metrics" aria-label="Key risk metrics" data-testid="golden-demo-metrics">
        <MetricCard label="Market Value" value={money(kpis.market_value ?? 0)} />
        <MetricCard label="99% VaR" value={money(kpis.var_99 ?? 0)} />
        <MetricCard label="99% Expected Shortfall" value={money(kpis.expected_shortfall_99 ?? 0)} />
        <MetricCard label="Worst Threat Loss" value={money(kpis.worst_threat_loss)} />
        <MetricCard label="Threat Breaches" value={String(kpis.threat_breaches)} />
      </section>

      <div className="overview-collage" aria-label="Terminal sections">
        <div className="overview-collage-head">
          <h3>Terminal map</h3>
          <p className="muted">
            Jump into risk workflows — teasers from loaded API payloads only
            {kpis.worst_threat_name ? ` · worst threat: ${kpis.worst_threat_name}` : ''}
          </p>
        </div>
        <div className="overview-tiles">
          {cards.map((c) => (
            <button
              key={c.id}
              type="button"
              className="overview-tile"
              onClick={() => onNavigate?.(c.id)}
            >
              <strong>{c.label}</strong>
              <span className="muted overview-tile-hint">{c.hint}</span>
              <span className="overview-tile-teaser">{c.teaser}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="grid overview-teasers">
        <HierarchyRiskHeatmap node={hierarchy} />
        <FactorExposureHeatmap items={factors} />
      </div>
    </>
  )
}
