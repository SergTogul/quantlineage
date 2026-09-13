import { money } from '../lib/risk.mjs'
import { contributionBarRows, keyRateDv01Chart } from '../lib/riskVisuals.mjs'

/**
 * Horizontal contribution bars from API amounts / contribution_pct.
 * Display scale only — no risk math.
 */
export function ContributionBars({
  items,
  amountKey = 'risk_amount',
  labelKey = 'label',
  ariaLabel = 'Contribution bars',
}) {
  const rows = contributionBarRows(items, { amountKey, labelKey })
  if (!rows.length) return null
  return (
    <div className="contrib-bars" role="list" aria-label={ariaLabel}>
      {rows.map((row) => (
        <div key={row.id} className="contrib-bar-row" role="listitem">
          <span className="contrib-bar-label">{row.label}</span>
          <div className="contrib-bar-track">
            <div
              data-testid="contribution-bar"
              className={`contrib-bar-fill ${row.amount < 0 ? 'negative' : 'positive'}`}
              style={{ width: `${row.barPct}%` }}
            />
          </div>
          <span className="contrib-bar-pct">{row.contribution_pct.toFixed(1)}%</span>
          <span className={`contrib-bar-amt ${row.amount < 0 ? 'negative' : 'positive'}`}>
            {money(row.amount)}
          </span>
        </div>
      ))}
    </div>
  )
}

/**
 * KR-DV01 by tenor from API key_rate_dv01. Parallel DV01 is a separate labeled field.
 */
export function KeyRateDv01Curve({ rows }) {
  const chart = keyRateDv01Chart(rows)
  if (!chart.rows.length) return null
  const W = 320
  const H = 72
  const n = chart.rows.length
  const points = chart.rows.map((row, i) => {
    const x = n === 1 ? W / 2 : (i / (n - 1)) * W
    const y = H - (row.barPct / 100) * (H - 8) - 4
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')

  return (
    <div className="tenor-curve" data-testid="kr-dv01-tenor-curve">
      <div className="muted">KR-DV01 by tenor from API key_rate_dv01</div>
      <svg
        className="tenor-curve-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="KR-DV01 by tenor"
      >
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          points={points}
        />
        {chart.rows.map((row, i) => {
          const x = n === 1 ? W / 2 : (i / (n - 1)) * W
          const y = H - (row.barPct / 100) * (H - 8) - 4
          return (
            <circle
              key={row.tenor}
              cx={Number(x.toFixed(1))}
              cy={Number(y.toFixed(1))}
              r="3"
              className={row.value < 0 ? 'tenor-dot-neg' : 'tenor-dot-pos'}
            />
          )
        })}
      </svg>
      <div className="tenor-curve-cols">
        {chart.rows.map((row) => (
          <div key={row.tenor} className="tenor-col">
            <span className={`tenor-val ${row.value < 0 ? 'negative' : 'positive'}`}>
              {money(row.value)}
            </span>
            <div className="tenor-col-track">
              <div
                className={`tenor-col-fill ${row.value < 0 ? 'negative' : 'positive'}`}
                style={{ height: `${row.barPct}%` }}
              />
            </div>
            <span className="tenor-label">{row.tenor}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
