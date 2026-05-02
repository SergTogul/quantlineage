/**
 * Help copy for analysis card "?" popovers.
 * Sole source of block explanations — keep UI out of this file.
 * Tone: technical — what is shown and how RiskForge calculates it.
 */

const entries = {
  positions: {
    body:
      'Shows the loaded Portfolio positions (id, type, book, instrument terms). No pricing or risk is computed in this block — it is inventory display only.',
  },
  'portfolio-hierarchy': {
    body:
      'Firm→desk→strategy→book→trade tree. Each node’s NAV/VaR/ES/Greeks are HierarchyEngine aggregates of priced children under an explicit MarketSnapshot; the UI shows the selected node’s API fields only (no client re-aggregation).',
  },
  'hierarchy-risk-heatmap': {
    body:
      'Tiles children of a hierarchy level colored by an API metric (NAV, VaR, or ES). Values are the node metrics from HierarchyEngine; color is a display scale on |value|, not a new calculation.',
  },
  'risk-factors': {
    body:
      'Factor exposures from RiskFactorEngine: per position QuantLib valuation, then sum Δ (equity), vega (vol), DV01 (rates), FX Δ by typed factor key. Table ranks absolute exposure.',
  },
  'factor-exposure-heatmap': {
    body:
      'Factor × bucket matrix of the same RiskFactorEngine exposures (Δ / vega / DV01 / FX Δ aggregates). Cell color scales |exposure| for display only.',
  },
  'var-es': {
    body:
      '99% VaR and Expected Shortfall from the VaR report: historical (empirical PnL distribution from factor history) vs parametric. Both are server-side; UI displays method rows only.',
  },
  'component-var': {
    body:
      'Parametric component VaR by trade from the VaR analytics contributions API. Share = trade component / portfolio component; amounts are Euler-style API contributions, not recomputed in the browser.',
  },
  'es-contributions': {
    body:
      'Decomposes portfolio Expected Shortfall along a chosen dimension (hierarchy node or risk factor) via the ES-contribution engine. Tail average is computed server-side for the selected methodology.',
  },
  'var-compare': {
    body:
      'Side-by-side 95%/99% VaR and 99% ES for LINEAR, DELTA_GAMMA, and FULL_REVALUATION on the same historical factor panel. Each methodology rebuilds the PnL series then takes the quantile / tail mean.',
  },
  'risk-change-attribution': {
    body:
      'Waterfall of Δ(VaR or ES) between previous and current books. Drivers are position/market deltas from the change-attribution engine; residual = total − explained (not P&L Explain).',
  },
  'stress-pnl-heatmap': {
    body:
      'One tile per library stress scenario showing portfolio PnL = shocked MV − base MV after full revaluation under scenario shocks. Color diverges around zero from API `pnl`.',
  },
  'stress-tests': {
    body:
      'Named StressEngine scenarios: apply equity/vol/rates/FX shocks to the MarketSnapshot, full-revalue the book with the pricing engine, report PnL vs base.',
  },
  'threat-scenarios': {
    body:
      'Threat library evaluate: full-reval loss under each scenario, loss% = loss / |NAV|, threat band vs max_loss_pct threshold, ranked by loss. Breach when loss% exceeds the scenario limit.',
  },
  'reverse-stress': {
    body:
      'Binary search on one factor family (equity, rates, vol, or FX) for the smallest shock with loss ≥ target % of |NAV|. Each trial full-revalues under that shock; returns required_shock when converged.',
  },
  'reverse-stress-multi': {
    body:
      'Multi-factor reverse stress: weighted ray search then coordinate descent over selected factors to hit target loss % of |NAV|, subject to per-factor bounds. Solution shocks are server-optimized.',
  },
  'scenario-builder': {
    body:
      'Custom scenario: map UI equity%/vol%/rates bp/FX% into FactorShocks, apply to the snapshot, full-revalue, return loss, loss% NAV, and threat vs max_loss_pct.',
  },
  'hedge-compare': {
    body:
      'Compares base vs hedged book. Runs VaR/ES (chosen methodology), stress PnL, and factor exposures on both; reports Δ risk, scenario improvement, and factor exposure deltas.',
  },
  'risk-query': {
    body:
      'NL question routed to deterministic risk tools (summary, stress, contributors, etc.). Answer text is assembled from API results — no LLM-invented risk numbers.',
  },
  'pnl-explain': {
    body:
      'P&L attribution: Taylor/sensitivity decomposition of MV change across market and position drivers via the attribution engine. Residual closes the identity between total and explained change.',
  },
  'limit-utilization-heatmap': {
    body:
      'Per-limit utilization_pct = 100 × |metric value| / limit from LimitEngine (VaR/ES/stress-loss vs configured caps). Color bands map utilization to OK / warn (≥80) / breach (≥100).',
  },
  limits: {
    body:
      'LimitEngine compares live VaR, ES, and stress loss to portfolio limits → status OK/WARNING/BREACH and utilization. Drill-down recomputes top contributors for a metric via LimitDrilldownEngine.',
  },
  'risk-runs': {
    body:
      'Async RiskRun lifecycle: enqueue a run_type (e.g. var), worker computes and persists result refs, UI polls status QUEUED→RUNNING→COMPLETED/FAILED. No risk math in the client.',
  },
}

export const BLOCK_HELP = Object.freeze(
  Object.fromEntries(
    Object.entries(entries).map(([id, entry]) => [id, Object.freeze({ ...entry })]),
  ),
)

export const BLOCK_HELP_IDS = Object.freeze(Object.keys(BLOCK_HELP))

/** @param {string} id */
export function getBlockHelp(id) {
  return BLOCK_HELP[id] ?? null
}
