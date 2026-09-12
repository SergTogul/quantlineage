import { useState } from 'react'
import MetricCard from './MetricCard'
import { FactorExposureHeatmap, HierarchyRiskHeatmap } from './Heatmaps'
import { Hierarchy } from './Analytics'
import { RiskQuery } from './ScenarioBuilder'
import { NAV_SECTIONS } from '../lib/nav.mjs'
import {
  limitStatus, limitStatusCounts, money, overviewBookStatus, overviewCollage,
  overviewExceptions, overviewKpis, overviewTapeRows, stressSummary,
} from '../lib/risk.mjs'

function BookStatus({ status, onNavigate }) {
  return (
    <section
      className={`book-status book-status-${status.tone}`}
      aria-label="Book status"
      data-testid="book-status"
    >
      <div className="book-status-copy">
        <h3 className="book-status-word">{status.label}</h3>
        <p className="book-status-reason">{status.reason}</p>
      </div>
      <button
        type="button"
        className="book-status-go"
        onClick={() => onNavigate?.(status.drill.id)}
      >
        {status.drill.label}
      </button>
    </section>
  )
}

function KpiStrip({ kpis }) {
  return (
    <section className="metrics metrics-tape" aria-label="Key risk metrics" data-testid="golden-demo-metrics">
      <MetricCard label="Market Value" value={money(kpis.market_value ?? 0)} />
      <MetricCard label="99% VaR" value={money(kpis.var_99 ?? 0)} />
      <MetricCard label="99% Expected Shortfall" value={money(kpis.expected_shortfall_99 ?? 0)} />
    </section>
  )
}

function ExceptionRows({ rows, onSelect, selectedKey }) {
  if (!rows.length) return null
  return (
    <ul>
      {rows.map((row) => (
        <li key={row.key}>
          <button
            type="button"
            className={`exception-row exception-${row.tone}${row.lead ? ' lead' : ''}${selectedKey === row.key ? ' selected' : ''}`}
            aria-label={`${row.title} ${row.detail}`.trim()}
            aria-pressed={selectedKey === row.key}
            onClick={() => onSelect?.(row)}
          >
            <span className="exception-title">{row.title}</span>
            <span className="exception-detail">{row.detail}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function TerminalMap({ cards, kpis, onNavigate }) {
  return (
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
  )
}

function useOverviewModel({ summary, threats, limits, hierarchy, stress, factors }) {
  const kpis = overviewKpis(summary, threats)
  const status = overviewBookStatus({ limits, threats })
  const exceptions = overviewExceptions({ limits, threats })
  const cards = overviewCollage({ summary, threats, limits, hierarchy, stress, factors })
  const tape = overviewTapeRows({ summary, threats, limits })
  return { kpis, status, exceptions, cards, tape }
}

export function StatusBlotterLayout({
  summary, threats, limits, hierarchy, stress, factors, onNavigate,
}) {
  const { kpis, status, exceptions, cards } = useOverviewModel({
    summary, threats, limits, hierarchy, stress, factors,
  })
  return (
    <div data-testid="overview-layout-status">
      <BookStatus status={status} onNavigate={onNavigate} />
      <section className="exception-list" aria-label="Exceptions">
        <h3>Where</h3>
        {exceptions.length ? (
          <ExceptionRows rows={exceptions} onSelect={(row) => onNavigate?.(row.section)} />
        ) : (
          <p className="muted overview-empty">{status.reason}</p>
        )}
      </section>
      <KpiStrip kpis={kpis} />
      <div className="grid overview-teasers">
        <FactorExposureHeatmap items={factors} />
        <HierarchyRiskHeatmap node={hierarchy} />
      </div>
      <TerminalMap cards={cards} kpis={kpis} onNavigate={onNavigate} />
    </div>
  )
}

function DockPanel({ row, limits, threats, onNavigate }) {
  if (!row) {
    return (
      <div className="overview-dock-empty" data-testid="overview-dock">
        Select an exception. Specialist figures stay on the API payload.
      </div>
    )
  }
  const limit = (limits || []).find((item) => (item.label || item.metric) === row.title)
  const threat = (threats?.evaluations || []).find((item) => item.scenario === row.title)
  return (
    <div className="overview-dock" data-testid="overview-dock">
      <h3>{row.title}</h3>
      {limit ? (
        <dl className="overview-dock-dl">
          <div><dt>Status</dt><dd className={`status ${limitStatus(limit).toLowerCase()}`}>{limit.status || limitStatus(limit)}</dd></div>
          <div><dt>Utilization</dt><dd>{Number(limit.utilization_pct).toFixed(0)}%</dd></div>
          <div><dt>Value</dt><dd>{money(limit.value ?? 0)}</dd></div>
          <div><dt>Limit</dt><dd>{money(limit.limit ?? 0)}</dd></div>
        </dl>
      ) : threat ? (
        <dl className="overview-dock-dl">
          <div><dt>Scenario</dt><dd>{threat.scenario}</dd></div>
          <div><dt>Loss</dt><dd>{money(threat.loss ?? 0)}</dd></div>
        </dl>
      ) : (
        <p className="muted">{row.detail}</p>
      )}
      <button type="button" className="book-status-go" onClick={() => onNavigate?.(row.section)}>
        Open {row.section === 'limits' ? 'Limits' : 'Stress'}
      </button>
    </div>
  )
}

export function TwoPaneDeskLayout({
  summary, threats, limits, hierarchy, stress, factors, onNavigate,
}) {
  const { kpis, status, exceptions } = useOverviewModel({
    summary, threats, limits, hierarchy, stress, factors,
  })
  const [selectedKey, setSelectedKey] = useState(exceptions[0]?.key ?? null)
  const selected = exceptions.find((row) => row.key === selectedKey) || null
  return (
    <div className="overview-desk" data-testid="overview-layout-desk">
      <div className="overview-desk-rail">
        <BookStatus status={status} onNavigate={onNavigate} />
        <KpiStrip kpis={kpis} />
        <section className="exception-list" aria-label="Exceptions">
          <h3>Where</h3>
          {exceptions.length ? (
            <ExceptionRows
              rows={exceptions}
              selectedKey={selectedKey}
              onSelect={(row) => setSelectedKey(row.key)}
            />
          ) : (
            <p className="muted overview-empty">{status.reason}</p>
          )}
        </section>
      </div>
      <DockPanel row={selected} limits={limits} threats={threats} onNavigate={onNavigate} />
    </div>
  )
}

export function ExceptionQueueLayout({
  summary, threats, limits, hierarchy, stress, factors, onNavigate,
}) {
  const { kpis, status, exceptions } = useOverviewModel({
    summary, threats, limits, hierarchy, stress, factors,
  })
  return (
    <div data-testid="overview-layout-queue">
      <p className={`overview-headline overview-headline-${status.tone}`}>
        {status.label} · {status.reason}
      </p>
      <KpiStrip kpis={kpis} />
      <section className="exception-list overview-queue" aria-label="Exception queue">
        <h3>Exception queue</h3>
        {exceptions.length ? (
          <ExceptionRows rows={exceptions} onSelect={(row) => onNavigate?.(row.section)} />
        ) : (
          <p className="muted overview-empty">{status.reason}</p>
        )}
      </section>
    </div>
  )
}

export function LaunchpadMosaicLayout({
  summary, threats, limits, hierarchy, stress, factors, onNavigate,
}) {
  const { kpis, status } = useOverviewModel({
    summary, threats, limits, hierarchy, stress, factors,
  })
  const [focus, setFocus] = useState('var')
  const counts = limitStatusCounts(limits)
  const ts = stressSummary(threats)
  const monitors = [
    {
      id: 'var',
      title: 'VaR tape',
      section: 'var-es',
      body: (
        <>
          <div>NAV {money(kpis.market_value ?? 0)}</div>
          <div>99% VaR {money(kpis.var_99 ?? 0)}</div>
          <div>99% ES {money(kpis.expected_shortfall_99 ?? 0)}</div>
        </>
      ),
    },
    {
      id: 'limits',
      title: 'Limits',
      section: 'limits',
      body: (
        <>
          <div>{counts.BREACH} breach · {counts.WARNING} warn · {counts.OK} ok</div>
          {(limits || []).filter((item) => limitStatus(item) === 'BREACH').slice(0, 3).map((item) => (
            <div key={item.metric}>{item.label || item.metric} {Number(item.utilization_pct).toFixed(0)}%</div>
          ))}
        </>
      ),
    },
    {
      id: 'threats',
      title: 'Threats',
      section: 'stress',
      body: ts.worst ? (
        <>
          <div>{ts.worst.scenario}</div>
          <div>{money(ts.worst.loss ?? 0)}</div>
          <div>{ts.breaches} threat breaches</div>
        </>
      ) : (
        <div>No threat evaluations on loaded payload</div>
      ),
    },
    {
      id: 'hierarchy',
      title: 'Hierarchy',
      section: 'portfolio',
      body: <HierarchyRiskHeatmap node={hierarchy} />,
    },
  ]
  return (
    <div data-testid="overview-layout-mosaic">
      <p className={`overview-headline overview-headline-${status.tone}`}>
        {status.label} · {status.reason}
      </p>
      <div className="overview-mosaic">
        {monitors.map((m) => (
          <article
            key={m.id}
            className={focus === m.id ? 'overview-monitor focused' : 'overview-monitor'}
          >
            <button
              type="button"
              className="overview-monitor-select"
              onClick={() => setFocus(m.id)}
            >
              {m.title}
            </button>
            <div className="overview-monitor-body">{m.body}</div>
            <button type="button" className="overview-monitor-open" onClick={() => onNavigate?.(m.section)}>
              Open {m.title}
            </button>
          </article>
        ))}
      </div>
    </div>
  )
}

export function CommandGoLayout({
  summary, threats, limits, hierarchy, stress, factors, onNavigate, portfolio,
}) {
  const { kpis, status } = useOverviewModel({
    summary, threats, limits, hierarchy, stress, factors,
  })
  return (
    <div data-testid="overview-layout-command">
      <p className={`overview-headline overview-headline-${status.tone}`}>
        {status.label} · {status.reason}
      </p>
      <div className="overview-command">
        <RiskQuery portfolio={portfolio} />
        <button type="button" className="book-status-go" onClick={() => onNavigate?.(status.drill.id)}>
          {status.drill.label}
        </button>
      </div>
      <KpiStrip kpis={kpis} />
    </div>
  )
}

export function HierarchyBookLayout({
  summary, threats, limits, hierarchy, stress, factors, onNavigate,
}) {
  const { status } = useOverviewModel({
    summary, threats, limits, hierarchy, stress, factors,
  })
  return (
    <div data-testid="overview-layout-hierarchy">
      <BookStatus status={status} onNavigate={onNavigate} />
      <Hierarchy node={hierarchy} />
      <div className="grid overview-teasers">
        <HierarchyRiskHeatmap node={hierarchy} />
        <FactorExposureHeatmap items={factors} />
      </div>
      <button type="button" className="book-status-go" onClick={() => onNavigate?.('portfolio')}>
        Open Portfolio
      </button>
    </div>
  )
}

export function OvernightTapeLayout({
  summary, threats, limits, hierarchy, stress, factors, onNavigate,
}) {
  const { kpis, status, tape } = useOverviewModel({
    summary, threats, limits, hierarchy, stress, factors,
  })
  return (
    <div data-testid="overview-layout-tape">
      <p className={`overview-headline overview-headline-${status.tone}`}>
        {status.label} · {status.reason}
      </p>
      <KpiStrip kpis={kpis} />
      <section className="exception-list" aria-label="Overnight tape">
        <h3>Overnight tape</h3>
        <ExceptionRows rows={tape} onSelect={(row) => onNavigate?.(row.section)} />
      </section>
    </div>
  )
}

export function FunctionKeysLayout({
  summary, threats, limits, hierarchy, stress, factors, onNavigate,
}) {
  const { kpis, status, cards } = useOverviewModel({
    summary, threats, limits, hierarchy, stress, factors,
  })
  const [focus, setFocus] = useState('var-es')
  const teaser = cards.find((c) => c.id === focus) || cards[0]
  return (
    <div data-testid="overview-layout-keys">
      <BookStatus status={status} onNavigate={onNavigate} />
      <KpiStrip kpis={kpis} />
      <div className="overview-fkey-strip" role="toolbar" aria-label="Function keys">
        {NAV_SECTIONS.map((s, i) => (
          <button
            key={s.id}
            type="button"
            className={focus === s.id ? 'overview-fkey active' : 'overview-fkey'}
            onClick={() => {
              if (s.id === 'overview') return
              setFocus(s.id)
            }}
          >
            F{i + 1} {s.label}
          </button>
        ))}
      </div>
      {teaser && teaser.id !== 'overview' && (
        <div className="overview-keys-teaser" data-testid="overview-keys-teaser">
          <h3>{teaser.label}</h3>
          <p className="muted">{teaser.hint}</p>
          <p>{teaser.teaser}</p>
          <button type="button" className="book-status-go" onClick={() => onNavigate?.(teaser.id)}>
            Open {teaser.label}
          </button>
        </div>
      )}
    </div>
  )
}
