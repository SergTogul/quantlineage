/**
 * Display-only mapping for contribution bars and KR-DV01 tenor charts.
 * Passes API amounts through; does not recompute contributions or sum KR tenors.
 */

/** Bar width 0–100 from |API amount| / maxAbs. Not a risk measure. */
export function contributionBarPct(amount, maxAbs) {
  const a = Math.abs(Number(amount))
  const m = Number(maxAbs)
  if (!Number.isFinite(a) || !Number.isFinite(m) || m <= 0) return 0
  return (a / m) * 100
}

/**
 * One display row per API contributor / ES factor row.
 * contribution_pct is copied from the payload — not recomputed.
 */
export function contributionBarRows(items, { amountKey = 'risk_amount', labelKey = 'label' } = {}) {
  const list = Array.isArray(items) ? items : []
  let maxAbs = 0
  for (const x of list) {
    const n = Math.abs(Number(x?.[amountKey]))
    if (Number.isFinite(n) && n > maxAbs) maxAbs = n
  }
  return list.map((x, i) => {
    const amount = Number(x?.[amountKey])
    const pct = Number(x?.contribution_pct)
    const finiteAmount = Number.isFinite(amount) ? amount : 0
    return {
      id: x?.position_id ?? x?.key ?? `${x?.[labelKey] ?? 'row'}-${i}`,
      label: x?.[labelKey] || x?.key || `Item ${i + 1}`,
      amount: finiteAmount,
      risk_amount: amountKey === 'risk_amount' ? finiteAmount : x?.risk_amount,
      contribution_pct: Number.isFinite(pct) ? pct : 0,
      barPct: contributionBarPct(finiteAmount, maxAbs),
    }
  })
}

/**
 * KR-DV01 tenor chart rows from GET /market/rates-showcase key_rate_dv01.
 * Each tenor is mapped independently. Callers must not add these values.
 */
export function keyRateDv01Chart(rows) {
  const list = Array.isArray(rows) ? rows : []
  let maxAbs = 0
  for (const r of list) {
    const n = Math.abs(Number(r?.value))
    if (Number.isFinite(n) && n > maxAbs) maxAbs = n
  }
  return {
    maxAbs,
    rows: list.map((r, i) => {
      const value = Number(r?.value)
      const finite = Number.isFinite(value) ? value : 0
      return {
        tenor: r?.tenor || `T${i + 1}`,
        value: finite,
        unit: r?.unit ?? '',
        barPct: contributionBarPct(finite, maxAbs),
      }
    }),
  }
}

/**
 * SVG polyline from an API dated series. Y is display scale on min/max
 * of the payload values — not a volatility, Sharpe, or drawdown measure.
 */
export function datedSeriesChart(series, { width = 640, height = 96, pad = 4 } = {}) {
  const list = Array.isArray(series) ? series : []
  const rowsIn = []
  for (const point of list) {
    const value = Number(point?.value)
    if (!Number.isFinite(value)) continue
    rowsIn.push({ as_of: point.as_of, value })
  }
  if (!rowsIn.length) return { points: '', rows: [], min: 0, max: 0 }
  let min = rowsIn[0].value
  let max = rowsIn[0].value
  for (const row of rowsIn) {
    if (row.value < min) min = row.value
    if (row.value > max) max = row.value
  }
  const span = max - min
  const innerH = height - pad * 2
  const innerW = width - pad * 2
  const n = rowsIn.length
  const rows = rowsIn.map((row, i) => {
    const x = n === 1 ? width / 2 : pad + (i / (n - 1)) * innerW
    const y = span === 0 ? height / 2 : pad + (1 - (row.value - min) / span) * innerH
    return { ...row, x, y }
  })
  return {
    points: rows.map((row) => `${row.x.toFixed(1)},${row.y.toFixed(1)}`).join(' '),
    rows,
    min,
    max,
  }
}

/**
 * Flagship T0→T1 waterfall steps from RiskChangeReport fields.
 * Copies API amounts; does not reconstruct residual or running totals.
 */
export function riskChangeWaterfallSteps(report) {
  if (!report) return []
  const specs = [
    { key: 't0', label: 'T0 risk', value: report.previous_risk, kind: 'level' },
    { key: 'portfolio', label: 'portfolio / trade change', value: report.portfolio_trade_change, kind: 'delta' },
    { key: 'market', label: 'market / factor changes', value: report.market_change, kind: 'delta' },
    {
      key: 'residual',
      label: report.residual_name || 'residual / interactions',
      value: report.residual,
      kind: 'delta',
    },
    { key: 't1', label: 'T1 risk', value: report.current_risk, kind: 'level' },
  ]
  let maxAbs = 0
  for (const spec of specs) {
    const n = Math.abs(Number(spec.value))
    if (Number.isFinite(n) && n > maxAbs) maxAbs = n
  }
  return specs.map((spec) => {
    const n = Number(spec.value)
    const finite = Number.isFinite(n) ? n : 0
    return {
      key: spec.key,
      label: spec.label,
      kind: spec.kind,
      value: finite,
      barPct: contributionBarPct(finite, maxAbs),
    }
  })
}
