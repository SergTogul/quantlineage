import { useState } from 'react'
import { money } from '../lib/risk.mjs'
import BlockHelp from './BlockHelp'
import {
  cellStyle, domainMaxAbs, divergingColor, sequentialColor, utilizationColor,
  hierarchyMetricCells, factorExposureMatrix, stressPnlCells, limitUtilizationCells,
} from '../lib/heatmap.mjs'

const HIER_METRICS = [
  { id: 'var_99', label: '99% VaR' },
  { id: 'expected_shortfall_99', label: '99% ES' },
  { id: 'market_value', label: 'NAV' },
]

const HIER_LEVELS = [
  { id: 'desk', label: 'Desk' },
  { id: 'strategy', label: 'Strategy' },
  { id: 'book', label: 'Book' },
]

function HeatLegend({ kind }) {
  if (kind === 'diverging') {
    return (
      <div className="heatmap-legend" aria-hidden="true">
        <span className="heatmap-swatch" style={{ background: divergingColor(-1, 1) }} />
        <span>loss</span>
        <span className="heatmap-swatch" style={{ background: divergingColor(0, 1) }} />
        <span>0</span>
        <span className="heatmap-swatch" style={{ background: divergingColor(1, 1) }} />
        <span>gain</span>
      </div>
    )
  }
  if (kind === 'utilization') {
    return (
      <div className="heatmap-legend" aria-hidden="true">
        <span className="heatmap-swatch" style={{ background: utilizationColor(20) }} />
        <span>low</span>
        <span className="heatmap-swatch" style={{ background: utilizationColor(85) }} />
        <span>warn</span>
        <span className="heatmap-swatch" style={{ background: utilizationColor(110) }} />
        <span>breach</span>
      </div>
    )
  }
  return (
    <div className="heatmap-legend" aria-hidden="true">
      <span className="heatmap-swatch" style={{ background: sequentialColor(0, 1) }} />
      <span>low</span>
      <span className="heatmap-swatch" style={{ background: sequentialColor(1, 1) }} />
      <span>high |API|</span>
    </div>
  )
}

/**
 * Hierarchy VaR / ES / NAV tiles — colors from API node metrics only.
 */
export function HierarchyRiskHeatmap({ node }) {
  const [metric, setMetric] = useState('var_99')
  const [level, setLevel] = useState('desk')
  const cells = hierarchyMetricCells(node, { levels: [level], metric })
  const maxAbs = domainMaxAbs(cells.map((c) => c.value))
  const metricLabel = HIER_METRICS.find((m) => m.id === metric)?.label || metric

  return (
    <div className="card wide">
      <div className="card-title-row">
        <div>
          <div className="block-title">
            <h3>Hierarchy risk heatmap</h3>
            <BlockHelp id="hierarchy-risk-heatmap" />
          </div>
          <div className="muted">
            Color scale of API {metricLabel} by {level} — POST /api/v1/risk/hierarchy (display only)
          </div>
        </div>
        <HeatLegend kind="sequential" />
      </div>
      <div className="inline-form risk-run-form heatmap-controls">
        <label>
          Metric
          <select aria-label="heatmap hierarchy metric" value={metric} onChange={(e) => setMetric(e.target.value)}>
            {HIER_METRICS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
        <label>
          Level
          <select aria-label="heatmap hierarchy level" value={level} onChange={(e) => setLevel(e.target.value)}>
            {HIER_LEVELS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
        </label>
      </div>
      {cells.length === 0
        ? <div className="muted foot">No {level} nodes in hierarchy</div>
        : (
          <div className="heatmap-tiles" role="list">
            {cells.map((c) => {
              const bg = sequentialColor(c.value, maxAbs)
              return (
                <div key={c.id} className="heatmap-tile" style={cellStyle(bg)} role="listitem" title={c.path}>
                  <span className="heatmap-tile-label">{c.label}</span>
                  <span className="heatmap-tile-value">{money(c.value)}</span>
                  <span className="heatmap-tile-meta">{c.level}</span>
                </div>
              )
            })}
          </div>
        )}
    </div>
  )
}

/**
 * Factor × bucket exposure matrix — cell values are API exposures.
 */
export function FactorExposureHeatmap({ items }) {
  const matrix = factorExposureMatrix(items)
  if (!matrix.rows.length) {
    return (
      <div className="card wide">
        <div className="block-title">
          <h3>Factor exposure heatmap</h3>
          <BlockHelp id="factor-exposure-heatmap" />
        </div>
        <div className="muted">No factor exposures from API</div>
      </div>
    )
  }

  return (
    <div className="card wide">
      <div className="card-title-row">
        <div>
          <div className="block-title">
            <h3>Factor exposure heatmap</h3>
            <BlockHelp id="factor-exposure-heatmap" />
          </div>
          <div className="muted">
            Factor × bucket grid from POST /api/v1/risk/factors — colors map API exposure (display only)
          </div>
        </div>
        <HeatLegend kind="diverging" />
      </div>
      <div className="heatmap-scroll">
        <table className="heatmap-matrix">
          <thead>
            <tr>
              <th scope="col">Factor</th>
              {matrix.cols.map((col) => <th key={col} scope="col">{col}</th>)}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row) => (
              <tr key={row}>
                <th scope="row">{row}</th>
                {matrix.cols.map((col) => {
                  const cell = matrix.cells.find((c) => c.row === row && c.col === col)
                  const v = cell?.value
                  if (v == null) {
                    return <td key={col} className="heatmap-empty">—</td>
                  }
                  const bg = divergingColor(v, matrix.maxAbs)
                  return (
                    <td key={col} className="heatmap-cell" style={cellStyle(bg)} title={`${row} · ${col}`}>
                      {money(v)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/**
 * Stress scenario P&L tiles — API pnl only.
 */
export function StressPnlHeatmap({ items }) {
  const cells = stressPnlCells(items)
  const maxAbs = domainMaxAbs(cells.map((c) => c.value))

  return (
    <div className="card wide">
      <div className="card-title-row">
        <div>
          <div className="block-title">
            <h3>Stress P&amp;L heatmap</h3>
            <BlockHelp id="stress-pnl-heatmap" />
          </div>
          <div className="muted">
            Scenario P&amp;L from POST /api/v1/risk/stress — diverging color on API pnl (display only)
          </div>
        </div>
        <HeatLegend kind="diverging" />
      </div>
      {cells.length === 0
        ? <div className="muted foot">No stress scenarios</div>
        : (
          <div className="heatmap-tiles" role="list">
            {cells.map((c) => {
              const bg = divergingColor(c.value, maxAbs)
              return (
                <div key={c.id} className="heatmap-tile" style={cellStyle(bg)} role="listitem">
                  <span className="heatmap-tile-label">{c.label}</span>
                  <span className="heatmap-tile-value">{money(c.value)}</span>
                </div>
              )
            })}
          </div>
        )}
    </div>
  )
}

/**
 * Limit utilization tiles — API utilization_pct bands.
 */
export function LimitUtilizationHeatmap({ items }) {
  const cells = limitUtilizationCells(items)

  return (
    <div className="card wide">
      <div className="card-title-row">
        <div>
          <div className="block-title">
            <h3>Limit utilization heatmap</h3>
            <BlockHelp id="limit-utilization-heatmap" />
          </div>
          <div className="muted">
            Utilization from POST /api/v1/risk/limits — color bands on API utilization_pct (display only)
          </div>
        </div>
        <HeatLegend kind="utilization" />
      </div>
      {cells.length === 0
        ? <div className="muted foot">No limits returned</div>
        : (
          <div className="heatmap-tiles" role="list">
            {cells.map((c) => {
              const bg = utilizationColor(c.value)
              return (
                <div key={c.id} className="heatmap-tile" style={cellStyle(bg)} role="listitem">
                  <span className="heatmap-tile-label">{c.label}</span>
                  <span className="heatmap-tile-value">{c.value.toFixed(0)}%</span>
                </div>
              )
            })}
          </div>
        )}
    </div>
  )
}
