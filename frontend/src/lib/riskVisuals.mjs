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
